from __future__ import annotations

import asyncio
import json
import time

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from mcn_ops.collection.channels import (
    ChannelsHub,
    ChannelsRemoteError,
    ChannelsTimeoutError,
    ChannelsWorkerDisconnected,
)
from mcn_ops.collection.channels.probe import run_search_probe
from mcn_ops.collection.channels.matrix import SearchCase, parse_case, run_search_matrix
from tests.helpers.channels_worker import MockChannelsWorker


def test_hub_correlates_gzip_response_and_search_pages() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            assert action == "search_videos"
            marker = str(data.get("next_marker") or "")
            if not marker:
                return {"list": [{"id": "video-1"}], "next_marker": "page-2", "has_more": True}
            return {"list": [{"id": "video-2"}], "next_marker": "", "has_more": False}

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
            gzip_messages=True,
        )
        await worker.start()
        try:
            capabilities = await hub.wait_for_worker("windows-01", timeout=1)
            assert capabilities.supports_search is True
            result = await run_search_probe(
                hub,
                worker_id="windows-01",
                keyword="AI",
                max_pages=3,
                command_timeout=1,
            )
            assert result["captured_pages"] == 2
            assert result["captured_items"] == 2
            assert result["source_exhausted"] is True
            assert result["stop_reason"] == "source_exhausted"
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_search_matrix_reports_acceptance_without_retaining_items() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            assert action == "search_videos"
            page = int(data["page"])
            return {
                "list": [{"id": f"work-{page}", "sessionBuffer": "private"}],
                "next_marker": "page-2" if page == 1 else "",
                "has_more": page == 1,
            }

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
        )
        await worker.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1, require_search_ready=True)
            result = await run_search_matrix(
                hub,
                worker_id="windows-01",
                cases=[
                    SearchCase("AI", 2),
                    SearchCase("职场", 2),
                    SearchCase("创业", 2),
                    SearchCase("读书", 1),
                    SearchCase("沟通", 1),
                ],
                repeat=4,
                command_timeout=1,
                interval=0,
            )
            assert result["total_calls"] == 20
            assert result["success_rate"] == 1
            assert result["acceptance"] == {
                "at_least_twenty_calls": True,
                "success_rate_at_least_95_percent": True,
                "three_second_page_keywords": True,
            }
            encoded = json.dumps(result)
            assert '"pages"' not in encoded
            assert "sessionBuffer" not in encoded
            assert "private" not in encoded
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_parse_search_matrix_case() -> None:
    assert parse_case("AI:2") == SearchCase(keyword="AI", max_pages=2)
    assert parse_case("职场") == SearchCase(keyword="职场", max_pages=1)


