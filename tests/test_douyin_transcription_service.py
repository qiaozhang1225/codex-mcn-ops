from __future__ import annotations

from mcn_ops.collection.douyin.contracts import build_provider_result
from mcn_ops.collection.transcription.service import DouyinTranscriptionService


class FakeDataProvider:
    provider_name = "direct"

    def __init__(self) -> None:
        self.calls = 0

    def call(self, method_key, params=None, body=None, use_cache=True):
        self.calls += 1
        assert method_key == "detail_v4"
        return build_provider_result(
            provider="direct",
            method_key=method_key,
            normalized={
                "source_package": {
                    "work_id": "123",
                    "title": "authoritative title",
                    "audio_url": "https://cdn.example.com/audio.mp3",
                }
            },
        )


class FakeTranscriptionProvider:
    provider_name = "fake-asr"

    def __init__(self):
        self.seen_source = None

    def transcribe(self, source, *, source_package=None, use_cache=True):
        self.seen_source = source
        return build_provider_result(
            provider="fake-asr",
            method_key="douyin_extract_video_text",
            normalized={
                "text": "完整文案",
                "source_package": {
                    "title": "sparse ASR title",
                    "transcript_text": "完整文案",
                },
            },
        )


def test_service_resolves_audio_before_transcription_and_preserves_metadata() -> None:
    asr = FakeTranscriptionProvider()
    service = DouyinTranscriptionService(
        data_provider=FakeDataProvider(),
        transcription_provider=asr,
    )

    result = service.transcribe("https://v.douyin.com/example/")

    assert asr.seen_source == "https://cdn.example.com/audio.mp3"
    assert result["method_key"] == "video_to_text_v2"
    assert result["normalized"]["text"] == "完整文案"
    assert result["normalized"]["source_package"]["title"] == "authoritative title"
    assert result["normalized"]["source_package"]["work_id"] == "123"


def test_service_uses_supplied_detail_package_without_fetching_detail_again() -> None:
    data = FakeDataProvider()
    asr = FakeTranscriptionProvider()
    service = DouyinTranscriptionService(data_provider=data, transcription_provider=asr)
    package = {
        "work_id": "123",
        "title": "already verified",
        "audio_url": "https://cdn.example.com/audio.mp3?signature=temporary",
    }

    result = service.transcribe(
        "https://www.douyin.com/video/123",
        source_package=package,
    )

    assert data.calls == 0
    assert asr.seen_source == package["audio_url"]
    assert result["normalized"]["source_package"]["title"] == "already verified"
