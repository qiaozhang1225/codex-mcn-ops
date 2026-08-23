from __future__ import annotations

import asyncio
import html
import os
import re
import ssl
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from ..douyin.contracts import ProviderResult, build_provider_result, normalize_paging
from ..douyin.errors import ProviderConfigError, ProviderInputError, ProviderResponseError
from .hub import ChannelsHub
from .media_probe import extract_media_candidate
from .probe import _is_loopback_host, _server_ssl_context


@dataclass(frozen=True)
class ChannelsRemoteConfig:
    worker_id: str
    shared_secret: str
    host: str = "127.0.0.1"
    port: int = 18081
    wait_timeout: float = 120.0
    command_timeout: float = 180.0
    tls_cert: str | None = None
    tls_key: str | None = None
    allow_insecure_lan: bool = False

    @classmethod
    def from_env(
        cls,
        *,
        worker_id_override: str | None = None,
        shared_secret_override: str | None = None,
    ) -> "ChannelsRemoteConfig":
        worker_id = str(
            worker_id_override
            if worker_id_override is not None
            else os.environ.get("CHANNELS_WORKER_ID", "")
        ).strip()
        shared_secret = str(
            shared_secret_override
            if shared_secret_override is not None
            else os.environ.get("CHANNELS_HUB_SECRET", "")
        ).strip()
        if not worker_id:
            raise ProviderConfigError("CHANNELS_WORKER_ID is required")
        if not shared_secret:
            raise ProviderConfigError("CHANNELS_HUB_SECRET is required")
        return cls(
            worker_id=worker_id,
            shared_secret=shared_secret,
            host=os.environ.get("CHANNELS_HUB_HOST", "127.0.0.1").strip(),
            port=_env_int("CHANNELS_HUB_PORT", 18081),
            wait_timeout=_env_float("CHANNELS_WAIT_TIMEOUT", 120.0),
            command_timeout=_env_float("CHANNELS_COMMAND_TIMEOUT", 180.0),
            tls_cert=os.environ.get("CHANNELS_TLS_CERT", "").strip() or None,
            tls_key=os.environ.get("CHANNELS_TLS_KEY", "").strip() or None,
            allow_insecure_lan=_env_bool("CHANNELS_ALLOW_INSECURE_LAN", False),
        )


@dataclass(frozen=True)
class ChannelsMediaLease:
    work_id: str
    locator: str
    decryption_key: str
    duration_ms: int
    file_size: int


class ChannelsSessionGuard(Protocol):
    @property
    def worker_id(self) -> str: ...

    @property
    def shared_secret(self) -> str: ...

    def ensure_active(self) -> dict[str, Any]: ...


