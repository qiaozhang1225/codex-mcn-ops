from __future__ import annotations

from mcn_ops.collection.douyin.contracts import build_provider_result
import mcn_ops.collection.douyin.factory as factory
from mcn_ops.collection.douyin.factory import TranscribingDouyinProvider
from mcn_ops.collection.douyin.registry import build_douyin_registry


class FakeData:
    provider_name = "direct"

    def call(self, method_key, params=None, body=None, use_cache=True):
        return build_provider_result(provider="direct", method_key=method_key)


class FakeBrowserData(FakeData):
    browser_pagination = True

    def __init__(self) -> None:
        self.params = None

    def call(self, method_key, params=None, body=None, use_cache=True):
        self.params = params
        return super().call(method_key, params=params, body=body, use_cache=use_cache)


class FakeTranscription:
    provider_name = "fake-asr"

    def transcribe(self, source, *, source_package=None, use_cache=True):
        return build_provider_result(
            provider="fake-asr",
            method_key="video_to_text_v2",
            normalized={"text": source},
        )


def test_composed_provider_routes_only_transcription_calls() -> None:
    provider = TranscribingDouyinProvider(
        data_provider=FakeData(),
        transcription_provider=FakeTranscription(),
    )

    assert provider.call("detail_v4")["provider"] == "direct"
    transcribed = provider.call("video_to_text_v2", body={"url": "https://example.com/audio.mp3"})
    assert transcribed["provider"] == "fake-asr"
    assert transcribed["normalized"]["text"] == "https://example.com/audio.mp3"


def test_provider_default_does_not_implicitly_enable_paid_asr(monkeypatch) -> None:
    data_provider = FakeData()
    monkeypatch.setattr(factory, "build_data_provider", lambda *args, **kwargs: data_provider)

    provider = factory.build_collection_provider(
        "direct",
        transcription_provider_name="provider",
    )

    assert provider.transcription_provider is None
    assert provider.call("video_to_text_v2")["provider"] == "direct"


def test_registry_passes_browser_page_limits_only_to_browser_provider() -> None:
    data_provider = FakeBrowserData()
    provider = TranscribingDouyinProvider(data_provider=data_provider)
    registry = build_douyin_registry(provider)

    registry.run(
        "douyin_search_videos",
        {"keyword": "亲子关系", "offset": "0", "max_pages": 6, "max_items": 80},
    )

    assert data_provider.params["max_pages"] == 6
    assert data_provider.params["max_items"] == 80
