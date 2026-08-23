from __future__ import annotations

import argparse
import json
import os

from .provider import ChannelsRemoteConfig, ChannelsRemoteProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search WeChat Channels through the LAN worker.")
    parser.add_argument("--keyword", action="append", required=True)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--host", default=os.environ.get("CHANNELS_HUB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CHANNELS_HUB_PORT", "18081")))
    parser.add_argument("--worker-id", default=os.environ.get("CHANNELS_WORKER_ID", ""))
    parser.add_argument("--wait-timeout", type=float, default=300.0)
    parser.add_argument("--command-timeout", type=float, default=180.0)
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--allow-insecure-lan", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    secret = os.environ.get("CHANNELS_HUB_SECRET", "").strip()
    if not secret:
        raise ValueError("CHANNELS_HUB_SECRET is required")
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
    results = provider.search_many(
        args.keyword,
        max_pages=args.max_pages,
        page_size=args.page_size,
    )
    for result in results:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
