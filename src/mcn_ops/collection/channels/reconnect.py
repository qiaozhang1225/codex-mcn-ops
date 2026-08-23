from __future__ import annotations

import argparse
import asyncio
import json
import os

from .hub import ChannelsHub
from .probe import _is_loopback_host, _server_ssl_context, run_search_probe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a live worker restart against one Hub.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--keyword", default="AI")
    parser.add_argument("--wait-timeout", type=float, default=300.0)
    parser.add_argument("--command-timeout", type=float, default=180.0)
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
    try:
        await hub.wait_for_worker(
            args.worker_id,
            timeout=args.wait_timeout,
            require_search_ready=True,
        )
        print(json.dumps({"event": "worker_ready_before_restart"}), flush=True)
        await hub.wait_for_worker_disconnect(args.worker_id, timeout=args.wait_timeout)
        print(json.dumps({"event": "worker_disconnected"}), flush=True)
        await hub.wait_for_worker(
            args.worker_id,
            timeout=args.wait_timeout,
            require_search_ready=True,
        )
        result = await run_search_probe(
            hub,
            worker_id=args.worker_id,
            keyword=args.keyword,
            max_pages=1,
            command_timeout=args.command_timeout,
        )
        print(
            json.dumps(
                {
                    "event": "worker_reconnected_and_search_passed",
                    "keyword": result["keyword"],
                    "captured_pages": result["captured_pages"],
                    "captured_items": result["captured_items"],
                    "stop_reason": result["stop_reason"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    finally:
        await hub.stop()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
