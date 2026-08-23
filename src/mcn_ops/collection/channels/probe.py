from __future__ import annotations

import argparse
import asyncio
import html
import ipaddress
import json
import os
import ssl
from dataclasses import asdict
from typing import Any

from .contracts import redact_payload
from .hub import ChannelsHub


async def run_search_probe(
    hub: ChannelsHub,
    *,
    worker_id: str,
    keyword: str,
    max_pages: int,
    page_size: int = 20,
    command_timeout: float = 180.0,
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    next_marker = ""
    has_more = False
    stop_reason = "source_exhausted"
    for page_number in range(1, max_pages + 1):
        data = await hub.call(
            worker_id,
            "search_videos",
            {
                "keyword": keyword,
                "next_marker": next_marker,
                "page": page_number,
                "page_size": page_size,
            },
            timeout=command_timeout,
            require_search_ready=True,
        )
        if not isinstance(data, dict):
            raise ValueError("search response data must be an object")
        items = data.get("list")
        if not isinstance(items, list):
            raise ValueError("search response data.list must be an array")
        has_more = bool(data.get("has_more"))
        returned_marker = str(data.get("next_marker") or "")
        pages.append(
            {
                "page": page_number,
                "item_count": len(items),
                "items": [_summarize_search_item(item) for item in items],
                "has_more": has_more,
                "next_marker": "<present>" if returned_marker else "",
            }
        )
        if not has_more:
            stop_reason = "source_exhausted"
            next_marker = ""
            break
        if not returned_marker:
            stop_reason = "cursor_missing"
            next_marker = ""
            break
        next_marker = returned_marker
    else:
        stop_reason = "max_pages" if has_more else "source_exhausted"

    source_exhausted = stop_reason == "source_exhausted"
    return {
        "keyword": keyword,
        "captured_pages": len(pages),
        "captured_items": sum(int(page["item_count"]) for page in pages),
        "has_next": has_more,
        "source_exhausted": source_exhausted,
        "request_satisfied": source_exhausted or len(pages) >= max_pages,
        "stop_reason": stop_reason,
        "pages": pages,
    }


def _summarize_search_item(value: Any) -> dict[str, Any]:
    """Retain only public, stable evidence needed by the search-only gate."""

    if not isinstance(value, dict):
        return {"invalid_shape": type(value).__name__}
    obj = value.get("object") if isinstance(value.get("object"), dict) else value
    contact = obj.get("contact") if isinstance(obj.get("contact"), dict) else {}
    description = obj.get("objectDesc") if isinstance(obj.get("objectDesc"), dict) else {}
    media = description.get("media") if isinstance(description.get("media"), list) else []
    primary_media = media[0] if media and isinstance(media[0], dict) else {}
    specs = primary_media.get("spec") if isinstance(primary_media.get("spec"), list) else []
    primary_spec = specs[0] if specs and isinstance(specs[0], dict) else {}
    description_text = html.unescape(str(description.get("description") or ""))
    if len(description_text) > 500:
        description_text = f"{description_text[:500]}…"
    return {
        "work_id": str(obj.get("id") or ""),
        "author_id": str(contact.get("username") or obj.get("username") or ""),
        "author_name": str(contact.get("nickname") or obj.get("nickname") or ""),
        "description": description_text,
        "created_at": int(obj.get("createtime") or 0),
        "duration_ms": int(primary_spec.get("durationMs") or 0),
        "like_count": int(obj.get("likeCount") or 0),
        "favorite_count": int(obj.get("favCount") or 0),
        "comment_count": int(obj.get("commentCount") or 0),
        "share_count": int(obj.get("forwardCount") or 0),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a search-only WeChat Channels LAN probe.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--wait-timeout", type=float, default=120.0)
    parser.add_argument("--command-timeout", type=float, default=180.0)
    parser.add_argument("--secret-env", default="CHANNELS_HUB_SECRET")
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--allow-insecure-lan", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.max_pages < 1:
        raise ValueError("--max-pages must be at least 1")
    if args.page_size < 1:
        raise ValueError("--page-size must be at least 1")
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
    scheme = "wss" if ssl_context else "ws"
    print(
        json.dumps(
            {
                "event": "hub_listening",
                "url": f"{scheme}://{args.host}:{hub.listening_port}/ws/client",
                "worker_id": args.worker_id,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        capabilities = await hub.wait_for_worker(
            args.worker_id,
            timeout=args.wait_timeout,
            require_search_ready=True,
        )
        print(
            json.dumps(
                {"event": "worker_ready", "capabilities": redact_payload(asdict(capabilities))},
                ensure_ascii=False,
            ),
            flush=True,
        )
        result = await run_search_probe(
            hub,
            worker_id=args.worker_id,
            keyword=args.keyword,
            max_pages=args.max_pages,
            page_size=args.page_size,
            command_timeout=args.command_timeout,
        )
        print(json.dumps({"event": "probe_result", "result": result}, ensure_ascii=False), flush=True)
        return 0
    finally:
        await hub.stop()


def _server_ssl_context(cert_path: str | None, key_path: str | None) -> ssl.SSLContext | None:
    if bool(cert_path) != bool(key_path):
        raise ValueError("--tls-cert and --tls-key must be provided together")
    if not cert_path:
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    return context


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
