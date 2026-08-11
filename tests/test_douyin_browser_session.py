from __future__ import annotations

import json

import pytest

from mcn_ops.collection.douyin.browser_session import (
    BrowserCommandResult,
    BrowserNavigation,
    BrowserSessionConfig,
    BrowserSessionDouyinClient,
    _browser_script,
)
from mcn_ops.collection.douyin.direct import DirectDouyinClient
from mcn_ops.collection.douyin.errors import ProviderInputError, ProviderUnavailableError


def _payload() -> dict:
    return {
        "status_code": 0,
        "aweme_detail": {
            "aweme_id": "7663071007338499362",
            "desc": "测试文案 #测试",
            "author": {"nickname": "作者"},
            "video": {"play_addr": {"url_list": ["https://media.example/video.mp4"]}},
            "music": {"play_url": {"url_list": ["https://media.example/audio.mp3"]}},
            "authentication_token": "must-not-leak",
        },
    }


def test_browser_session_detail_normalizes_real_response_shape() -> None:
    calls = []

    def runner(navigation, config):
        calls.append(navigation)
        return BrowserCommandResult(0, json.dumps(_payload(), ensure_ascii=False), "")

    provider = BrowserSessionDouyinClient(DirectDouyinClient(), runner=runner)
    result = provider.call(
        "detail_v4",
        body={"url": "https://www.douyin.com/video/7663071007338499362"},
    )

    assert calls == [
        BrowserNavigation(
            target="https://www.douyin.com/video/7663071007338499362",
            response_path="/aweme/v1/web/aweme/detail/",
        )
    ]
    assert result["normalized"]["video"]["caption"] == "测试文案 #测试"
    assert result["normalized"]["source_package"]["audio_url"] == "https://media.example/audio.mp3"
    assert result["raw"]["aweme_detail"]["authentication_token"] == "<redacted>"


def test_browser_session_detail_cache_avoids_second_browser_call() -> None:
    count = 0

    def runner(navigation, config):
        nonlocal count
        count += 1
        return BrowserCommandResult(0, json.dumps(_payload()), "")

    provider = BrowserSessionDouyinClient(DirectDouyinClient(), runner=runner)
    provider.call("detail_v4", body={"url": "7663071007338499362"})
    cached = provider.call("detail_v4", body={"url": "7663071007338499362"})

    assert count == 1
    assert cached["cache_hit"] is True


def test_browser_session_rejects_non_douyin_url_before_runner() -> None:
    provider = BrowserSessionDouyinClient(
        DirectDouyinClient(),
        runner=lambda navigation, config: pytest.fail("runner must not be called"),
    )

    with pytest.raises(ProviderInputError):
        provider.call("detail_v4", body={"url": "https://example.com/video/123"})


def test_browser_session_maps_command_failure() -> None:
    provider = BrowserSessionDouyinClient(
        DirectDouyinClient(),
        runner=lambda navigation, config: BrowserCommandResult(1, "", "connection failed"),
    )

    with pytest.raises(ProviderUnavailableError, match="browser request failed"):
        provider.call("detail_v4", body={"url": "7663071007338499362"})


def test_browser_session_accepts_large_payload_from_stderr() -> None:
    provider = BrowserSessionDouyinClient(
        DirectDouyinClient(),
        runner=lambda navigation, config: BrowserCommandResult(
            0,
            "",
            json.dumps(_payload(), ensure_ascii=False),
        ),
    )

    result = provider.call("detail_v4", body={"url": "7663071007338499362"})

    assert result["normalized"]["video"]["id"] == "7663071007338499362"


