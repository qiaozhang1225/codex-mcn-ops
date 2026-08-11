from __future__ import annotations

from typing import Any

import pytest

from mcn_ops.collection.douyin.contracts import build_provider_result
from mcn_ops.collection.douyin.errors import (
    ProviderConfigError,
    ProviderRateLimitError,
    TranscriptionInputError,
)
from mcn_ops.collection.douyin.registry import build_douyin_registry
from mcn_ops.collection.douyin.router import ProviderRouter


class FakeProvider:
    def __init__(self, name: str, *, result=None, error: Exception | None = None) -> None:
        self.provider_name = name
        self.result = result or build_provider_result(provider=name, method_key="test")
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def call(self, method_key, params=None, body=None, use_cache=True):
        self.calls.append({"method_key": method_key, "params": params, "body": body, "use_cache": use_cache})
        if self.error:
            raise self.error
        result = dict(self.result)
        result["method_key"] = method_key
        return result


class FakeTranscriber:
    provider_name = "fake-asr"

    def __init__(self) -> None:
        self.sources: list[str] = []
        self.source_packages: list[dict[str, Any] | None] = []

    def transcribe(self, source, *, source_package=None, use_cache=True):
        self.sources.append(source)
        self.source_packages.append(source_package)
        return build_provider_result(
            provider=self.provider_name,
            method_key="transcribe",
            normalized={"text": "离线转写"},
        )


def test_router_returns_direct_result_without_touching_mxnzp() -> None:
    direct = FakeProvider("direct")
    mxnzp = FakeProvider("mxnzp")

    result = ProviderRouter(direct, mxnzp, allow_paid_fallback=True).call("detail_v4", body={"url": "x"})

    assert result["provider"] == "direct"
    assert len(direct.calls) == 1
    assert mxnzp.calls == []


def test_router_only_falls_back_for_allowed_provider_errors_and_explicit_opt_in() -> None:
    direct = FakeProvider("direct", error=ProviderRateLimitError("limited"))
    mxnzp = FakeProvider("mxnzp")

    result = ProviderRouter(direct, mxnzp, allow_paid_fallback=True).call("video_search")

    assert result["provider"] == "mxnzp"
    assert result["fallback"] == {
        "attempted": True,
        "from": "direct",
        "to": "mxnzp",
        "reason_code": "provider_rate_limited",
    }
    assert len(mxnzp.calls) == 1


@pytest.mark.parametrize("error", [ProviderConfigError("bad config"), TranscriptionInputError("bad input")])
def test_router_never_falls_back_for_config_or_input_errors(error: Exception) -> None:
    direct = FakeProvider("direct", error=error)
    mxnzp = FakeProvider("mxnzp")

    with pytest.raises(type(error)):
        ProviderRouter(direct, mxnzp, allow_paid_fallback=True).call("detail_v4")

    assert mxnzp.calls == []


def test_router_does_not_use_paid_fallback_without_explicit_opt_in() -> None:
    direct = FakeProvider("direct", error=ProviderRateLimitError("limited"))
    mxnzp = FakeProvider("mxnzp")

    with pytest.raises(ProviderRateLimitError):
        ProviderRouter(direct, mxnzp, allow_paid_fallback=False).call("video_search")

    assert mxnzp.calls == []


def test_registry_maps_stable_tools_to_provider_and_transcriber() -> None:
    direct = FakeProvider("direct")
    transcriber = FakeTranscriber()
    registry = build_douyin_registry(direct, transcription_provider=transcriber)

    registry.run("douyin_search_videos", {"keyword": "财运", "offset": "12", "search_id": "s1"})
    source_package = {"work_id": "123", "audio_url": "https://media.example/audio.mp3"}
    transcript = registry.run(
        "douyin_extract_video_text",
        {"url": "https://v.douyin.com/test", "source_package": source_package},
    )

    assert direct.calls[0] == {
        "method_key": "video_search",
        "params": {"keyword": "财运", "offset": "12", "search_id": "s1"},
        "body": None,
        "use_cache": True,
    }
    assert transcriber.sources == ["https://v.douyin.com/test"]
    assert transcriber.source_packages == [source_package]
    assert transcript["normalized"]["text"] == "离线转写"