class ChannelsRemoteProvider:
    provider_name = "wechat_channels_remote"

    def __init__(
        self,
        config: ChannelsRemoteConfig,
        *,
        session_guard: ChannelsSessionGuard | None = None,
    ) -> None:
        self.config = config
        self.session_guard = session_guard
        _validate_config(config)
        if session_guard is not None and session_guard.worker_id != config.worker_id:
            raise ProviderConfigError("Channels session guard worker_id must match provider config")

    def call(
        self,
        method_key: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ProviderResult:
        del use_cache
        supplied = {**(params or {}), **(body or {})}
        canonical = _canonical_method(method_key)
        if canonical == "search":
            keyword = str(supplied.get("keyword") or "").strip()
            if not keyword:
                raise ProviderInputError("Channels search requires keyword")
            max_pages = _positive_int(supplied.get("max_pages"), default=1, label="max_pages")
            page_size = _positive_int(supplied.get("page_size"), default=20, label="page_size")
            cursor = str(supplied.get("cursor") or supplied.get("next_marker") or "")
            return self.search_many(
                [keyword], max_pages=max_pages, page_size=page_size, cursor=cursor
            )[0]
        if canonical == "author_feed":
            platform_author_id = str(
                supplied.get("platform_author_id")
                or supplied.get("author_id")
                or supplied.get("username")
                or ""
            ).strip()
            if not platform_author_id:
                raise ProviderInputError("Channels author feed requires platform_author_id")
            return asyncio.run(
                self._author_feed_once(
                    platform_author_id=platform_author_id,
                    cursor=str(supplied.get("cursor") or supplied.get("next_marker") or ""),
                    max_pages=_positive_int(
                        supplied.get("max_pages"), default=1, label="max_pages"
                    ),
                    page_size=_positive_int(
                        supplied.get("page_size"), default=20, label="page_size"
                    ),
                )
            )
        if canonical == "detail":
            return asyncio.run(self._detail_once(supplied))
        raise ProviderInputError(f"unsupported Channels method: {method_key}")

    def search_many(
        self,
        keywords: Iterable[str],
        *,
        max_pages: int = 1,
        page_size: int = 20,
        cursor: str = "",
    ) -> list[ProviderResult]:
        normalized_keywords = [str(keyword).strip() for keyword in keywords if str(keyword).strip()]
        if not normalized_keywords:
            raise ProviderInputError("at least one Channels keyword is required")
        if max_pages < 1 or page_size < 1:
            raise ProviderInputError("max_pages and page_size must be positive")
        if cursor and len(normalized_keywords) != 1:
            raise ProviderInputError("a Channels cursor can resume only one keyword")
        return asyncio.run(
            self._search_many(
                normalized_keywords,
                max_pages=max_pages,
                page_size=page_size,
                cursor=cursor,
            )
        )

    def resolve_media_lease(self, detail_ref: dict[str, Any]) -> ChannelsMediaLease:
        return asyncio.run(self._resolve_media_lease_once(detail_ref))

    async def _search_many(
        self,
        keywords: list[str],
        *,
        max_pages: int,
        page_size: int,
        cursor: str,
    ) -> list[ProviderResult]:
        hub, ssl_context = await self._start_hub()
        del ssl_context
        try:
            await hub.wait_for_worker(
                self.config.worker_id,
                timeout=self.config.wait_timeout,
                required_capability="search",
            )
            return [
                await _search_with_hub(
                    hub,
                    worker_id=self.config.worker_id,
                    keyword=keyword,
                    max_pages=max_pages,
                    page_size=page_size,
                    cursor=cursor,
                    command_timeout=self.config.command_timeout,
                )
                for keyword in keywords
            ]
        finally:
            await hub.stop()

    async def _author_feed_once(
        self,
        *,
        platform_author_id: str,
        cursor: str,
        max_pages: int,
        page_size: int,
    ) -> ProviderResult:
        hub, ssl_context = await self._start_hub()
        del ssl_context
        try:
            await hub.wait_for_worker(
                self.config.worker_id,
                timeout=self.config.wait_timeout,
                required_capability="feed",
            )
            return await _author_feed_with_hub(
                hub,
                worker_id=self.config.worker_id,
                platform_author_id=platform_author_id,
                cursor=cursor,
                max_pages=max_pages,
                page_size=page_size,
                command_timeout=self.config.command_timeout,
            )
        finally:
            await hub.stop()

    async def _detail_once(self, supplied: dict[str, Any]) -> ProviderResult:
        hub, ssl_context = await self._start_hub()
        del ssl_context
        try:
            await hub.wait_for_worker(
                self.config.worker_id,
                timeout=self.config.wait_timeout,
                required_capability="profile",
            )
            detail = await _detail_with_hub(
                hub,
                worker_id=self.config.worker_id,
                detail_ref=supplied,
                command_timeout=self.config.command_timeout,
            )
            package = _source_package(detail)
            media_candidate = extract_media_candidate(detail)
            package["detail_verified"] = True
            package["media_lease_available"] = bool(
                media_candidate and media_candidate.get("locator")
            )
            return build_provider_result(
                provider=self.provider_name,
                method_key="wechat_channels_detail",
                endpoint="channels-lan://detail",
                normalized={"source_package": package},
                raw={},
            )
        finally:
            await hub.stop()

    async def _resolve_media_lease_once(
        self, detail_ref: dict[str, Any]
    ) -> ChannelsMediaLease:
        hub, ssl_context = await self._start_hub()
        del ssl_context
        try:
            await hub.wait_for_worker(
                self.config.worker_id,
                timeout=self.config.wait_timeout,
                required_capability="profile",
            )
            detail = await _detail_with_hub(
                hub,
                worker_id=self.config.worker_id,
                detail_ref=detail_ref,
                command_timeout=self.config.command_timeout,
            )
            candidate = extract_media_candidate(detail)
            if not candidate or not candidate.get("locator"):
                raise ProviderResponseError("Channels detail returned no media locator")
            return ChannelsMediaLease(
                work_id=str(candidate.get("work_id") or detail_ref.get("object_id") or ""),
                locator=str(candidate["locator"]),
                decryption_key=str(candidate.get("decryption_key") or ""),
                duration_ms=_int(candidate.get("duration_ms")),
                file_size=_int(candidate.get("file_size")),
            )
        finally:
            await hub.stop()

    async def _start_hub(self) -> tuple[ChannelsHub, ssl.SSLContext | None]:
        shared_secret = self.config.shared_secret
        worker_id = self.config.worker_id
        if self.session_guard is not None:
            self.session_guard.ensure_active()
            shared_secret = self.session_guard.shared_secret
            worker_id = self.session_guard.worker_id
        ssl_context = _server_ssl_context(self.config.tls_cert, self.config.tls_key)
        hub = ChannelsHub(
            shared_secret=shared_secret,
            allowed_worker_ids={worker_id},
        )
        await hub.start(self.config.host, self.config.port, ssl_context=ssl_context)
        return hub, ssl_context


async def _search_with_hub(
    hub: ChannelsHub,
    *,
    worker_id: str,
    keyword: str,
    max_pages: int,
    page_size: int,
    command_timeout: float,
    cursor: str = "",
) -> ProviderResult:
    packages: list[dict[str, Any]] = []
    seen: set[str] = set()
    initial_cursor = cursor
    next_marker = cursor
    seen_cursors = {cursor} if cursor else set()
    has_more = False
    stop_reason = "source_exhausted"
    captured_pages = 0
    for page in range(1, max_pages + 1):
        data = await hub.call(
            worker_id,
            "search_videos",
            {
                "keyword": keyword,
                "next_marker": next_marker,
                "page": page,
                "page_size": page_size,
            },
            timeout=command_timeout,
            required_capability="search",
        )
        if not isinstance(data, dict) or not isinstance(data.get("list"), list):
            raise ProviderResponseError("Channels search returned an invalid list")
        captured_pages += 1
        for item in data["list"]:
            package = _source_package(item)
            work_id = str(package.get("work_id") or "")
            if not work_id or work_id in seen:
                continue
            seen.add(work_id)
            package["search_keyword"] = keyword
            packages.append(package)
        has_more = bool(data.get("has_more"))
        marker = str(data.get("next_marker") or "")
        if not has_more:
            stop_reason = "source_exhausted"
            break
        if not marker:
            stop_reason = "cursor_missing"
            next_marker = ""
            break
        if marker in seen_cursors:
            stop_reason = "cursor_cycle"
            next_marker = ""
            break
        seen_cursors.add(marker)
        next_marker = marker
    else:
        stop_reason = "max_pages" if has_more else "source_exhausted"
    source_exhausted = stop_reason == "source_exhausted"
    paging = normalize_paging(
        {
            "has_next": has_more,
            "cursor": next_marker if stop_reason == "max_pages" else None,
            "next_cursor": next_marker if stop_reason == "max_pages" else None,
            "captured_pages": captured_pages,
            "captured_items": len(packages),
            "stop_reason": stop_reason,
            "request_satisfied": stop_reason in {"source_exhausted", "max_pages"},
            "source_exhausted": source_exhausted,
            "raw": {"resumed_from_cursor": bool(initial_cursor)},
        },
        captured_items=len(packages),
    )
    return build_provider_result(
        provider="wechat_channels_remote",
        method_key="wechat_channels_search",
        endpoint="channels-lan://search",
        normalized={"keyword": keyword, "source_packages": packages},
        raw={},
        paging=paging,
    )


async def _author_feed_with_hub(
    hub: ChannelsHub,
    *,
    worker_id: str,
    platform_author_id: str,
    max_pages: int,
    page_size: int,
    command_timeout: float,
    cursor: str = "",
) -> ProviderResult:
    packages: list[dict[str, Any]] = []
    seen_work_ids: set[str] = set()
    initial_cursor = cursor
    next_marker = cursor
    seen_cursors = {cursor} if cursor else set()
    has_more = False
    stop_reason = "pagination_unverified"
    captured_pages = 0
    for page in range(1, max_pages + 1):
        data = await hub.call(
            worker_id,
            "api_call",
            {
                "key": "key:channels:feed_list",
                "body": {
                    "username": platform_author_id,
                    "next_marker": next_marker,
                    "page": page,
                    "page_size": page_size,
                },
            },
            timeout=command_timeout,
            required_capability="feed",
        )
        items, marker, continuation = _parse_author_feed_response(data)
        captured_pages += 1
        for item in items:
            package = _source_package(item)
            work_id = str(package.get("work_id") or "")
            if not work_id or work_id in seen_work_ids:
                continue
            seen_work_ids.add(work_id)
            package["collection_notes"] = [
                {"type": "author_feed", "platform_author_id": platform_author_id}
            ]
            packages.append(package)

        has_more = continuation is True or (continuation is None and bool(marker))
        if continuation is False:
            # The pinned worker documents this flag, but its live author-feed
            # terminal shape has not yet been captured on this installation.
            stop_reason = "source_exhausted_unverified"
            next_marker = ""
            break
        if continuation is None and not marker:
            stop_reason = "pagination_unverified"
            next_marker = ""
            break
        if not marker:
            stop_reason = "cursor_missing"
            next_marker = ""
            break
        if marker in seen_cursors:
            stop_reason = "cursor_cycle"
            next_marker = ""
            break
        seen_cursors.add(marker)
        next_marker = marker
    else:
        stop_reason = "max_pages" if has_more else "pagination_unverified"

    source_exhausted = False
    paging = normalize_paging(
        {
            "has_next": has_more,
            "cursor": next_marker if stop_reason == "max_pages" else None,
            "next_cursor": next_marker if stop_reason == "max_pages" else None,
            "captured_pages": captured_pages,
            "captured_items": len(packages),
            "stop_reason": stop_reason,
            "request_satisfied": stop_reason == "max_pages",
            "source_exhausted": source_exhausted,
            "raw": {
                "resumed_from_cursor": bool(initial_cursor),
                "response_contract": "poc_fixture_only",
            },
        },
        captured_items=len(packages),
    )
    return build_provider_result(
        provider="wechat_channels_remote",
        method_key="wechat_channels_author_feed",
        endpoint="channels-lan://author-feed",
        normalized={
            "platform_author_id": platform_author_id,
            "source_packages": packages,
            "response_contract": "poc_fixture_only",
            "capability_gate": {
                "required_worker_capability": "feed",
                "live_poc_verified": False,
                "production_ready": False,
            },
        },
        raw={},
        paging=paging,
    )


def _parse_author_feed_response(
    value: Any,
) -> tuple[list[Any], str, bool | None]:
    """Parse the pinned upstream's documented shape; live fixture validation is still required."""

    error = _author_feed_error(value)
    if error:
        raise ProviderResponseError(f"Channels author feed returned an error: {error}")
    payload = _find_author_feed_payload(value)
    if payload is None:
        raise ProviderResponseError("Channels author feed returned an unverified response shape")
    items = payload.get("object")
    if not isinstance(items, list):
        raise ProviderResponseError("Channels author feed returned an invalid object list")
    marker = str(payload.get("lastBuffer") or payload.get("lastBuff") or "")
    raw_continuation = payload.get("continueFlag")
    continuation: bool | None
    if raw_continuation is None:
        continuation = None
    else:
        try:
            continuation = int(raw_continuation) != 0
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(
                "Channels author feed returned an invalid continuation flag"
            ) from exc
    return items, marker, continuation


def _author_feed_error(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    error_code = value.get("errCode")
    if error_code not in (None, "", 0, "0"):
        return str(value.get("errMsg") or error_code)
    base_response = value.get("BaseResponse")
    if isinstance(base_response, dict) and base_response.get("Ret") not in (None, "", 0, "0"):
        return str(base_response.get("ErrMsg") or base_response.get("Ret"))
    for key in ("data", "response"):
        error = _author_feed_error(value.get(key))
        if error:
            return error
    return ""


def _find_author_feed_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("object"), list):
        return value
    for key in ("data", "response"):
        found = _find_author_feed_payload(value.get(key))
        if found is not None:
            return found
    return None


async def _detail_with_hub(
    hub: ChannelsHub,
    *,
    worker_id: str,
    detail_ref: dict[str, Any],
    command_timeout: float,
) -> dict[str, Any]:
    object_id = str(
        detail_ref.get("object_id") or detail_ref.get("objectId") or detail_ref.get("work_id") or ""
    )
    nonce_id = str(
        detail_ref.get("object_nonce_id") or detail_ref.get("nonce_id") or detail_ref.get("nonceId") or ""
    )
    encrypted_object_id = str(
        detail_ref.get("encrypted_object_id") or detail_ref.get("encryptedObjectId") or detail_ref.get("eid") or ""
    )
    if not encrypted_object_id and (not object_id or not nonce_id):
        raise ProviderInputError("Channels detail requires eid or object_id plus object_nonce_id")
    data = await hub.call(
        worker_id,
        "api_call",
        {
            "key": "key:channels:feed_profile",
            "body": {
                "objectId": object_id,
                "nonceId": nonce_id,
                "eid": encrypted_object_id,
            },
        },
        timeout=command_timeout,
        required_capability="profile",
    )
    if not isinstance(data, dict):
        raise ProviderResponseError("Channels detail returned an invalid object")
    return data


def _source_package(value: Any) -> dict[str, Any]:
    obj = _find_object(value)
    if obj is None:
        return {}
    contact = obj.get("contact") if isinstance(obj.get("contact"), dict) else {}
    description = obj.get("objectDesc") if isinstance(obj.get("objectDesc"), dict) else {}
    text = _clean_caption(description.get("description") or obj.get("title") or "")
    media = description.get("media") if isinstance(description.get("media"), list) else []
    primary_media = next((item for item in media if isinstance(item, dict)), {})
    specs = primary_media.get("spec") if isinstance(primary_media.get("spec"), list) else []
    primary_spec = next((item for item in specs if isinstance(item, dict)), {})
    work_id = str(obj.get("id") or "")
    author_id = str(contact.get("username") or obj.get("username") or "")
    return {
        "source_type": "wechat_channels_remote",
        "source_platform": "wechat_channels",
        "provider": "wechat_channels_remote",
        "work_id": work_id,
        "title": text[:120],
        "platform_caption": text,
        "author_name": str(contact.get("nickname") or obj.get("nickname") or ""),
        "author_sec_uid": author_id,
        "platform_author_id": author_id,
        "post_time": _int(obj.get("createtime")),
        "duration_ms": _media_duration_ms(primary_media, primary_spec),
        "public_metrics": {
            "digg_count": _int(obj.get("likeCount")),
            "collect_count": _int(obj.get("favCount")),
            "comment_count": _int(obj.get("commentCount")),
            "share_count": _int(obj.get("forwardCount")),
            "play_count": None,
        },
        "detail_ref": {
            "object_id": work_id,
            "object_nonce_id": str(obj.get("objectNonceId") or obj.get("nonceId") or ""),
            "encrypted_object_id": str(
                obj.get("encryptedObjectId")
                or obj.get("encrypted_objectid")
                or obj.get("eid")
                or ""
            ),
        },
        "media_lease_available": bool(primary_media.get("url") or primary_media.get("urlToken")),
        "collection_notes": [],
    }


def _find_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("objectDesc"), dict):
        return value
    if isinstance(value.get("object"), dict):
        return value["object"]
    for key in ("data", "response"):
        found = _find_object(value.get(key))
        if found is not None:
            return found
    return None