def test_browser_video_search_retries_an_empty_first_response() -> None:
    responses = [
        {"status_code": 0, "data": [], "cursor": 20, "has_more": 0},
        {
            "status_code": 0,
            "data": [
                {
                    "aweme_info": {
                        "aweme_id": "1234567890123456789",
                        "desc": "亲子关系测试",
                        "author": {"nickname": "测试作者"},
                    }
                }
            ],
            "cursor": 20,
            "has_more": 1,
        },
    ]
    calls = []

    def runner(navigation, config):
        calls.append(navigation)
        return BrowserCommandResult(0, json.dumps(responses.pop(0), ensure_ascii=False), "")

    provider = BrowserSessionDouyinClient(DirectDouyinClient(), runner=runner)
    result = provider.call("video_search", params={"keyword": "亲子关系", "offset": "0"})

    assert len(calls) == 2
    assert calls[0].response_path == "/aweme/v1/web/search/item/"
    assert "%E4%BA%B2%E5%AD%90%E5%85%B3%E7%B3%BB" in calls[0].target
    assert result["normalized"]["items"][0]["id"] == "1234567890123456789"
    assert result["paging"]["has_next"] is True


def test_browser_video_search_rejects_unimplemented_pagination() -> None:
    provider = BrowserSessionDouyinClient(
        DirectDouyinClient(),
        runner=lambda navigation, config: pytest.fail("runner must not be called"),
    )

    with pytest.raises(ProviderInputError, match="first result page only"):
        provider.call("video_search", params={"keyword": "亲子关系", "offset": "20"})


def test_browser_video_search_aggregates_scroll_pages_and_deduplicates() -> None:
    envelope = {
        "__ego_browser__": True,
        "payloads": [
            {
                "status_code": 0,
                "data": [
                    {"aweme_info": {"aweme_id": "1111111111111111111", "desc": "第一页"}},
                ],
                "cursor": 20,
                "has_more": 1,
                "search_id": "search-1",
            },
            {
                "status_code": 0,
                "data": [
                    {"aweme_info": {"aweme_id": "1111111111111111111", "desc": "重复"}},
                    {"aweme_info": {"aweme_id": "2222222222222222222", "desc": "第二页"}},
                ],
                "cursor": 40,
                "has_more": 1,
                "search_id": "search-1",
            },
        ],
        "browser_meta": {
            "browser_aggregated": True,
            "pages_captured": 2,
            "unique_items": 2,
            "max_pages": 2,
            "max_items": 0,
            "stop_reason": "max_pages",
        },
    }
    calls = []

    def runner(navigation, config):
        calls.append(navigation)
        return BrowserCommandResult(0, json.dumps(envelope, ensure_ascii=False), "")

    provider = BrowserSessionDouyinClient(DirectDouyinClient(), runner=runner)
    result = provider.call(
        "video_search",
        params={"keyword": "亲子关系", "offset": "0", "max_pages": 2},
    )

    assert calls[0].max_pages == 2
    assert [item["id"] for item in result["normalized"]["items"]] == [
        "1111111111111111111",
        "2222222222222222222",
    ]
    assert result["paging"]["cursor"] == "40"
    assert result["paging"]["raw"]["browser_aggregated"] is True
    assert result["paging"]["raw"]["pages_captured"] == 2


def test_browser_video_search_strictly_caps_normalized_items() -> None:
    envelope = {
        "__ego_browser__": True,
        "payloads": [
            {
                "status_code": 0,
                "data": [
                    {"aweme_info": {"aweme_id": "1111111111111111111"}},
                    {"aweme_info": {"aweme_id": "2222222222222222222"}},
                ],
                "cursor": 20,
                "has_more": 1,
            }
        ],
        "browser_meta": {
            "browser_aggregated": True,
            "pages_captured": 1,
            "unique_items": 2,
            "max_pages": 1,
            "max_items": 1,
            "stop_reason": "max_items",
        },
    }
    provider = BrowserSessionDouyinClient(
        DirectDouyinClient(),
        runner=lambda navigation, config: BrowserCommandResult(0, json.dumps(envelope), ""),
    )

    result = provider.call(
        "video_search",
        params={"keyword": "亲子关系", "max_pages": 1, "max_items": 1},
    )

    assert [item["id"] for item in result["normalized"]["items"]] == [
        "1111111111111111111"
    ]
    assert len(result["normalized"]["source_packages"]) == 1


