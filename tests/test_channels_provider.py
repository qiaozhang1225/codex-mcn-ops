from __future__ import annotations

import asyncio
import json

import pytest

from mcn_ops.collection.channels.hub import ChannelsHub
from mcn_ops.collection.channels.provider import (
    ChannelsRemoteConfig,
    ChannelsRemoteProvider,
    _author_feed_with_hub,
    _search_with_hub,
    _share_url_with_hub,
    _source_package,
)
from mcn_ops.collection.channels.registry import build_channels_registry
from mcn_ops.collection.douyin.errors import (
    ProviderConfigError,
    ProviderInputError,
    ProviderResponseError,
)
from tests.helpers.channels_worker import MockChannelsWorker


def test_search_provider_normalizes_and_never_returns_media_credentials() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            assert action == "search_videos"
            page = int(data["page"])
            return {
                "list": [
                    {
                        "object": {
                            "id": f"work-{page}",
                            "objectNonceId": f"nonce-{page}",
                            "createtime": 123,
                            "likeCount": 1000 * page,
                            "favCount": 20,
                            "commentCount": 30,
                            "forwardCount": 40,
                            "sessionBuffer": "private-session",
                            "contact": {"username": "author-1", "nickname": "心理老师"},
                            "objectDesc": {
                                "description": (
                                    '<em class="highlight">青春期孩子</em>为什么不愿沟通'
                                ),
                                "media": [
                                    {
                                        "url": "https://media.example/video.mp4?",
                                        "urlToken": "token=private&sign=secret",
                                        "decodeKey": "123456",
                                        "videoPlayLen": 12,
                                    }
                                ],
                            },
                        }
                    }
                ],
                "next_marker": "next" if page == 1 else "",
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
            result = await _search_with_hub(
                hub,
                worker_id="windows-01",
                keyword="青春期孩子",
                max_pages=2,
                page_size=20,
                command_timeout=1,
            )
            packages = result["normalized"]["source_packages"]
            assert [package["work_id"] for package in packages] == ["work-1", "work-2"]
            assert packages[0]["duration_ms"] == 12000
            assert packages[0]["platform_caption"] == "青春期孩子为什么不愿沟通"
            assert packages[0]["detail_ref"] == {
                "object_id": "work-1",
                "object_nonce_id": "nonce-1",
                "encrypted_object_id": "",
            }
            assert result["paging"]["source_exhausted"] is True
            encoded = json.dumps(result)
            for forbidden in ("private-session", "token=private", "sign=secret", "123456"):
                assert forbidden not in encoded
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_source_package_uses_platform_neutral_identity_and_metrics() -> None:
    package = _source_package(
        {
            "id": "work-1",
            "contact": {"username": "wx-author", "nickname": "作者"},
            "objectDesc": {"description": "标题", "media": [{"durationMs": 4321}]},
            "likeCount": 90,
        }
    )

    assert package["source_platform"] == "wechat_channels"
    assert package["platform_author_id"] == "wx-author"
    assert package["author_sec_uid"] == "wx-author"
    assert package["duration_ms"] == 4321
    assert package["public_metrics"]["digg_count"] == 90


def test_share_url_provider_requires_matching_public_weixin_link() -> None:
    async def scenario() -> None:
        calls: list[dict[str, object]] = []

        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            calls.append({"action": action, "data": data})
            return {
                "errCode": 0,
                "errMsg": "ok",
                "data": {
                    "feedH5Url": "https://weixin.qq.com/sph/Abc_123-Z",
                    "urlList": [
                        {
                            "objectId": "work-1",
                            "feedH5Url": "https://weixin.qq.com/sph/Abc_123-Z",
                        }
                    ],
                },
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
            await hub.wait_for_worker(
                "windows-01", timeout=1, required_capability="profile"
            )
            url = await _share_url_with_hub(
                hub,
                worker_id="windows-01",
                work_id="work-1",
                command_timeout=1,
            )
            assert url == "https://weixin.qq.com/sph/Abc_123-Z"
            assert calls == [
                {
                    "action": "api_call",
                    "data": {
                        "key": "key:channels:feed_share_url",
                        "body": {"object_id": "work-1"},
                    },
                }
            ]
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "response",
    [
        {
            "errCode": 0,
            "data": {"feedH5Url": "https://finder.video.qq.com/private"},
        },
        {
            "errCode": 0,
            "data": {
                "urlList": [
                    {
                        "objectId": "other-work",
                        "feedH5Url": "https://weixin.qq.com/sph/Other123",
                    }
                ]
            },
        },
    ],
)
def test_share_url_provider_rejects_private_or_mismatched_links(
    response: dict[str, object],
) -> None:
    async def scenario() -> None:
        async def responder(_action: str, _data: dict[str, object]) -> dict[str, object]:
            return response

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
            await hub.wait_for_worker(
                "windows-01", timeout=1, required_capability="profile"
            )
            with pytest.raises(ProviderResponseError, match="verified"):
                await _share_url_with_hub(
                    hub,
                    worker_id="windows-01",
                    work_id="work-1",
                    command_timeout=1,
                )
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_provider_fails_closed_for_insecure_lan_and_missing_keyword() -> None:
    with pytest.raises(ProviderConfigError, match="requires TLS"):
        ChannelsRemoteProvider(
            ChannelsRemoteConfig(
                worker_id="windows-01",
                shared_secret="secret",
                host="0.0.0.0",
            )
        )

    provider = ChannelsRemoteProvider(
        ChannelsRemoteConfig(worker_id="windows-01", shared_secret="secret")
    )
    with pytest.raises(ProviderInputError, match="requires keyword"):
        provider.call("wechat_channels_search", params={"keyword": ""})


def test_search_provider_resumes_from_cursor_and_returns_next_cursor() -> None:
    async def scenario() -> None:
        calls: list[dict[str, object]] = []

        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            assert action == "search_videos"
            calls.append(data)
            return {
                "list": [{"object": {"id": "work-2", "objectDesc": {}}}],
                "next_marker": "page-3",
                "has_more": True,
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
            await hub.wait_for_worker(
                "windows-01", timeout=1, required_capability="search"
            )
            result = await _search_with_hub(
                hub,
                worker_id="windows-01",
                keyword="青春期孩子",
                cursor="page-2",
                max_pages=1,
                page_size=20,
                command_timeout=1,
            )
            assert calls[0]["next_marker"] == "page-2"
            assert result["paging"]["next_cursor"] == "page-3"
            assert result["paging"]["stop_reason"] == "max_pages"
            assert result["paging"]["raw"]["resumed_from_cursor"] is True
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("returned_marker", "expected_reason"),
    [("", "cursor_missing"), ("page-2", "cursor_cycle")],
)
def test_search_provider_fails_closed_for_invalid_cursor_progression(
    returned_marker: str,
    expected_reason: str,
) -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            return {"list": [], "next_marker": returned_marker, "has_more": True}

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
            await hub.wait_for_worker(
                "windows-01", timeout=1, required_capability="search"
            )
            result = await _search_with_hub(
                hub,
                worker_id="windows-01",
                keyword="青春期孩子",
                cursor="page-2",
                max_pages=1,
                page_size=20,
                command_timeout=1,
            )
            assert result["paging"]["stop_reason"] == expected_reason
            assert result["paging"]["request_satisfied"] is False
            assert result["paging"]["next_cursor"] is None
            assert result["paging"]["source_exhausted"] is False
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_author_feed_uses_documented_poc_shape_without_claiming_unverified_exhaustion() -> None:
    async def scenario() -> None:
        calls: list[dict[str, object]] = []

        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            calls.append({"action": action, "data": data})
            return {
                "data": {
                    "object": [
                        {
                            "id": "author-work-1",
                            "contact": {
                                "username": "finder-author-1",
                                "nickname": "心理老师",
                            },
                            "objectDesc": {"description": "亲子沟通"},
                            "likeCount": 2500,
                        }
                    ],
                    "lastBuffer": "author-page-2",
                }
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
            await hub.wait_for_worker(
                "windows-01", timeout=1, required_capability="feed"
            )
            result = await _author_feed_with_hub(
                hub,
                worker_id="windows-01",
                platform_author_id="finder-author-1",
                max_pages=1,
                page_size=20,
                command_timeout=1,
            )
            assert calls[0] == {
                "action": "api_call",
                "data": {
                    "key": "key:channels:feed_list",
                    "body": {
                        "username": "finder-author-1",
                        "next_marker": "",
                        "page": 1,
                        "page_size": 20,
                    },
                },
            }
            assert result["normalized"]["source_packages"][0]["work_id"] == "author-work-1"
            assert result["normalized"]["response_contract"] == "poc_fixture_only"
            assert result["normalized"]["capability_gate"] == {
                "required_worker_capability": "feed",
                "live_poc_verified": False,
                "production_ready": False,
            }
            assert result["paging"]["next_cursor"] == "author-page-2"
            assert result["paging"]["source_exhausted"] is False
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_author_feed_rejects_remote_business_error_before_parsing_items() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            return {
                "errCode": 1001,
                "errMsg": "finderUserPage unavailable",
                "data": {"object": []},
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
            await hub.wait_for_worker(
                "windows-01", timeout=1, required_capability="feed"
            )
            with pytest.raises(ProviderResponseError, match="finderUserPage unavailable"):
                await _author_feed_with_hub(
                    hub,
                    worker_id="windows-01",
                    platform_author_id="finder-author-1",
                    max_pages=1,
                    page_size=20,
                    command_timeout=1,
                )
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_author_feed_requires_verified_terminal_signal_before_source_exhaustion() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            return {"data": {"object": [], "lastBuffer": ""}}

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
            await hub.wait_for_worker(
                "windows-01", timeout=1, required_capability="feed"
            )
            result = await _author_feed_with_hub(
                hub,
                worker_id="windows-01",
                platform_author_id="finder-author-1",
                max_pages=1,
                page_size=20,
                command_timeout=1,
            )
            assert result["paging"]["stop_reason"] == "pagination_unverified"
            assert result["paging"]["request_satisfied"] is False
            assert result["paging"]["source_exhausted"] is False
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_author_feed_documented_terminal_flag_remains_live_poc_gated() -> None:
    async def scenario() -> None:
        async def responder(action: str, data: dict[str, object]) -> dict[str, object]:
            return {"data": {"object": [], "lastBuffer": "", "continueFlag": 0}}

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
            await hub.wait_for_worker(
                "windows-01", timeout=1, required_capability="feed"
            )
            result = await _author_feed_with_hub(
                hub,
                worker_id="windows-01",
                platform_author_id="finder-author-1",
                max_pages=1,
                page_size=20,
                command_timeout=1,
            )
            assert result["paging"]["stop_reason"] == "source_exhausted_unverified"
            assert result["paging"]["request_satisfied"] is False
            assert result["paging"]["source_exhausted"] is False
        finally:
            await worker.stop()
            await hub.stop()

    asyncio.run(scenario())


def test_channels_registry_forwards_search_and_author_cursors() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def call(
            self,
            method_key: str,
            params: dict[str, object] | None = None,
            body: dict[str, object] | None = None,
            use_cache: bool = True,
        ) -> dict[str, object]:
            del body, use_cache
            self.calls.append((method_key, dict(params or {})))
            return {"ok": True}

    class UnusedTranscriber:
        pass

    provider = FakeProvider()
    registry = build_channels_registry(
        provider,  # type: ignore[arg-type]
        transcription_provider=UnusedTranscriber(),  # type: ignore[arg-type]
    )

    registry.run(
        "channels_search_videos",
        {"keyword": "青春期孩子", "cursor": "search-page-2"},
    )
    registry.run(
        "channels_list_author_works",
        {
            "platform_author_id": "finder-author-1",
            "cursor": "author-page-2",
        },
    )

    assert provider.calls == [
        (
            "wechat_channels_search",
            {
                "keyword": "青春期孩子",
                "cursor": "search-page-2",
                "max_pages": 1,
                "page_size": 20,
            },
        ),
        (
            "wechat_channels_author_feed",
            {
                "platform_author_id": "finder-author-1",
                "cursor": "author-page-2",
                "max_pages": 1,
                "page_size": 20,
            },
        ),
    ]