def test_hub_observes_worker_disconnect() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            return {}

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
        )
        await worker.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1)
            stop_task = asyncio.create_task(worker.stop())
            await hub.wait_for_worker_disconnect("windows-01", timeout=1)
            await stop_task
            assert hub.worker_capabilities("windows-01") is None
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_hub_rejects_wrong_secret() -> None:
    async def scenario() -> None:
        hub = ChannelsHub(shared_secret="correct", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        try:
            async with connect(
                f"ws://127.0.0.1:{hub.listening_port}/ws/client",
                additional_headers={
                    "X-Cloud-Secret": "wrong",
                    "X-Client-ID": "windows-01",
                },
            ) as connection:
                with pytest.raises(ConnectionClosed):
                    await connection.recv()
            with pytest.raises(ChannelsTimeoutError):
                await hub.wait_for_worker("windows-01", timeout=0.05)
        finally:
            await hub.stop()

    asyncio.run(scenario())


def test_hub_waits_for_search_ready_heartbeat() -> None:
    async def scenario() -> None:
        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        try:
            async with connect(
                f"ws://127.0.0.1:{hub.listening_port}/ws/client",
                additional_headers={
                    "X-Cloud-Secret": "secret",
                    "X-Client-ID": "windows-01",
                },
            ) as connection:
                waiter = asyncio.create_task(
                    hub.wait_for_worker(
                        "windows-01",
                        timeout=1,
                        require_search_ready=True,
                    )
                )

                def heartbeat(*, ready: bool) -> str:
                    return json.dumps(
                        {
                            "id": f"hb-{time.time_ns()}",
                            "type": "heartbeat",
                            "client_id": "windows-01",
                            "payload": {
                                "api_ready": ready,
                                "supports_search": ready,
                            },
                            "timestamp": int(time.time()),
                        }
                    )

                await connection.send(heartbeat(ready=False))
                await asyncio.sleep(0.02)
                assert waiter.done() is False

                await connection.send(heartbeat(ready=True))
                capabilities = await waiter
                assert capabilities.api_ready is True
                assert capabilities.supports_search is True
        finally:
            await hub.stop()

    asyncio.run(scenario())


def test_hub_rejects_unknown_worker_and_wrong_path() -> None:
    async def rejected(uri: str, worker_id: str) -> None:
        async with connect(
            uri,
            additional_headers={
                "X-Cloud-Secret": "secret",
                "X-Client-ID": worker_id,
            },
        ) as connection:
            with pytest.raises(ConnectionClosed):
                await connection.recv()

    async def scenario() -> None:
        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        try:
            await rejected(
                f"ws://127.0.0.1:{hub.listening_port}/ws/client",
                "unknown-worker",
            )
            await rejected(
                f"ws://127.0.0.1:{hub.listening_port}/wrong-path",
                "windows-01",
            )
        finally:
            await hub.stop()

    asyncio.run(scenario())


def test_hub_propagates_remote_error() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("wechat page unavailable")

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
        )
        await worker.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1)
            with pytest.raises(ChannelsRemoteError, match="wechat page unavailable"):
                await hub.call(
                    "windows-01",
                    "search_videos",
                    {"keyword": "AI"},
                    timeout=1,
                    require_search_ready=True,
                )
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_hub_redacts_credentials_from_remote_error() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            raise RuntimeError(
                "failed https://media.example/video.mp4?token=private&quality=high "
                "decodeKey=12345"
            )

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
        )
        await worker.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1)
            with pytest.raises(ChannelsRemoteError) as captured:
                await hub.call(
                    "windows-01",
                    "search_videos",
                    {"keyword": "AI"},
                    timeout=1,
                    require_search_ready=True,
                )
            message = str(captured.value)
            assert "private" not in message
            assert "12345" not in message
            assert "quality=high" in message
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_hub_times_out_when_worker_drops_response() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            await asyncio.sleep(1)
            return {}

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
        )
        await worker.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1)
            with pytest.raises(ChannelsTimeoutError):
                await hub.call(
                    "windows-01",
                    "search_videos",
                    {"keyword": "AI"},
                    timeout=0.05,
                    require_search_ready=True,
                )
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_hub_fails_pending_call_when_worker_disconnects() -> None:
    async def scenario() -> None:
        started = asyncio.Event()

        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            started.set()
            await asyncio.sleep(5)
            return {}

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
        )
        await worker.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1)
            call = asyncio.create_task(
                hub.call(
                    "windows-01",
                    "search_videos",
                    {"keyword": "AI"},
                    timeout=2,
                    require_search_ready=True,
                )
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            await worker.disconnect()
            with pytest.raises(ChannelsWorkerDisconnected):
                await call
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_hub_reconnect_replaces_stale_worker() -> None:
    async def scenario() -> None:
        first_started = asyncio.Event()

        async def slow_responder(action: str, data: dict[str, object]) -> dict[str, object]:
            first_started.set()
            await asyncio.sleep(5)
            return {}

        async def fast_responder(action: str, data: dict[str, object]) -> dict[str, object]:
            return {"list": [{"id": "replacement"}], "next_marker": "", "has_more": False}

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        uri = f"ws://127.0.0.1:{hub.listening_port}/ws/client"
        first = MockChannelsWorker(
            uri=uri,
            secret="secret",
            worker_id="windows-01",
            responder=slow_responder,
        )
        replacement = MockChannelsWorker(
            uri=uri,
            secret="secret",
            worker_id="windows-01",
            responder=fast_responder,
        )
        await first.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1)
            pending = asyncio.create_task(
                hub.call(
                    "windows-01",
                    "search_videos",
                    {"keyword": "AI"},
                    timeout=2,
                    require_search_ready=True,
                )
            )
            await asyncio.wait_for(first_started.wait(), timeout=1)
            await replacement.start()
            with pytest.raises(ChannelsWorkerDisconnected):
                await pending
            await hub.wait_for_worker("windows-01", timeout=1)
            result = await hub.call(
                "windows-01",
                "search_videos",
                {"keyword": "AI"},
                timeout=1,
                require_search_ready=True,
            )
            assert result["list"][0]["id"] == "replacement"
        finally:
            await first.stop()
            await replacement.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_search_probe_marks_bounded_sample_and_cursor_failure() -> None:
    async def bounded_scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            return {"list": [{"id": "video"}], "next_marker": "next", "has_more": True}

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
        )
        await worker.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1)
            result = await run_search_probe(
                hub,
                worker_id="windows-01",
                keyword="AI",
                max_pages=1,
                command_timeout=1,
            )
            assert result["stop_reason"] == "max_pages"
            assert result["source_exhausted"] is False
            assert result["request_satisfied"] is True
        finally:
            await worker.stop()
            await hub.stop()

    async def cursor_scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            return {"list": [], "next_marker": "", "has_more": True}

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
        )
        await worker.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1)
            result = await run_search_probe(
                hub,
                worker_id="windows-01",
                keyword="AI",
                max_pages=2,
                command_timeout=1,
            )
            assert result["stop_reason"] == "cursor_missing"
            assert result["source_exhausted"] is False
            assert result["request_satisfied"] is False
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(bounded_scenario())
    asyncio.run(cursor_scenario())


