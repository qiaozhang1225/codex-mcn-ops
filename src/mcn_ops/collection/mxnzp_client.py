from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .api_manifest import ApiMethodManifest, load_manifest_from_markdown


COOKIE_REQUIRED_METHODS = {"user_post"}


class MxnzpConfigError(Exception):
    pass


class MxnzpRequestError(Exception):
    pass


@dataclass
class MxnzpConfig:
    app_id: str
    app_secret: str
    douyin_cookie: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 1

    @classmethod
    def from_env(cls) -> "MxnzpConfig":
        _load_local_env()
        app_id = os.environ.get("MXNZP_APP_ID", "").strip()
        app_secret = os.environ.get("MXNZP_APP_SECRET", "").strip()
        if not app_id or not app_secret:
            raise MxnzpConfigError("MXNZP_APP_ID and MXNZP_APP_SECRET are required.")
        return cls(
            app_id=app_id,
            app_secret=app_secret,
            douyin_cookie=os.environ.get("DOUYIN_COOKIE"),
            timeout_seconds=float(os.environ.get("MXNZP_TIMEOUT_SECONDS", "30")),
            max_retries=int(os.environ.get("MXNZP_MAX_RETRIES", "1")),
        )


Transport = Callable[[str, str, Optional[bytes], Mapping[str, str], float], dict[str, Any]]


@dataclass
class PagingState:
    has_next: bool = False
    cursor: str | None = None
    offset: str | None = None
    search_id: str | None = None
    page: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_next": self.has_next,
            "cursor": self.cursor,
            "offset": self.offset,
            "search_id": self.search_id,
            "page": self.page,
            "raw": self.raw,
        }


