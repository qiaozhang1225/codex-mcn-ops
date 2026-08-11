from __future__ import annotations

from typing import Any, Protocol, TypedDict, runtime_checkable


CONTRACT_VERSION = "v1"


class PagingPayload(TypedDict):
    has_next: bool
    cursor: str | None
    offset: str | None
    search_id: str | None
    page: int | None
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
        "offset": None,
        "search_id": None,
        "page": None,
        "raw": {},
    }


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
        "paging": paging or empty_paging(),
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
