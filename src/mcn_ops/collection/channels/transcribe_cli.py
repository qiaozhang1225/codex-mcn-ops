from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ..douyin.factory import load_local_env
from ..transcription.aliyun import AliyunTranscriptionConfig, AliyunTranscriptionProvider
from ..transcription.cache import MemoryTranscriptionCache
from .media import acquire_channels_media
from .provider import ChannelsRemoteConfig, ChannelsRemoteProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve, download, decrypt, and transcribe one Channels search candidate."
    )
    parser.add_argument("--search-results", type=Path, required=True)
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument("--host", default=os.environ.get("CHANNELS_HUB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CHANNELS_HUB_PORT", "18081")))
    parser.add_argument("--worker-id", default=os.environ.get("CHANNELS_WORKER_ID", ""))
    parser.add_argument("--wait-timeout", type=float, default=300.0)
    parser.add_argument("--command-timeout", type=float, default=180.0)
    parser.add_argument("--download-timeout", type=float, default=180.0)
    parser.add_argument("--max-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--allow-insecure-lan", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_local_env(args.env_file)
    secret = os.environ.get("CHANNELS_HUB_SECRET", "").strip()
    if not secret:
        raise ValueError("CHANNELS_HUB_SECRET is required")
    candidate = find_candidate(args.search_results, args.work_id)
    provider = ChannelsRemoteProvider(
        ChannelsRemoteConfig(
            worker_id=args.worker_id,
            shared_secret=secret,
            host=args.host,
            port=args.port,
            wait_timeout=args.wait_timeout,
            command_timeout=args.command_timeout,
            tls_cert=args.tls_cert,
            tls_key=args.tls_key,
            allow_insecure_lan=args.allow_insecure_lan,
        )
    )
    lease = provider.resolve_media_lease(dict(candidate.get("detail_ref") or {}))
    media = acquire_channels_media(
        lease,
        download_limit_bytes=args.max_bytes,
        timeout_seconds=args.download_timeout,
    )
    try:
        transcriber = AliyunTranscriptionProvider(
            AliyunTranscriptionConfig.from_env(),
            cache=MemoryTranscriptionCache(),
        )
        result = transcriber.transcribe(
            str(media.path),
            source_package={
                key: value
                for key, value in candidate.items()
                if key not in {"detail_ref", "media_lease_available"}
            },
            use_cache=False,
        )
        normalized = result.get("normalized") if isinstance(result.get("normalized"), dict) else {}
        output = {
            "work_id": candidate.get("work_id"),
            "author_name": candidate.get("author_name"),
            "title": candidate.get("title"),
            "search_keyword": candidate.get("search_keyword"),
            "public_metrics": candidate.get("public_metrics") or {},
            "media": {
                "size_bytes": media.size_bytes,
                "advertised_size_bytes": media.advertised_size_bytes,
                "size_matches_detail": media.size_matches_detail,
                "sha256": media.sha256,
                "source_host": media.source_host,
                "decrypted_prefix_bytes": media.decrypted_prefix_bytes,
            },
            "transcription": {
                "provider": result.get("provider"),
                "model": normalized.get("model"),
                "language": normalized.get("language"),
                "text": normalized.get("text"),
                "usage": result.get("usage") or {},
            },
            "persisted_formal_material": False,
        }
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")), flush=True)
        return 0
    finally:
        media.cleanup()


def find_candidate(path: Path, work_id: str) -> dict[str, Any]:
    target = work_id.strip()
    if not target:
        raise ValueError("work_id is required")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        result = json.loads(line)
        normalized = result.get("normalized") if isinstance(result, dict) else {}
        packages = normalized.get("source_packages") if isinstance(normalized, dict) else []
        if not isinstance(packages, list):
            continue
        for package in packages:
            if isinstance(package, dict) and str(package.get("work_id") or "") == target:
                return dict(package)
    raise ValueError(f"work_id was not found in search results: {target}")


if __name__ == "__main__":
    raise SystemExit(main())
