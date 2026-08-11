from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from ..contracts import ProviderResult, build_provider_result, empty_paging, normalize_paging
from ..errors import (
    ProviderAuthError,
    ProviderInputError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRiskControlError,
    ProviderUnavailableError,
)
from . import endpoints
from .signer import ABogusSigner, Signer


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

AUTHENTICATED_COOKIE_NAMES = {
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "uid_tt",
    "uid_tt_ss",
}


def cookie_looks_authenticated(cookie: str | None) -> bool:
    names = {
        part.split("=", 1)[0].strip().lower()
        for part in str(cookie or "").split(";")
        if "=" in part
    }
    return bool(names & AUTHENTICATED_COOKIE_NAMES)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


Transport = Callable[[str, str, Mapping[str, str], float], HttpResponse]


@dataclass
class DirectDouyinConfig:
    cookie: str | None = None
    user_agent: str = DEFAULT_USER_AGENT
    timeout_seconds: float = 30.0
    empty_page_retries: int = 1
    count: int = 18


class DirectDouyinClient:
    provider_name = "direct"

    def __init__(
        self,
        config: DirectDouyinConfig | None = None,
        *,
        transport: Transport | None = None,
        signer: Signer | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self.config = config or DirectDouyinConfig()
        self.transport = transport or _urllib_transport
        self.signer = signer or ABogusSigner(self.config.user_agent)
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._cache: dict[str, ProviderResult] = {}

    def call(
        self,
        method_key: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ProviderResult:
        params = dict(params or {})
        body = dict(body or {})
        canonical = _canonical_method(method_key)
        if canonical == "share_link":
            return self._resolve_share_link(method_key, params, body)
        if canonical == "user_info_dy_id":
            return self._user_info_by_douyin_id(method_key, params, body, use_cache=use_cache)
        if canonical not in endpoints.METHOD_ENDPOINTS:
            raise ProviderInputError(f"unsupported direct Douyin method: {method_key}")

        supplied = {**params, **body}
        if canonical == "detail" and not _work_id(
            str(supplied.get("url") or supplied.get("aweme_id") or supplied.get("id") or "")
        ):
            resolved = self._resolve_share_link(method_key, params, body)
            params["id"] = resolved["normalized"]["work_id"]

        request_params = self._request_params(canonical, params, body)
        cache_key = json.dumps([canonical, request_params], ensure_ascii=False, sort_keys=True)
        if use_cache and cache_key in self._cache:
            cached = dict(self._cache[cache_key])
            cached["cache_hit"] = True
            return cached  # type: ignore[return-value]

        attempts = self.config.empty_page_retries + 1 if canonical == "user_post" else 1
        raw: dict[str, Any] | None = None
        endpoint = endpoints.METHOD_ENDPOINTS[canonical]
        for attempt in range(attempts):
            attempt_params = dict(request_params)
            if attempt:
                attempt_params["_rticket"] = str(self.clock_ms())
            raw = self._get_json(endpoint, attempt_params)
            if canonical != "user_post" or _video_items(raw) or attempt + 1 >= attempts:
                break
        assert raw is not None
        normalized, paging = _normalize(canonical, raw)
        result = build_provider_result(
            provider=self.provider_name,
            method_key=method_key,
            endpoint=endpoint,
            normalized=normalized,
            raw=scrub_secrets(raw),
            paging=paging,
        )
        if use_cache:
            self._cache[cache_key] = result
        return result

    def _request_params(
        self,
        method_key: str,
        params: dict[str, Any],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        supplied = {**params, **body}
        base: dict[str, Any] = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "pc_client_type": "1",
            "version_code": "190500",
            "version_name": "19.5.0",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_online": "true",
            "engine_name": "Blink",
            "os_name": "Windows",
            "os_version": "10",
            "platform": "PC",
            "screen_width": "1920",
            "screen_height": "1080",
            "msToken": "",
        }
        if method_key in {"detail", "detail_v3", "detail_v4"}:
            work_id = supplied.get("aweme_id") or supplied.get("id") or _work_id(str(supplied.get("url") or ""))
            if not work_id:
                raise ProviderInputError("detail requires a Douyin share URL or aweme_id")
            base["aweme_id"] = str(work_id)
        elif method_key == "user_post":
            self._require_cookie(method_key)
            user_id = supplied.get("sec_user_id") or supplied.get("userId") or supplied.get("user_id")
            if not user_id:
                raise ProviderInputError("user_post requires sec_user_id")
            base.update(
                sec_user_id=str(user_id),
                max_cursor=str(supplied.get("max_cursor") or supplied.get("cursor") or "0"),
                count=str(supplied.get("count") or self.config.count),
                locate_query="false",
                publish_video_strategy_type="2",
                sort_type=str(supplied.get("sortType") or supplied.get("sort_type") or "0"),
            )
        elif method_key == "video_search":
            self._require_cookie(method_key)
            keyword = str(supplied.get("keyword") or "").strip()
            if not keyword:
                raise ProviderInputError("video_search requires keyword")
            base.update(
                keyword=keyword,
                offset=str(supplied.get("offset") or "0"),
                count=str(supplied.get("count") or self.config.count),
                search_id=str(supplied.get("search_id") or ""),
                search_source="normal_search",
                query_correct_type="1",
                is_filter_search="0",
            )
        elif method_key == "user_search":
            self._require_cookie(method_key)
            keyword = str(supplied.get("keyword") or "").strip()
            if not keyword:
                raise ProviderInputError("user_search requires keyword")
            base.update(
                keyword=keyword,
                offset=str(supplied.get("offset") or "0"),
                count=str(supplied.get("count") or self.config.count),
                search_id=str(supplied.get("search_id") or ""),
                type="1",
            )
        elif method_key in {"user_info", "user_info_dy_id"}:
            self._require_cookie(method_key)
            user_id = supplied.get("sec_user_id") or supplied.get("userId") or supplied.get("user_id")
            if not user_id:
                raise ProviderInputError("user_info requires sec_user_id")
            base["sec_user_id"] = str(user_id)
        return base

    def _require_cookie(self, method_key: str) -> None:
        if not self.config.cookie:
            raise ProviderAuthError(f"{method_key} requires DOUYIN_COOKIE")

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        signed = dict(params)
        signed["a_bogus"] = self.signer.sign(params)
        url = endpoint + "?" + urllib.parse.urlencode(signed)
        response = self.transport("GET", url, self._headers(), self.config.timeout_seconds)
        return _decode_response(response)

    def _user_info_by_douyin_id(
        self,
        method_key: str,
        params: dict[str, Any],
        body: dict[str, Any],
        *,
        use_cache: bool,
    ) -> ProviderResult:
        supplied = {**params, **body}
        douyin_id = str(supplied.get("userCode") or supplied.get("douyin_id") or "").strip()
        if not douyin_id:
            raise ProviderInputError("user_info_dy_id requires userCode")
        search = self.call("user_search", params={"keyword": douyin_id}, use_cache=use_cache)
        items = search.get("normalized", {}).get("items", [])
        candidates = [item for item in items if isinstance(item, dict)]
        exact = [item for item in candidates if str(item.get("douyin_id") or "") == douyin_id]
        picked = exact[0] if exact else None
        if not picked or not picked.get("sec_uid"):
            raise ProviderResponseError(f"Douyin user was not found: {douyin_id}")
        result = dict(self.call("user_info", params={"userId": picked["sec_uid"]}, use_cache=use_cache))
        result["method_key"] = method_key
        return result  # type: ignore[return-value]

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": endpoints.DOUYIN_HOME + "/",
            "User-Agent": self.config.user_agent,
        }
        if self.config.cookie:
            headers["Cookie"] = self.config.cookie
        return headers

    def _resolve_share_link(
        self,
        method_key: str,
        params: dict[str, Any],
        body: dict[str, Any],
    ) -> ProviderResult:
        supplied = {**params, **body}
        work_id = supplied.get("id") or supplied.get("work_id")
        original_url = str(supplied.get("url") or supplied.get("share_url") or "")
        final_url = original_url
        raw: dict[str, Any] = {}
        if not work_id and original_url:
            work_id = _work_id(original_url)
            if not work_id:
                response = self.transport("GET", original_url, self._headers(), self.config.timeout_seconds)
                if response.status == 429:
                    raise ProviderRateLimitError("Douyin share link was rate limited")
                if response.status >= 400:
                    raise ProviderUnavailableError(f"share link returned HTTP {response.status}")
                final_url = response.final_url
                work_id = _work_id(final_url)
                if not work_id:
                    _raise_for_html_risk(response)
                    work_id = _work_id(response.body.decode("utf-8", errors="ignore"))
                raw = {"status_code": response.status, "final_url": final_url}
        if not work_id:
            raise ProviderInputError("could not resolve a Douyin work ID from the share link")
        target = f"{endpoints.DOUYIN_HOME}/video/{work_id}"
        normalized = {"status": "success", "target": target, "short_url": original_url or None, "work_id": str(work_id)}
        return build_provider_result(
            provider=self.provider_name,
            method_key=method_key,
            endpoint=None,
            normalized=normalized,
            raw=scrub_secrets(raw),
        )


def _urllib_transport(method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    request = urllib.request.Request(url=url, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(
                status=int(getattr(response, "status", 200)),
                headers=dict(response.headers.items()),
                body=response.read(),
                final_url=response.geturl(),
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(
            status=exc.code,
            headers=dict(exc.headers.items()) if exc.headers else {},
            body=exc.read(),
            final_url=exc.geturl(),
        )
    except Exception as exc:
        raise ProviderUnavailableError("Douyin request failed", detail=str(exc)) from exc


def _decode_response(response: HttpResponse) -> dict[str, Any]:
    if response.status == 429:
        raise ProviderRateLimitError("Douyin API rate limit exceeded")
    if response.status in {401, 403}:
        raise ProviderAuthError(f"Douyin API returned HTTP {response.status}")
    if response.status >= 500:
        raise ProviderUnavailableError(f"Douyin API returned HTTP {response.status}")
    if response.status >= 400:
        raise ProviderResponseError(f"Douyin API returned HTTP {response.status}")
    _raise_for_html_risk(response)
    try:
        decoded = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderResponseError("Douyin response is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ProviderResponseError("Douyin response JSON must be an object")
    message = str(decoded.get("status_msg") or decoded.get("message") or decoded.get("msg") or "")
    status_code = decoded.get("status_code")
    if _risk_text(message) or _risk_text(json.dumps(decoded, ensure_ascii=False)[:2000]):
        raise ProviderRiskControlError("Douyin risk control or CAPTCHA was triggered")
    if status_code not in (None, 0, "0"):
        if any(token in message.lower() for token in ("login", "cookie", "登录")):
            raise ProviderAuthError(message or f"Douyin status_code={status_code}")
        raise ProviderResponseError(message or f"Douyin status_code={status_code}")
    return decoded


def _raise_for_html_risk(response: HttpResponse) -> None:
    content_type = str(response.headers.get("Content-Type") or response.headers.get("content-type") or "").lower()
    sample = response.body[:10000].decode("utf-8", errors="ignore")
    is_html = "text/html" in content_type or sample.lstrip().lower().startswith(("<!doctype html", "<html"))
    if is_html and _risk_text(sample):
        raise ProviderRiskControlError("Douyin returned a CAPTCHA or verification page")
    if is_html:
        raise ProviderResponseError("Douyin returned HTML instead of JSON")


def _risk_text(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("captcha", "verify", "verification", "验证码", "安全验证", "异常访问"))


def _canonical_method(method_key: str) -> str:
    return {"detail_v3": "detail", "detail_v4": "detail"}.get(method_key, method_key)


def _work_id(value: str) -> str | None:
    for pattern in (r"/video/(\d+)", r"modal_id=(\d+)", r"(?:aweme_id|item_id)[=/](\d+)", r'"aweme_id"\s*:\s*"?(\d+)'):
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return value if value.isdigit() and len(value) >= 10 else None


def _normalize(method_key: str, raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    paging = empty_paging()
    if method_key == "detail":
        item = raw.get("aweme_detail") or raw.get("aweme") or raw.get("data") or {}
        video = _normalize_video(item)
        return {"video": video, "source_package": _source_package(video)}, paging
    if method_key == "user_post":
        items = [_normalize_video(item) for item in _video_items(raw)]
        paging = _paging(raw, cursor_keys=("max_cursor", "cursor"))
        return {
            "items": items,
            "source_packages": [_source_package(item) for item in items],
        }, normalize_paging(paging, captured_items=len(items))
    if method_key == "video_search":
        items = [_normalize_video(item) for item in _search_video_items(raw)]
        paging = _paging(raw, cursor_keys=("cursor", "offset"))
        return {
            "items": items,
            "source_packages": [_source_package(item) for item in items],
        }, normalize_paging(paging, captured_items=len(items))
    if method_key == "user_search":
        items = [_normalize_user(item) for item in _search_user_items(raw)]
        paging = _paging(raw, cursor_keys=("cursor", "offset"))
        return {"items": items}, normalize_paging(paging, captured_items=len(items))
    if method_key == "user_info":
        item = raw.get("user") or raw.get("user_info") or raw.get("data") or {}
        return {"user": _normalize_user(item)}, paging
    return {}, paging


def _paging(raw: dict[str, Any], *, cursor_keys: tuple[str, ...]) -> dict[str, Any]:
    cursor = next((raw.get(key) for key in cursor_keys if raw.get(key) not in (None, "")), None)
    has_more_value = raw.get("has_more") if "has_more" in raw else raw.get("hasMore")
    has_next = has_more_value is True or has_more_value == 1 or str(has_more_value).lower() in {"1", "true"}
    search_id = raw.get("search_id") or raw.get("searchId")
    return {
        "has_next": has_next,
        "cursor": str(cursor) if cursor is not None else None,
        "offset": str(cursor) if cursor is not None else None,
        "search_id": str(search_id) if search_id not in (None, "") else None,
        "page": None,
        "raw": {
            key: raw[key]
            for key in ("cursor", "offset", "max_cursor", "has_more", "hasMore", "search_id", "searchId")
            if key in raw
        },
    }


def _video_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
    items = raw.get("aweme_list") or raw.get("items") or raw.get("list") or []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _search_video_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
    source = raw.get("data") or raw.get("items") or raw.get("aweme_list") or []
    output: list[dict[str, Any]] = []
    if isinstance(source, list):
        for item in source:
            if not isinstance(item, dict):
                continue
            candidate = item.get("aweme_info") or item.get("aweme_mix_info") or item
            if isinstance(candidate, dict) and (candidate.get("aweme_id") or candidate.get("id")):
                output.append(candidate)
    return output


def _search_user_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
    source = raw.get("user_list") or raw.get("data") or raw.get("items") or []
    output: list[dict[str, Any]] = []
    if isinstance(source, list):
        for item in source:
            if isinstance(item, dict):
                candidate = item.get("user_info") or item.get("user") or item
                if isinstance(candidate, dict):
                    output.append(candidate)
    return output


def _normalize_video(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"raw": item}
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    music = item.get("music") if isinstance(item.get("music"), dict) else {}
    work_id = item.get("aweme_id") or item.get("id")
    caption = item.get("desc") or item.get("title") or ""
    return {
        "id": str(work_id) if work_id is not None else None,
        "title": caption,
        "caption": caption,
        "share_url": item.get("share_url") or (f"{endpoints.DOUYIN_HOME}/video/{work_id}" if work_id else None),
        "short_url": item.get("short_url"),
        "author_name": author.get("nickname") or item.get("nickname"),
        "author_sec_uid": author.get("sec_uid") or item.get("sec_uid"),
        "author_douyin_id": author.get("unique_id") or author.get("short_id") or item.get("unique_id"),
        "author_profile_url": author.get("share_url"),
        "post_time": _post_time(item.get("create_time") or item.get("post_time")),
        "duration": item.get("duration") or video.get("duration"),
        "cover_url": _first_url(video.get("cover") or video.get("dynamic_cover") or item.get("cover")),
        "video_url": _first_url(video.get("play_addr") or video.get("download_addr") or item.get("video_url")),
        "audio_url": _first_url(music.get("play_url") or item.get("audio_url")),
        "metrics": {
            "digg_count": statistics.get("digg_count") or item.get("digg_count"),
            "collect_count": statistics.get("collect_count") or item.get("collect_count"),
            "comment_count": statistics.get("comment_count") or item.get("comment_count"),
            "share_count": statistics.get("share_count") or item.get("share_count"),
            "play_count": statistics.get("play_count") or item.get("play_count"),
        },
        "raw": scrub_secrets(item),
    }


def _normalize_user(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"raw": item}
    sec_uid = item.get("sec_uid") or item.get("secUid")
    return {
        "nickname": item.get("nickname"),
        "sec_uid": sec_uid,
        "douyin_id": item.get("unique_id") or item.get("short_id"),
        "share_url": item.get("share_url") or (f"{endpoints.DOUYIN_HOME}/user/{sec_uid}" if sec_uid else None),
        "signature": item.get("signature"),
        "follower_count": item.get("follower_count"),
        "total_favorited": item.get("total_favorited"),
        "avatar_url": _first_url(item.get("avatar_larger") or item.get("avatar_thumb")),
        "raw": scrub_secrets(item),
    }


def _source_package(video: dict[str, Any]) -> dict[str, Any]:
    caption = str(video.get("caption") or video.get("title") or "").strip()
    hashtags = list(dict.fromkeys(match.group(1).strip() for match in re.finditer(r"#([^\s#]+)", caption)))
    caption_text = re.sub(r"#([^\s#]+)", "", caption)
    caption_text = re.sub(r"\s+", " ", caption_text).strip()
    package: dict[str, Any] = {
        "source_type": "douyin",
        "source_platform": "douyin",
        "source_link": video.get("share_url") or video.get("short_url"),
        "title": caption_text or video.get("title"),
        "clean_title": caption_text,
        "platform_caption": caption,
        "caption_text": caption_text,
        "hashtags": hashtags,
        "transcript_text": "",
        "author_name": video.get("author_name"),
        "author_sec_uid": video.get("author_sec_uid"),
        "author_douyin_id": video.get("author_douyin_id"),
        "author_profile_url": video.get("author_profile_url"),
        "work_id": video.get("id"),
        "work_short_url": video.get("short_url"),
        "post_time": video.get("post_time"),
        "cover_url": video.get("cover_url"),
        "video_url": video.get("video_url"),
        "audio_url": video.get("audio_url"),
        "public_metrics": dict(video.get("metrics") or {}),
        "collection_notes": [],
    }
    duration = video.get("duration")
    if duration not in (None, ""):
        package["duration_ms"] = duration
        try:
            package["duration_seconds"] = float(duration) / 1000
        except (TypeError, ValueError):
            pass
    return package


def _first_url(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        urls = value.get("url_list") or value.get("urlList")
        if isinstance(urls, list) and urls:
            return str(urls[0])
        return _first_url(value.get("url"))
    if isinstance(value, list) and value:
        return _first_url(value[0])
    return None


def _post_time(value: Any) -> Any:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    return value


def scrub_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("cookie", "authorization", "api_key", "apikey", "secret", "token", "a_bogus")):
                output[key] = "<redacted>"
            else:
                output[key] = scrub_secrets(item)
        return output
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(a_bogus|[^&\s]*token|cookie|authorization)=([^&\s]+)", r"\1=<redacted>", value)
    return value
