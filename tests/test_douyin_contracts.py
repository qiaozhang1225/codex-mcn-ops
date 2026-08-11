from __future__ import annotations

import pytest

from mcn_ops.collection.douyin.contracts import build_provider_result, provider_cache_namespace
from mcn_ops.collection.douyin.errors import ProviderConfigError, ProviderRateLimitError


def test_provider_result_has_stable_envelope() -> None:
    result = build_provider_result(
        provider="direct",
        method_key="video_search",
        normalized={"items": []},
    )

    assert result == {
        "ok": True,
        "provider": "direct",
        "method_key": "video_search",
        "endpoint": None,
        "paging": {
            "has_next": False,
            "cursor": None,
            "offset": None,
            "search_id": None,
            "page": None,
            "raw": {},
        },
        "normalized": {"items": []},
        "raw": {},
        "cache_hit": False,
        "fallback": None,
    }


def test_provider_cache_namespace_separates_paid_and_direct_calls() -> None:
    direct = provider_cache_namespace("direct", "video_search")
    mxnzp = provider_cache_namespace("mxnzp", "video_search")

    assert direct == "direct:v1:video_search"
    assert direct != mxnzp


def test_only_transient_provider_errors_allow_fallback() -> None:
    assert ProviderRateLimitError.fallback_allowed is True
    assert ProviderConfigError.fallback_allowed is False


def test_provider_cache_namespace_rejects_empty_parts() -> None:
    with pytest.raises(ValueError):
        provider_cache_namespace("", "video_search")