def _clean_caption(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"</?em\b[^>]*>", "", text, flags=re.IGNORECASE)
    return html.unescape(text).strip()


def _canonical_method(method_key: str) -> str:
    aliases = {
        "wechat_channels_search": "search",
        "channels_search": "search",
        "video_search": "search",
        "wechat_channels_detail": "detail",
        "channels_detail": "detail",
        "detail": "detail",
        "wechat_channels_author_feed": "author_feed",
        "channels_author_feed": "author_feed",
        "author_feed": "author_feed",
    }
    return aliases.get(method_key.strip().lower(), method_key.strip().lower())


def _validate_config(config: ChannelsRemoteConfig) -> None:
    if not config.worker_id.strip() or not config.shared_secret.strip():
        raise ProviderConfigError("worker_id and shared_secret are required")
    ssl_context = _server_ssl_context(config.tls_cert, config.tls_key)
    if not _is_loopback_host(config.host) and ssl_context is None and not config.allow_insecure_lan:
        raise ProviderConfigError(
            "non-loopback Channels Hub requires TLS; allow insecure LAN only for a controlled PoC"
        )


def _positive_int(value: Any, *, default: int, label: str) -> int:
    try:
        result = int(value or default)
    except (TypeError, ValueError) as exc:
        raise ProviderInputError(f"{label} must be an integer") from exc
    if result < 1:
        raise ProviderInputError(f"{label} must be positive")
    return result


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _media_duration_ms(media: dict[str, Any], spec: dict[str, Any]) -> int:
    duration_ms = _int(media.get("durationMs") or spec.get("durationMs"))
    if duration_ms:
        return duration_ms
    play_length = _int(media.get("videoPlayLen") or spec.get("videoPlayLen"))
    return play_length * 1000


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError as exc:
        raise ProviderConfigError(f"{key} must be an integer") from exc


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError as exc:
        raise ProviderConfigError(f"{key} must be numeric") from exc


def _env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    if value.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if value.strip().lower() in {"0", "false", "no", "off"}:
        return False
    raise ProviderConfigError(f"{key} must be boolean")
