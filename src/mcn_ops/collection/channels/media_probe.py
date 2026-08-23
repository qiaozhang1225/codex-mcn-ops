from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from typing import Any

from .contracts import redact_payload
from .hub import ChannelsHub
from .probe import _is_loopback_host, _server_ssl_context


RANGE_END = 4095


def extract_media_candidate(value: Any) -> dict[str, Any] | None:
    """Extract one media candidate while keeping its credentials in memory only."""

    obj = _find_object(value)
    if obj is None:
        return None
    description = obj.get("objectDesc")
    if not isinstance(description, dict):
        description = {}
    media_list = description.get("media")
    if not isinstance(media_list, list) or not media_list:
        return {
            "work_id": str(obj.get("id") or ""),
            "nonce_id": str(obj.get("objectNonceId") or obj.get("nonceId") or ""),
            "encrypted_object_id": str(
                obj.get("encryptedObjectId") or obj.get("encrypted_objectid") or obj.get("eid") or ""
            ),
            "locator": "",
            "decryption_key": "",
            "duration_ms": 0,
            "file_size": 0,
        }
    media = next((item for item in media_list if isinstance(item, dict)), {})
    specs = media.get("spec") if isinstance(media.get("spec"), list) else []
    spec = next((item for item in specs if isinstance(item, dict)), {})
    base_url = str(media.get("url") or spec.get("url") or "")
    url_token = str(media.get("urlToken") or spec.get("urlToken") or "")
    locator = _join_locator(base_url, url_token)
    return {
        "work_id": str(obj.get("id") or ""),
        "nonce_id": str(obj.get("objectNonceId") or obj.get("nonceId") or ""),
        "encrypted_object_id": str(
            obj.get("encryptedObjectId") or obj.get("encrypted_objectid") or obj.get("eid") or ""
        ),
        "locator": locator,
        "decryption_key": str(
            media.get("decodeKey")
            or media.get("decryptKey")
            or spec.get("decodeKey")
            or spec.get("decryptKey")
            or ""
        ),
        "duration_ms": _safe_int(
            media.get("durationMs") or spec.get("durationMs") or media.get("videoPlayLen")
        ),
        "file_size": _safe_int(media.get("fileSize") or media.get("cdnFileSize") or spec.get("fileSize")),
    }


def summarize_candidate(candidate: dict[str, Any], *, source: str) -> dict[str, Any]:
    locator = str(candidate.get("locator") or "")
    parsed = urllib.parse.urlsplit(locator) if locator else None
    return {
        "work_id": str(candidate.get("work_id") or ""),
        "nonce_id_present": bool(candidate.get("nonce_id")),
        "encrypted_object_id_present": bool(candidate.get("encrypted_object_id")),
        "locator_present": bool(locator),
        "locator_source": source if locator else "none",
        "locator_scheme": parsed.scheme if parsed else "",
        "locator_host": parsed.hostname or "" if parsed else "",
        "locator_query_keys": sorted(
            {key for key, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)}
        )
        if parsed
        else [],
        "decryption_key_present": bool(candidate.get("decryption_key")),
        "duration_ms": _safe_int(candidate.get("duration_ms")),
        "file_size": _safe_int(candidate.get("file_size")),
    }


async def run_media_probe(
    hub: ChannelsHub,
    *,
    worker_id: str,
    keyword: str,
    page_size: int = 20,
    command_timeout: float = 180.0,
    locator_timeout: float = 20.0,
) -> dict[str, Any]:
    search = await hub.call(
        worker_id,
        "search_videos",
        {"keyword": keyword, "page": 1, "page_size": page_size},
        timeout=command_timeout,
        require_search_ready=True,
    )
    items = search.get("list") if isinstance(search, dict) else None
    if not isinstance(items, list):
        raise ValueError("search response data.list must be an array")

    search_candidates = [extract_media_candidate(item) for item in items]
    search_candidates = [item for item in search_candidates if item and item.get("work_id")]
    if not search_candidates:
        raise ValueError("search returned no usable work identity")
    candidate = next((item for item in search_candidates if item.get("locator")), search_candidates[0])
    source = "search"
    detail_attempted = False
    detail_success = False
    detail_error_type = ""

    if candidate.get("encrypted_object_id") or (candidate.get("work_id") and candidate.get("nonce_id")):
        detail_attempted = True
        body = {
            "objectId": candidate.get("work_id") or "",
            "nonceId": candidate.get("nonce_id") or "",
            "eid": candidate.get("encrypted_object_id") or "",
        }
        try:
            detail = await hub.call(
                worker_id,
                "api_call",
                {"key": "key:channels:feed_profile", "body": body},
                timeout=command_timeout,
                require_search_ready=True,
            )
            detail_success = True
            detail_candidate = extract_media_candidate(detail)
            if detail_candidate and detail_candidate.get("locator"):
                candidate = detail_candidate
                source = "detail"
        except Exception as exc:  # the exception message can contain signed data
            detail_error_type = type(exc).__name__

    candidate_summary = summarize_candidate(candidate, source=source)
    locator = str(candidate.get("locator") or "")
    range_probe = await asyncio.to_thread(
        _probe_locator,
        locator,
        str(candidate.get("decryption_key") or ""),
        locator_timeout,
    )
    return {
        "keyword": keyword,
        "search_items": len(items),
        "detail_attempted": detail_attempted,
        "detail_success": detail_success,
        "detail_error_type": detail_error_type,
        "candidate": candidate_summary,
        "range_probe": range_probe,
        "persisted_media": False,
    }


