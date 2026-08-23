from __future__ import annotations

import asyncio
import json

import pytest

from mcn_ops.collection.channels.hub import ChannelsHub
from mcn_ops.collection.channels.provider import (
    ChannelsRemoteConfig,
    ChannelsRemoteProvider,
    _search_with_hub,
    _source_package,
)
from mcn_ops.collection.douyin.errors import ProviderConfigError, ProviderInputError
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