class MxnzpDouyinProClient:
    def __init__(
        self,
        config: MxnzpConfig,
        manifest_path: str | Path | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.config = config
        self.methods: dict[str, ApiMethodManifest] = {
            method.key: method for method in load_manifest_from_markdown(manifest_path)
        }
        self.transport = transport or _urllib_transport
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

    def call(
        self,
        method_key: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        if method_key not in self.methods:
            raise MxnzpRequestError(f"Unknown mxnzp method: {method_key}")

        method = self.methods[method_key]
        params = dict(params or {})
        body = dict(body or {})
        self._guard_requirements(method, params, body)

        request_url, request_body, headers = self._build_request(method, params, body)
        cache_key = (
            method_key,
            json.dumps({"url": _scrub_url(request_url), "body": body}, ensure_ascii=False, sort_keys=True),
        )
        if use_cache and cache_key in self._cache:
            cached = dict(self._cache[cache_key])
            cached["cache_hit"] = True
            return cached

        raw = self._request_with_retry(method.http_method, request_url, request_body, headers)
        safe_raw = scrub_secrets(raw)
        _raise_for_api_error(safe_raw)
        normalized = normalize_response(method_key, safe_raw)
        result = {
            "ok": True,
            "method_key": method_key,
            "endpoint": method.endpoint,
            "cost_weight": method.cost_weight,
            "paging": infer_paging_state(safe_raw, normalized).to_dict(),
            "normalized": normalized,
            "raw": safe_raw,
            "cache_hit": False,
        }
        if use_cache:
            self._cache[cache_key] = result
        return result

    def _guard_requirements(
        self,
        method: ApiMethodManifest,
        params: dict[str, Any],
        body: dict[str, Any],
    ) -> None:
        if method.key == "video_search" and self.config.douyin_cookie:
            params.setdefault("cookie", self.config.douyin_cookie)

        if method.key in COOKIE_REQUIRED_METHODS:
            supplied_cookie = params.get("cookie") or body.get("cookie") or self.config.douyin_cookie
            if not supplied_cookie:
                raise MxnzpConfigError(f"{method.key} requires DOUYIN_COOKIE or an explicit cookie parameter.")
            params.setdefault("cookie", supplied_cookie)

    def _build_request(
        self,
        method: ApiMethodManifest,
        params: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[str, bytes | None, dict[str, str]]:
        query = dict(params)
        query["app_id"] = self.config.app_id
        query["app_secret"] = self.config.app_secret

        if method.key in {"detail", "detail_v3", "comments", "child_comments"} and "url" in query:
            query["url"] = base64.b64encode(str(query["url"]).encode("utf-8")).decode("ascii")

        request_url = method.endpoint + "?" + urllib.parse.urlencode(query)
        headers: dict[str, str] = {}
        request_body: bytes | None = None
        if method.http_method == "POST":
            headers["Content-Type"] = method.content_type or "application/json"
            request_body = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else b"{}"
        return request_url, request_body, headers

    def _request_with_retry(
        self,
        http_method: str,
        url: str,
        body: bytes | None,
        headers: Mapping[str, str],
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return self.transport(http_method, url, body, headers, self.config.timeout_seconds)
            except Exception as exc:  # pragma: no cover - exact network exception varies
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                time.sleep(0.2 * (attempt + 1))
        raise MxnzpRequestError(str(last_error))


def _urllib_transport(
    http_method: str,
    url: str,
    body: bytes | None,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    request = urllib.request.Request(url=url, data=body, headers=dict(headers), method=http_method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise MxnzpRequestError(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='ignore')}") from exc
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MxnzpRequestError(f"Response is not valid JSON: {payload[:300]}") from exc
    if not isinstance(decoded, dict):
        raise MxnzpRequestError("Response JSON must be an object.")
    return decoded


def normalize_response(method_key: str, raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data", raw)
    if not isinstance(data, dict):
        items = data if isinstance(data, list) else [data]
        if method_key.startswith("billboard_"):
            return {"items": [_normalize_rank_item(item) for item in items]}
        return {"items": items}

    if method_key in {"video_search", "user_post", "user_favorite_list", "user_mix_list", "user_series_list"}:
        items = [_normalize_video_item(item) for item in _items(data)]
        return {"items": items, "source_packages": [_source_package_from_video(item) for item in items]}
    if method_key == "user_search":
        return {"items": [_normalize_user_item(item) for item in _items(data)]}
    if method_key.startswith("billboard_"):
        items = _items(data) or data.get("list") or data.get("data") or []
        return {"items": [_normalize_rank_item(item) for item in items] if isinstance(items, list) else data}
    if method_key in {"comments", "child_comments"}:
        return {"comments": _items(data)}
    if method_key == "video_to_text_v2":
        video = _normalize_video_item(data.get("douyinInfo", {}))
        transcript_text = data.get("audioInfo")
        return {
            "text": transcript_text,
            "video": video,
            "source_package": _source_package_from_video(video, transcript_text=transcript_text),
        }
    if method_key in {"detail", "detail_v3", "detail_v4"}:
        video = _normalize_video_item(data)
        return {"video": video, "source_package": _source_package_from_video(video)}
    if method_key in {"user_info", "user_info_dy_id"}:
        return {"user": _normalize_user_item(data)}
    if method_key == "share_link":
        return {
            "status": data.get("status"),
            "target": data.get("target"),
            "short_url": data.get("short_url") or data.get("shortUrl"),
            "raw": data,
        }
    return data


def infer_paging_state(raw: dict[str, Any], normalized: dict[str, Any]) -> PagingState:
    data = raw.get("data", raw)
    if not isinstance(data, dict):
        return PagingState(raw={})
    has_next = _truthy_paging_flag(data.get("hasMore") if "hasMore" in data else data.get("has_more"))
    cursor = _optional_str(data.get("cursor") or data.get("max_cursor"))
    return PagingState(
        has_next=has_next,
        cursor=cursor,
        offset=cursor,
        search_id=_optional_str(data.get("searchId") or data.get("search_id")),
        raw={
            key: data.get(key)
            for key in ["cursor", "max_cursor", "hasMore", "has_more", "searchId", "search_id"]
            if key in data
        },
    )


def scrub_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(token in lowered for token in ["secret", "cookie", "api_key", "apikey", "authorization"]):
                scrubbed[key] = "<redacted>"
            else:
                scrubbed[key] = scrub_secrets(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(app_secret=)[^&]+", r"\1<redacted>", value)
    return value


def _load_local_env() -> None:
    for path in [Path(".env.local"), Path(".env")]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _scrub_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    safe = [
        (key, "<redacted>" if key.lower() in {"app_secret", "cookie"} else value)
        for key, value in query
    ]
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(safe)))


def _raise_for_api_error(raw: dict[str, Any]) -> None:
    code = raw.get("code")
    if code in (None, 0, 1, 200, "0", "1", "200"):
        return
    raise MxnzpRequestError(str(raw.get("msg") or raw.get("message") or f"mxnzp API returned code={code}"))


def _items(data: dict[str, Any]) -> list[Any]:
    items = data.get("items")
    if items is None:
        items = data.get("list")
    if items is None:
        items = data.get("aweme_list")
    return items if isinstance(items, list) else []


def _normalize_video_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"raw": item}
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
    share_url = item.get("shareUrl") or item.get("share_url")
    author_profile_url = item.get("userShareUrl") or item.get("user_share_url") or author.get("shareUrl")
    title = item.get("title") or item.get("desc")
    caption = item.get("desc") or item.get("title")
    return {
        "id": item.get("id") or item.get("aweme_id") or item.get("awemeId"),
        "title": title,
        "caption": caption,
        "share_url": share_url,
        "short_url": item.get("shortUrl") or item.get("short_url"),
        "author_name": author.get("nickname") or item.get("nickname") or item.get("nickName") or item.get("author_name"),
        "author_sec_uid": item.get("sec_uid") or item.get("secUid") or _parse_author_sec_uid(author_profile_url),
        "author_douyin_id": author.get("unique_id") or author.get("short_id") or item.get("douyin_id"),
        "author_profile_url": author_profile_url,
        "post_time": item.get("post_time") or item.get("postTime"),
        "duration": item.get("duration") or item.get("videoDuration"),
        "cover_url": item.get("cover") or item.get("coverUrl") or item.get("cover_url"),
        "video_url": item.get("videoUrl") or item.get("video_url"),
        "audio_url": item.get("audioUrl") or item.get("audio_url"),
        "metrics": {
            "digg_count": item.get("digg_count") or item.get("diggCount") or statistics.get("digg_count"),
            "collect_count": item.get("collect_count") or item.get("collectCount") or statistics.get("collect_count"),
            "comment_count": item.get("comment_count") or item.get("commentCount") or statistics.get("comment_count"),
            "share_count": item.get("share_count") or item.get("shareCount") or statistics.get("share_count"),
            "play_count": item.get("play_count") or item.get("playCount") or statistics.get("play_count"),
        },
        "raw": item,
    }


def _source_package_from_video(video: dict[str, Any], transcript_text: str | None = None) -> dict[str, Any]:
    parsed_caption = _parse_caption(
        title=str(video.get("title") or ""),
        caption=str(video.get("caption") or video.get("title") or ""),
    )
    package = {
        "source_type": "mxnzp_douyin",
        "source_platform": "douyin",
        "source_link": video.get("share_url") or video.get("short_url"),
        "title": parsed_caption["clean_title"] or video.get("title"),
        "clean_title": parsed_caption["clean_title"],
        "platform_caption": video.get("caption") or video.get("title"),
        "caption_text": parsed_caption["caption_text"],
        "hashtags": parsed_caption["hashtags"],
        "transcript_text": transcript_text or "",
        "author_name": video.get("author_name"),
        "author_sec_uid": video.get("author_sec_uid"),
        "author_profile_url": video.get("author_profile_url"),
        "author_douyin_id": video.get("author_douyin_id"),
        "work_id": video.get("id"),
        "work_short_url": video.get("short_url"),
        "post_time": video.get("post_time"),
        "cover_url": video.get("cover_url"),
        "video_url": video.get("video_url"),
        "audio_url": video.get("audio_url"),
        "public_metrics": video.get("metrics") or {},
        "collection_notes": [],
    }
    if video.get("duration") not in (None, ""):
        package["duration_ms"] = video.get("duration")
        try:
            package["duration_seconds"] = float(video["duration"]) / 1000
        except (TypeError, ValueError):
            pass
    return package


def _parse_caption(*, title: str, caption: str) -> dict[str, Any]:
    raw_caption = str(caption or title or "").strip()
    hashtags: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"#([^\s#]+)", raw_caption):
        tag = match.group(1).strip()
        if tag and tag not in seen:
            seen.add(tag)
            hashtags.append(tag)
    caption_text = re.sub(r"#([^\s#]+)", "", raw_caption).strip()
    caption_text = re.sub(r"\s+", " ", caption_text)
    clean_title = re.sub(r"#([^\s#]+)", "", str(title or caption_text or raw_caption)).strip()
    clean_title = re.sub(r"\s+", " ", clean_title)
    return {"clean_title": clean_title, "caption_text": caption_text, "hashtags": hashtags}


def _normalize_user_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"raw": item}
    return {
        "nickname": item.get("nickname"),
        "sec_uid": item.get("sec_uid") or item.get("secUid"),
        "douyin_id": item.get("unique_id") or item.get("short_id"),
        "share_url": item.get("shareUrl") or item.get("share_url"),
        "raw": item,
    }


def _normalize_rank_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"raw": item}
    video = _normalize_video_item(item)
    video["rank"] = item.get("rank")
    video["rank_diff"] = item.get("rank_diff") or item.get("rankDiff")
    return video


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _truthy_paging_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return False


def _parse_author_sec_uid(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"user/([^/?]+)", url)
    return match.group(1) if match else None