def test_browser_user_posts_uses_profile_scroll_and_normalizes_all_items() -> None:
    envelope = {
        "__ego_browser__": True,
        "payloads": [
            {
                "status_code": 0,
                "aweme_list": [
                    {
                        "aweme_id": "3333333333333333333",
                        "desc": "作者作品",
                        "author": {"nickname": "目标作者", "sec_uid": "MS4.test"},
                    }
                ],
                "max_cursor": 10,
                "has_more": 0,
            }
        ],
        "browser_meta": {
            "browser_aggregated": True,
            "pages_captured": 1,
            "unique_items": 1,
            "max_pages": 20,
            "max_items": 0,
            "stop_reason": "no_next_page",
        },
    }
    calls = []

    def runner(navigation, config):
        calls.append(navigation)
        return BrowserCommandResult(0, json.dumps(envelope, ensure_ascii=False), "")

    provider = BrowserSessionDouyinClient(DirectDouyinClient(), runner=runner)
    result = provider.call(
        "user_post",
        params={"userId": "MS4.test", "cursor": "0", "max_pages": 20},
    )

    assert calls == [
        BrowserNavigation(
            target="https://www.douyin.com/user/MS4.test",
            response_path="/aweme/v1/web/aweme/post/",
            max_pages=20,
            max_items=0,
            require_exhaustion=False,
        )
    ]
    assert result["normalized"]["items"][0]["author_name"] == "目标作者"
    assert result["normalized"]["items"][0]["id"] == "3333333333333333333"
    assert result["paging"]["has_next"] is False


def test_browser_multi_page_request_fails_closed_when_only_first_page_was_observed() -> None:
    envelope = {
        "__ego_browser__": True,
        "payloads": [
            {
                "status_code": 0,
                "data": [{"aweme_info": {"aweme_id": "1111111111111111111"}}],
                "cursor": 20,
                "has_more": 1,
            }
        ],
        "browser_meta": {
            "browser_aggregated": True,
            "pages_captured": 1,
            "unique_items": 1,
            "max_pages": 3,
            "max_items": 0,
            "stop_reason": "idle_scroll_limit",
        },
    }
    provider = BrowserSessionDouyinClient(
        DirectDouyinClient(),
        runner=lambda navigation, config: BrowserCommandResult(0, json.dumps(envelope), ""),
    )

    with pytest.raises(ProviderUnavailableError, match="did not expose the requested next page"):
        provider.call("video_search", params={"keyword": "亲子关系", "max_pages": 3})


def test_browser_script_uses_json_escaped_target_and_bounded_wait() -> None:
    script = _browser_script(
        BrowserNavigation(
            target='https://v.douyin.com/a"b',
            response_path="/aweme/v1/web/aweme/detail/",
        ),
        BrowserSessionConfig(wait_seconds=100),
    )

    assert 'https://v.douyin.com/a\\"b' in script
    assert "await wait(30.0)" in script
    assert "Network.getResponseBody" in script
    assert "await window.fetch" in script
    assert "requestUrl.searchParams.set('offset'" in script
    assert "Page.addScriptToEvaluateOnNewDocument" in script
    assert "parsed.searchParams.set('max_cursor', wanted)" in script
    assert "const seenPages = new Set()" in script
    assert "if (seenPages.has(pageKey)) return false" in script
    assert "browser_aggregated" in script
    assert "/aweme/v1/web/aweme/detail/" in script
    assert "DOUYIN_COOKIE" not in script
    assert "Network.setCookies" not in script
    assert "finally" in script
    assert "await completeTaskSpace(task.id, { keep: false })" in script
    assert "task space not found" in script
    assert "handOffTaskSpace(task.id)" in script
