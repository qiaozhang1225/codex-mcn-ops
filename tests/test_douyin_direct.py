from __future__ import annotations

import json
import random
from urllib.parse import parse_qs, urlsplit

import pytest

from mcn_ops.collection.douyin.direct import ABogusSigner, DirectDouyinClient, DirectDouyinConfig, HttpResponse
from mcn_ops.collection.douyin.direct.client import cookie_looks_authenticated, scrub_secrets
from mcn_ops.collection.douyin.errors import (
    ProviderAuthError,
    ProviderInputError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRiskControlError,
)


class StaticSigner:
    def sign(self, params, *, method="GET"):
        assert method == "GET"
        return "signed-token"


def test_cookie_authentication_requires_a_login_session_cookie() -> None:
    assert cookie_looks_authenticated("ttwid=anonymous; passport_csrf_token=value") is False
    assert cookie_looks_authenticated("ttwid=value; sessionid_ss=logged-in") is True


def response(payload, *, status=200, content_type="application/json", final_url="https://www.douyin.com/"):
    body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
    return HttpResponse(status=status, headers={"Content-Type": content_type}, body=body, final_url=final_url)


def test_a_bogus_signer_is_repeatable_with_injected_time_and_entropy() -> None:
    signer = ABogusSigner(
        "Test/1.0",
        clock_ms=lambda: 1_700_000_000_123,
        random_source=random.Random(7),
    )

    token = signer.sign({"aid": "6383", "aweme_id": "123"})

    assert token == (
        "YjR0BQh2kVyTvjyG56KLfY3q6AN3YgoI0SVkMf2fZx37qL39HMTa9eooIBGvXFEjwG/-"
        "Iebjy4hbO3xprQAjM36UHWwEUdQ2mgukKl5Q5xSSs1feeLbQrsJx-k4lFeep5JV3Ecvh"
        "qJKczbEk09Or4hqvPjoja3LkFk6FOoQO"
    )
    assert "=" not in token


def test_a_bogus_signer_resets_permutation_for_each_request() -> None:
    signer = ABogusSigner("Test/1.0", clock_ms=lambda: 1_700_000_000_123)
    signer.random_source = random.Random(9)
    first = signer.sign({"aid": "6383", "aweme_id": "123"})
    signer.random_source = random.Random(9)

    assert signer.sign({"aid": "6383", "aweme_id": "123"}) == first


def test_detail_builds_signed_request_and_normalizes_source_package() -> None:
    seen = {}

    def transport(method, url, headers, timeout):
        seen.update(method=method, url=url, headers=headers, timeout=timeout)
        return response(
            {
                "status_code": 0,
                "aweme_detail": {
                    "aweme_id": "7560000000000000001",
                    "desc": "八个旺自己的秘密 #女性成长",
                    "create_time": 1_700_000_000,
                    "duration": 61_000,
                    "author": {"nickname": "作者", "sec_uid": "sec_1", "unique_id": "author-1"},
                    "statistics": {"digg_count": 26144, "comment_count": 123},
                    "video": {
                        "cover": {"url_list": ["https://cdn.example/cover.jpg"]},
                        "play_addr": {"url_list": ["https://cdn.example/video.mp4"]},
                    },
                    "music": {"play_url": {"url_list": ["https://cdn.example/audio.mp3"]}},
                },
            }
        )

    client = DirectDouyinClient(transport=transport, signer=StaticSigner())
    result = client.call("detail_v4", body={"url": "https://www.douyin.com/video/7560000000000000001"})

    query = parse_qs(urlsplit(seen["url"]).query)
    assert query["aweme_id"] == ["7560000000000000001"]
    assert query["a_bogus"] == ["signed-token"]
    assert result["provider"] == "direct"
    assert result["method_key"] == "detail_v4"
    package = result["normalized"]["source_package"]
    assert package["clean_title"] == "八个旺自己的秘密"
    assert package["hashtags"] == ["女性成长"]
    assert package["author_sec_uid"] == "sec_1"
    assert package["duration_seconds"] == 61
    assert package["audio_url"] == "https://cdn.example/audio.mp3"


def test_user_post_retries_one_empty_page_and_preserves_max_cursor() -> None:
    calls = []
    pages = [
        {"status_code": 0, "aweme_list": [], "max_cursor": 0, "has_more": 1},
        {
            "status_code": 0,
            "aweme_list": [{"aweme_id": "756", "desc": "作品", "duration": 30000}],
            "max_cursor": "20",
            "has_more": 1,
        },
    ]

    def transport(method, url, headers, timeout):
        calls.append(parse_qs(urlsplit(url).query))
        return response(pages.pop(0))

    client = DirectDouyinClient(
        DirectDouyinConfig(cookie="sessionid=secret", empty_page_retries=1),
        transport=transport,
        signer=StaticSigner(),
        clock_ms=lambda: 123456,
    )
    result = client.call("user_post", params={"userId": "sec_1", "cursor": "0", "sortType": "1"})

    assert len(calls) == 2
    assert calls[0]["max_cursor"] == ["0"]
    assert calls[0]["sort_type"] == ["1"]
    assert calls[1]["_rticket"] == ["123456"]
    assert result["normalized"]["items"][0]["id"] == "756"
    assert result["paging"]["has_next"] is True
    assert result["paging"]["cursor"] == "20"