def test_call_without_worker_fails_immediately() -> None:
    async def scenario() -> None:
        hub = ChannelsHub(shared_secret="secret")
        with pytest.raises(ChannelsWorkerDisconnected):
            await hub.call("missing", "search_videos", {"keyword": "AI"})

    asyncio.run(scenario())


def test_search_probe_outputs_only_public_stable_item_evidence() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            assert action == "search_videos"
            return {
                "list": [
                    {
                        "id": "video-1",
                        "sessionBuffer": "private-session",
                        "cookie": "private-cookie",
                        "contact": {"username": "author-1", "nickname": "Author"},
                        "objectDesc": {
                            "description": "Public copy",
                            "media": [
                                {
                                    "url": "https://private.example/video?token=secret",
                                    "decodeKey": "private-key",
                                    "spec": [{"durationMs": 1234}],
                                }
                            ],
                        },
                        "createtime": 123,
                        "likeCount": 10,
                        "favCount": 9,
                        "commentCount": 8,
                        "forwardCount": 7,
                    }
                ],
                "has_more": False,
                "next_marker": "",
            }

        hub = ChannelsHub(shared_secret="secret", allowed_worker_ids={"windows-01"})
        await hub.start("127.0.0.1", 0)
        worker = MockChannelsWorker(
            uri=f"ws://127.0.0.1:{hub.listening_port}/ws/client",
            secret="secret",
            worker_id="windows-01",
            responder=responder,
        )
        await worker.start()
        try:
            await hub.wait_for_worker("windows-01", timeout=1, require_search_ready=True)
            result = await run_search_probe(
                hub,
                worker_id="windows-01",
                keyword="AI",
                max_pages=1,
                command_timeout=1,
            )
            item = result["pages"][0]["items"][0]
            assert item == {
                "work_id": "video-1",
                "author_id": "author-1",
                "author_name": "Author",
                "description": "Public copy",
                "created_at": 123,
                "duration_ms": 1234,
                "like_count": 10,
                "favorite_count": 9,
                "comment_count": 8,
                "share_count": 7,
            }
            assert "private" not in json.dumps(result)
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())
