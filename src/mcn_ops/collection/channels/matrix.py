from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import time
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import redact_payload, redact_text
from .hub import ChannelsHub
from .probe import _is_loopback_host, _server_ssl_context, run_search_probe


@dataclass(frozen=True)
class SearchCase:
    keyword: str
    max_pages: int


async def run_search_matrix(
    hub: ChannelsHub,
    *,
    worker_id: str,
    cases: list[SearchCase],
    repeat: int,
    page_size: int = 20,
    command_timeout: float = 180.0,
    interval: float = 3.0,
) -> dict[str, Any]:
    if not cases:
        raise ValueError("at least one search case is required")
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    if interval < 0:
        raise ValueError("interval cannot be negative")

    calls: list[dict[str, Any]] = []
    for repetition in range(1, repeat + 1):
        for case_index, case in enumerate(cases, start=1):
            started_at = int(time.time())
            call: dict[str, Any] = {
                "repetition": repetition,
                "case": case_index,
                "keyword": case.keyword,
                "requested_pages": case.max_pages,
                "started_at": started_at,
            }
            try:
                result = await run_search_probe(
                    hub,
                    worker_id=worker_id,
                    keyword=case.keyword,
                    max_pages=case.max_pages,
                    page_size=page_size,
                    command_timeout=command_timeout,
                )
                call.update(
                    {
                        "success": True,
                        "captured_pages": result["captured_pages"],
                        "captured_items": result["captured_items"],
                        "has_next": result["has_next"],
                        "source_exhausted": result["source_exhausted"],
                        "request_satisfied": result["request_satisfied"],
                        "stop_reason": result["stop_reason"],
                    }
                )
            except Exception as exc:  # preserve the matrix after an individual failure
                call.update(
                    {
                        "success": False,
                        "error_type": type(exc).__name__,
                        "error": redact_text(str(exc)),
                    }
                )
            call["finished_at"] = int(time.time())
            calls.append(call)
            if interval and len(calls) < len(cases) * repeat:
                await asyncio.sleep(interval)

    successful_calls = sum(1 for call in calls if call["success"])
    verified_second_page_keywords = sorted(
        {
            str(call["keyword"])
            for call in calls
            if call["success"] and int(call.get("captured_pages") or 0) >= 2
        }
    )
    success_rate = successful_calls / len(calls)
    return {
        "total_calls": len(calls),
        "successful_calls": successful_calls,
        "failed_calls": len(calls) - successful_calls,
        "success_rate": success_rate,
        "verified_second_page_keywords": verified_second_page_keywords,
        "acceptance": {
            "at_least_twenty_calls": len(calls) >= 20,
            "success_rate_at_least_95_percent": success_rate >= 0.95,
            "three_second_page_keywords": len(verified_second_page_keywords) >= 3,
        },
        "calls": calls,
    }


def parse_case(value: str) -> SearchCase:
    keyword, separator, pages_text = value.rpartition(":")
    if not separator:
        keyword = value
        pages_text = "1"
    keyword = keyword.strip()
    if not keyword:
        raise argparse.ArgumentTypeError("case keyword cannot be empty")
    try:
        max_pages = int(pages_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("case pages must be an integer") from exc
    if max_pages < 1:
        raise argparse.ArgumentTypeError("case pages must be at least 1")
    return SearchCase(keyword=keyword, max_pages=max_pages)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the WeChat Channels search acceptance matrix.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--case", type=parse_case, action="append", required=True, dest="cases")
    parser.add_argument("--repeat", type=int, default=4)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--wait-timeout", type=float, default=120.0)
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
    if args.page_size < 1:
        raise ValueError("--page-size must be at least 1")

    ssl_context: ssl.SSLContext | None = _server_ssl_context(args.tls_cert, args.tls_key)
    if not _is_loopback_host(args.host) and ssl_context is None and not args.allow_insecure_lan:
        raise ValueError(
            "non-loopback binding requires --tls-cert/--tls-key; "
            "use --allow-insecure-lan only for a controlled PoC"
        )

    hub = ChannelsHub(shared_secret=secret, allowed_worker_ids={args.worker_id})
    await hub.start(args.host, args.port, ssl_context=ssl_context)
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
        result = await run_search_matrix(
            hub,
            worker_id=args.worker_id,
            cases=args.cases,
            repeat=args.repeat,
            page_size=args.page_size,
            command_timeout=args.command_timeout,
            interval=args.interval,
        )
        print(json.dumps({"event": "matrix_result", "result": result}, ensure_ascii=False), flush=True)
        return 0 if all(result["acceptance"].values()) else 1
    finally:
        await hub.stop()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