def test_search_and_user_info_normalization() -> None:
    payloads = {
        "/search/item/": {
            "status_code": 0,
            "data": [{"aweme_info": {"aweme_id": "100", "desc": "知识口播"}}],
            "cursor": 10,
            "has_more": 1,
            "search_id": "search-1",
        },
        "/discover/search/": {
            "status_code": 0,
            "data": [{"user_info": {"nickname": "思丞说", "sec_uid": "sec_2", "unique_id": "dy2"}}],
            "cursor": 10,
            "has_more": 0,
        },
        "/user/profile/other/": {
            "status_code": 0,
            "user": {"nickname": "思丞说", "sec_uid": "sec_2", "follower_count": 1234},
        },
    }

    def transport(method, url, headers, timeout):
        return response(next(value for key, value in payloads.items() if key in url))

    client = DirectDouyinClient(
        DirectDouyinConfig(cookie="sessionid=secret"), transport=transport, signer=StaticSigner()
    )
    videos = client.call("video_search", params={"keyword": "心理"})
    users = client.call("user_search", params={"keyword": "思丞说"})
    user = client.call("user_info", params={"userId": "sec_2"})

    assert videos["normalized"]["source_packages"][0]["work_id"] == "100"
    assert videos["paging"]["search_id"] == "search-1"
    assert users["normalized"]["items"][0]["douyin_id"] == "dy2"
    assert user["normalized"]["user"]["follower_count"] == 1234


def test_share_link_follows_redirect_and_extracts_work_id() -> None:
    def transport(method, url, headers, timeout):
        return response(b"", final_url="https://www.douyin.com/video/7560000000000000002")

    client = DirectDouyinClient(transport=transport, signer=StaticSigner())
    result = client.call("share_link", params={"url": "https://v.douyin.com/abc/"})

    assert result["normalized"]["work_id"] == "7560000000000000002"
    assert result["normalized"]["target"].endswith("/video/7560000000000000002")


def test_detail_resolves_short_link_before_requesting_json_detail() -> None:
    calls = []

    def transport(method, url, headers, timeout):
        calls.append(url)
        if url.startswith("https://v.douyin.com/"):
            return response(
                b"<html>normal landing page</html>",
                content_type="text/html",
                final_url="https://www.douyin.com/video/7560000000000000004",
            )
        return response({"status_code": 0, "aweme_detail": {"aweme_id": "7560000000000000004"}})

    client = DirectDouyinClient(transport=transport, signer=StaticSigner())
    result = client.call("detail_v4", body={"url": "https://v.douyin.com/short/"})

    assert len(calls) == 2
    assert result["normalized"]["source_package"]["work_id"] == "7560000000000000004"


def test_user_info_by_douyin_id_searches_then_loads_profile() -> None:
    calls = []

    def transport(method, url, headers, timeout):
        calls.append(url)
        if "/discover/search/" in url:
            return response(
                {
                    "status_code": 0,
                    "data": [{"user_info": {"nickname": "作者", "sec_uid": "sec_exact", "unique_id": "dy-exact"}}],
                }
            )
        return response({"status_code": 0, "user": {"nickname": "作者", "sec_uid": "sec_exact"}})

    client = DirectDouyinClient(
        DirectDouyinConfig(cookie="sessionid=fake"), transport=transport, signer=StaticSigner()
    )
    result = client.call("user_info_dy_id", params={"userCode": "dy-exact"})

    assert len(calls) == 2
    assert result["method_key"] == "user_info_dy_id"
    assert result["normalized"]["user"]["sec_uid"] == "sec_exact"


def test_user_info_by_douyin_id_rejects_inexact_search_result() -> None:
    def transport(method, url, headers, timeout):
        return response(
            {
                "status_code": 0,
                "data": [{"user_info": {"nickname": "其他人", "sec_uid": "wrong", "unique_id": "different-id"}}],
            }
        )

    client = DirectDouyinClient(
        DirectDouyinConfig(cookie="sessionid=fake"), transport=transport, signer=StaticSigner()
    )

    with pytest.raises(ProviderResponseError, match="was not found"):
        client.call("user_info_dy_id", params={"userCode": "target-id"})


def test_invalid_detail_input_is_classified_as_non_fallback_input_error() -> None:
    client = DirectDouyinClient(transport=lambda *args: response({}), signer=StaticSigner())

    with pytest.raises(ProviderInputError) as caught:
        client.call("detail_v4", body={"url": "not-a-douyin-url"})

    assert caught.value.fallback_allowed is False


@pytest.mark.parametrize(
    ("http_response", "error_type"),
    [
        (response({}, status=429), ProviderRateLimitError),
        (response(b"<html>captcha verify</html>", content_type="text/html"), ProviderRiskControlError),
        (response(b"<html>maintenance</html>", content_type="text/html"), ProviderResponseError),
    ],
)
def test_transport_response_classification(http_response, error_type) -> None:
    client = DirectDouyinClient(transport=lambda *args: http_response, signer=StaticSigner())
    with pytest.raises(error_type):
        client.call("detail", params={"id": "7560000000000000003"}, use_cache=False)


def test_cookie_is_required_for_account_scoped_endpoints() -> None:
    client = DirectDouyinClient(transport=lambda *args: response({}), signer=StaticSigner())
    with pytest.raises(ProviderAuthError, match="DOUYIN_COOKIE"):
        client.call("user_post", params={"userId": "sec_1"})


def test_scrub_secrets_is_recursive_and_does_not_mutate_input() -> None:
    source = {
        "Cookie": "sessionid=secret",
        "nested": {"authorization": "Bearer secret", "url": "https://x.test/?a_bogus=abc&ok=1"},
        "items": [{"msToken": "token", "title": "safe"}],
    }

    scrubbed = scrub_secrets(source)

    assert scrubbed["Cookie"] == "<redacted>"
    assert scrubbed["nested"]["authorization"] == "<redacted>"
    assert "abc" not in scrubbed["nested"]["url"]
    assert scrubbed["items"][0] == {"msToken": "<redacted>", "title": "safe"}
    assert source["Cookie"] == "sessionid=secret"
