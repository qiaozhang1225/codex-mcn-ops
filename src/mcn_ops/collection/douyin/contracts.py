from __future__ import annotations

from typing import Any, Protocol, TypedDict, runtime_checkable


CONTRACT_VERSION = "v1"


class PagingPayload(TypedDict):
    has_next: bool
    cursor: str | None
    next_cursor: str | None
    offset: str | None
    search_id: str | None
    page: int | None
    captured_pages: int
    captured_items: int
    stop_reason: str
    request_satisfied: bool
    source_exhausted: bool
    raw: dict[str, Any]


class ProviderResult(TypedDict, total=False):
    ok: bool
    provider: str
    method_key: str
    endpoint: str | None
    paging: PagingPayload
    normalized: dict[str, Any]
    raw: dict[str, Any]
    cache_hit: bool
    fallback: dict[str, Any] | None
    usage: dict[str, Any]
    error: str


@runtime_checkable
class DouyinProvider(Protocol):
    provider_name: str

    def call(
        self,
        method_key: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ProviderResult: ...


@runtime_checkable
class TranscriptionProvider(Protocol):
    provider_name: str

    def transcribe(
        self,
        source: str,
        *,
        source_package: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ProviderResult: ...


def empty_paging() -> PagingPayload:
    return {
        "has_next": False,
        "cursor": None,
        "next_cursor": None,
        "offset": None,
        "search_id": None,
        "page": None,
        "captured_pages": 0,
        "captured_items": 0,
        "stop_reason": "not_applicable",
        "request_satisfied": True,
        "source_exhausted": True,
        "raw": {},
    }


def normalize_paging(
    paging: dict[str, Any] | None,
    *,
    captured_items: int | None = None,
) -> PagingPayload:
    """Return the provider-neutral traversal contract for any paging payload."""
    source = dict(paging or {})
    raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
    browser_aggregated = bool(raw.get("browser_aggregated"))
    has_next = bool(source.get("has_next"))
    cursor = source.get("next_cursor") or source.get("cursor")
    pages = _non_negative_int(
        raw.get("pages_captured") if browser_aggregated else source.get("captured_pages"),
        default=0 if source.get("stop_reason") == "not_applicable" else 1,
    )
    item_count = _non_negative_int(
        raw.get("unique_items") if browser_aggregated else source.get("captured_items"),
        default=max(0, int(captured_items or 0)),
    )
    stop_reason = str(
        raw.get("stop_reason") if browser_aggregated else source.get("stop_reason") or ""
    ).strip()
    if not stop_reason:
        stop_reason = "page_boundary" if has_next else "no_next_page"
    request_satisfied = source.get("request_satisfied")
    if request_satisfied is None:
        request_satisfied = stop_reason not in {
            "active_pagination_unavailable",
            "idle_scroll_limit",
            "signed_page_request_failed",
            "task_space_released",
        }
    source_exhausted = source.get("source_exhausted")
    if source_exhausted is None:
        source_exhausted = not has_next and stop_reason in {"no_next_page", "not_applicable"}
    return {
        "has_next": has_next,
        "cursor": str(cursor) if cursor not in (None, "") else None,
        "next_cursor": str(cursor) if cursor not in (None, "") else None,
        "offset": str(source.get("offset")) if source.get("offset") not in (None, "") else None,
        "search_id": str(source.get("search_id")) if source.get("search_id") not in (None, "") else None,
        "page": source.get("page"),
        "captured_pages": pages,
        "captured_items": item_count,
        "stop_reason": stop_reason,
        "request_satisfied": bool(request_satisfied),
        "source_exhausted": bool(source_exhausted),
        "raw": dict(raw),
    }


def _non_negative_int(value: Any, *, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def build_provider_result(
    *,
    provider: str,
    method_key: str,
    normalized: dict[str, Any] | None = None,
    raw: dict[str, Any] | None = None,
    paging: PagingPayload | None = None,
    endpoint: str | None = None,
    cache_hit: bool = False,
    fallback: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
) -> ProviderResult:
    result: ProviderResult = {
        "ok": True,
        "provider": provider,
        "method_key": method_key,
        "endpoint": endpoint,
        "paging": normalize_paging(paging) if paging is not None else empty_paging(),
        "normalized": normalized or {},
        "raw": raw or {},
        "cache_hit": cache_hit,
        "fallback": fallback,
    }
    if usage is not None:
        result["usage"] = usage
    return result


def provider_cache_namespace(provider: str, operation: str) -> str:
    provider = provider.strip().lower()
    operation = operation.strip().lower()
    if not provider or not operation:
        raise ValueError("provider and operation are required")
    return f"{provider}:{CONTRACT_VERSION}:{operation}"