def _probe_locator(locator: str, decryption_key: str, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(locator),
        "reachable": False,
        "status": 0,
        "content_type": "",
        "content_length": 0,
        "content_range_present": False,
        "returned_bytes": 0,
        "mp4_ftyp_visible": False,
        "decryption_attempted": False,
        "decrypted_mp4_ftyp_visible": False,
        "decryption_error_type": "",
        "sample_sha256": "",
        "final_host": "",
        "error_type": "",
    }
    if not locator:
        return result
    request = urllib.request.Request(
        locator,
        headers={"Range": f"bytes=0-{RANGE_END}", "User-Agent": "Mozilla/5.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            sample = response.read(RANGE_END + 1)
            result.update(
                {
                    "reachable": True,
                    "status": int(response.status),
                    "content_type": str(response.headers.get("Content-Type") or "").split(";", 1)[0],
                    "content_length": _safe_int(response.headers.get("Content-Length")),
                    "content_range_present": bool(response.headers.get("Content-Range")),
                    "returned_bytes": len(sample),
                    "mp4_ftyp_visible": b"ftyp" in sample[:64],
                    "sample_sha256": hashlib.sha256(sample).hexdigest() if sample else "",
                    "final_host": urllib.parse.urlsplit(response.geturl()).hostname or "",
                }
            )
            if decryption_key and sample:
                result["decryption_attempted"] = True
                try:
                    seed = int(decryption_key, 10)
                    stream = _Isaac64(seed).generate(len(sample))
                    decrypted = bytes(left ^ right for left, right in zip(sample, stream, strict=True))
                    result["decrypted_mp4_ftyp_visible"] = b"ftyp" in decrypted[:64]
                except Exception as exc:
                    result["decryption_error_type"] = type(exc).__name__
    except urllib.error.HTTPError as exc:
        result.update(
            {
                "status": int(exc.code),
                "final_host": urllib.parse.urlsplit(exc.geturl()).hostname or "",
                "error_type": type(exc).__name__,
            }
        )
    except Exception as exc:
        result["error_type"] = type(exc).__name__
    return result


def _find_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("objectDesc"), dict):
        return value
    if isinstance(value.get("object"), dict):
        return value["object"]
    for key in ("data", "response"):
        found = _find_object(value.get(key))
        if found is not None:
            return found
    return None


def _join_locator(base_url: str, url_token: str) -> str:
    if not base_url:
        return url_token
    if not url_token:
        return base_url
    if url_token.startswith("http://") or url_token.startswith("https://"):
        return url_token
    return f"{base_url}{url_token}"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class _Isaac64:
    """Small ISAAC64 implementation matching the worker's 128 KiB prefix cipher."""

    _MASK = (1 << 64) - 1

    def __init__(self, seed: int) -> None:
        self.randrsl = [0] * 256
        self.mm = [0] * 256
        self.aa = 0
        self.bb = 0
        self.cc = 0
        self.randcnt = 0
        self.randrsl[0] = seed & self._MASK
        self._randinit()

    def _mix(self, values: list[int]) -> list[int]:
        a, b, c, d, e, f, g, h = values
        mask = self._MASK
        a = (a - e) & mask
        f = (f ^ (h >> 9)) & mask
        h = (h + a) & mask
        b = (b - f) & mask
        g = (g ^ ((a << 9) & mask)) & mask
        a = (a + b) & mask
        c = (c - g) & mask
        h = (h ^ (b >> 23)) & mask
        b = (b + c) & mask
        d = (d - h) & mask
        a = (a ^ ((c << 15) & mask)) & mask
        c = (c + d) & mask
        e = (e - a) & mask
        b = (b ^ (d >> 14)) & mask
        d = (d + e) & mask
        f = (f - b) & mask
        c = (c ^ ((e << 20) & mask)) & mask
        e = (e + f) & mask
        g = (g - c) & mask
        d = (d ^ (f >> 17)) & mask
        f = (f + g) & mask
        h = (h - d) & mask
        e = (e ^ ((g << 14) & mask)) & mask
        g = (g + h) & mask
        return [a, b, c, d, e, f, g, h]

    def _randinit(self) -> None:
        state = [0x9E3779B97F4A7C13] * 8
        for _ in range(4):
            state = self._mix(state)
        for start in range(0, 256, 8):
            state = [
                (state[index] + self.randrsl[start + index]) & self._MASK for index in range(8)
            ]
            state = self._mix(state)
            self.mm[start : start + 8] = state
        for start in range(0, 256, 8):
            state = [(state[index] + self.mm[start + index]) & self._MASK for index in range(8)]
            state = self._mix(state)
            self.mm[start : start + 8] = state
        self._isaac64()
        self.randcnt = 256

    def _isaac64(self) -> None:
        mask = self._MASK
        self.cc = (self.cc + 1) & mask
        self.bb = (self.bb + self.cc) & mask
        for index in range(256):
            x = self.mm[index]
            if index % 4 == 0:
                self.aa = (~(self.aa ^ ((self.aa << 21) & mask))) & mask
            elif index % 4 == 1:
                self.aa = (self.aa ^ (self.aa >> 5)) & mask
            elif index % 4 == 2:
                self.aa = (self.aa ^ ((self.aa << 12) & mask)) & mask
            else:
                self.aa = (self.aa ^ (self.aa >> 33)) & mask
            self.aa = (self.aa + self.mm[(index + 128) % 256]) & mask
            y = (self.mm[(x >> 3) % 256] + self.aa + self.bb) & mask
            self.mm[index] = y
            self.bb = (self.mm[(y >> 11) % 256] + x) & mask
            self.randrsl[index] = self.bb

    def generate(self, length: int) -> bytes:
        result = bytearray()
        while len(result) < length:
            if self.randcnt == 0:
                self._isaac64()
                self.randcnt = 256
            self.randcnt -= 1
            result.extend(self.randrsl[self.randcnt].to_bytes(8, "big"))
        return bytes(result[:length])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe a Channels media locator without persisting media.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--wait-timeout", type=float, default=120.0)
    parser.add_argument("--command-timeout", type=float, default=180.0)
    parser.add_argument("--locator-timeout", type=float, default=20.0)
    parser.add_argument("--secret-env", default="CHANNELS_HUB_SECRET")
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--allow-insecure-lan", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> int:
    secret = os.environ.get(args.secret_env, "").strip()
    if not secret:
        raise ValueError(f"environment variable {args.secret_env} is required")
    ssl_context = _server_ssl_context(args.tls_cert, args.tls_key)
    if not _is_loopback_host(args.host) and ssl_context is None and not args.allow_insecure_lan:
        raise ValueError(
            "non-loopback binding requires --tls-cert/--tls-key; "
            "use --allow-insecure-lan only for a controlled PoC"
        )
    hub = ChannelsHub(shared_secret=secret, allowed_worker_ids={args.worker_id})
    await hub.start(args.host, args.port, ssl_context=ssl_context)
    print(
        json.dumps(
            {"event": "hub_listening", "port": hub.listening_port, "worker_id": args.worker_id},
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        capabilities = await hub.wait_for_worker(
            args.worker_id, timeout=args.wait_timeout, require_search_ready=True
        )
        print(
            json.dumps(
                {"event": "worker_ready", "capabilities": redact_payload(asdict(capabilities))},
                ensure_ascii=False,
            ),
            flush=True,
        )
        result = await run_media_probe(
            hub,
            worker_id=args.worker_id,
            keyword=args.keyword,
            page_size=args.page_size,
            command_timeout=args.command_timeout,
            locator_timeout=args.locator_timeout,
        )
        print(json.dumps({"event": "media_probe_result", "result": result}, ensure_ascii=False), flush=True)
        return 0
    finally:
        await hub.stop()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
