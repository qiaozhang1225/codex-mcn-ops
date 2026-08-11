from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from mcn_ops.collection.douyin.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    TranscriptionInputError,
)
from mcn_ops.collection.transcription.aliyun import (
    AliyunTranscriptionConfig,
    AliyunTranscriptionProvider,
    HttpResponse,
    normalize_long_transcription,
    scrub_sensitive,
)
from mcn_ops.collection.transcription.cache import transcription_cache_key
from mcn_ops.collection.transcription.local_whisper import LocalWhisperAdapter
from mcn_ops.collection.transcription.media import (
    PreparedMedia,
    normalize_prepared_media,
    validate_public_https_url,
    validate_resolved_public_https_url,
)
from mcn_ops.collection.transcription.sqlite_cache import SqliteTranscriptionCache


FIXTURES = Path(__file__).parent / "fixtures" / "aliyun_asr"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def make_media(tmp_path: Path, *, duration: float, content: bytes = b"fake-audio") -> PreparedMedia:
    directory = tmp_path / f"media-{duration}"
    directory.mkdir()
    path = directory / "audio.mp3"
    path.write_bytes(content)
    return PreparedMedia(
        path=path,
        duration_seconds=duration,
        size_bytes=len(content),
        mime_type="audio/mpeg",
        sha256="a" * 64,
        source_url="https://media.example.com/audio.mp3",
        temporary_directory=directory,
    )


class SequenceTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body, "timeout": timeout})
        assert self.responses, f"unexpected request: {method} {url}"
        return self.responses.pop(0)


def config(**overrides) -> AliyunTranscriptionConfig:
    values = {
        "api_key": "sk-super-secret-key",
        "workspace_id": "workspace-test",
        "base_url": "https://workspace-test.cn-beijing.maas.aliyuncs.com",
        "poll_interval_seconds": 0,
    }
    values.update(overrides)
    return AliyunTranscriptionConfig(**values)


def test_short_audio_uses_base64_contract_and_cache(tmp_path: Path) -> None:
    media = make_media(tmp_path, duration=42)
    transport = SequenceTransport([HttpResponse(200, fixture("short_success.json"))])
    provider = AliyunTranscriptionProvider(config(), transport=transport, media_preparer=lambda source: media)

    result = provider.transcribe(
        "https://media.example.com/audio.mp3",
        source_package={"work_id": "123", "title": "测试"},
    )

    assert result["normalized"]["text"] == "旺自己，要先稳住自己的能量。"
    assert result["normalized"]["source_package"]["transcript_text"] == result["normalized"]["text"]
    assert result["usage"]["audio_seconds"] == 42
    assert result["usage"]["estimated_cost_cny"] == pytest.approx(0.00924)
    request = json.loads(transport.calls[0]["body"])
    assert request["model"] == "qwen3-asr-flash"
    audio = request["messages"][0]["content"][0]["input_audio"]["data"]
    assert audio.startswith("data:audio/mpeg;base64,")
    assert "sk-super-secret-key" not in json.dumps(result)
    assert not media.path.exists(), "provider must clean its prepared temporary media"

    cached_media = make_media(tmp_path, duration=42)
    provider.media_preparer = lambda source: cached_media
    cached = provider.transcribe("https://media.example.com/changed-signature.mp3")
    assert cached["cache_hit"] is True
    assert len(transport.calls) == 1
    assert not cached_media.path.exists()


def test_long_audio_submits_polls_and_normalizes_segments(tmp_path: Path) -> None:
    media = make_media(tmp_path, duration=361)
    transport = SequenceTransport(
        [
            HttpResponse(200, fixture("long_submit.json")),
            HttpResponse(200, fixture("long_running.json")),
            HttpResponse(200, fixture("long_succeeded.json")),
            HttpResponse(200, fixture("long_result.json")),
        ]
    )
    provider = AliyunTranscriptionProvider(config(), transport=transport, media_preparer=lambda source: media)

    result = provider.transcribe("https://media.example.com/long.mp3?token=private")

    assert result["normalized"]["text"] == "第一句话。第二句话。"
    assert result["normalized"]["segments"] == [
        {"text": "第一句话。", "begin_time_ms": 0, "end_time_ms": 1500, "emotion": "neutral"},
        {"text": "第二句话。", "begin_time_ms": 1500, "end_time_ms": 3200, "emotion": "neutral"},
    ]
    submit = json.loads(transport.calls[0]["body"])
    assert submit["model"] == "qwen3-asr-flash-filetrans"
    assert submit["input"]["file_url"].endswith("?token=private")
    assert [call["method"] for call in transport.calls] == ["POST", "GET", "GET", "GET"]
    assert transport.calls[-1]["headers"] == {"Content-Type": "application/json"}
    assert "Signature=secret" not in json.dumps(result)


def test_long_local_audio_uses_uploader_and_cleans_remote(tmp_path: Path) -> None:
    media = make_media(tmp_path, duration=400)
    uploaded: list[str] = []
    cleaned: list[str] = []
    transport = SequenceTransport(
        [
            HttpResponse(200, fixture("long_submit.json")),
            HttpResponse(200, fixture("long_succeeded.json")),
            HttpResponse(200, fixture("long_result.json")),
        ]
    )

    def uploader(path: Path) -> str:
        assert path == media.path
        url = "https://bucket.example.com/private/audio.mp3?signature=secret"
        uploaded.append(url)
        return url

    provider = AliyunTranscriptionProvider(
        config(),
        transport=transport,
        media_preparer=lambda source: media,
        url_uploader=uploader,
        uploaded_url_cleanup=cleaned.append,
    )
    result = provider.transcribe(str(tmp_path / "local.mp3"))

    assert result["ok"] is True
    assert cleaned == uploaded


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ProviderAuthError),
        (429, ProviderRateLimitError),
        (503, ProviderUnavailableError),
    ],
)
def test_http_failures_are_typed_and_secrets_are_scrubbed(tmp_path: Path, status: int, expected: type[Exception]) -> None:
    media = make_media(tmp_path, duration=10)
    transport = SequenceTransport([HttpResponse(status, fixture("error_auth.json"))])
    provider = AliyunTranscriptionProvider(config(), transport=transport, media_preparer=lambda source: media)

    with pytest.raises(expected) as caught:
        provider.transcribe("https://media.example.com/audio.mp3")

    assert "sk-this-must-be-redacted" not in str(caught.value)
    assert "sk-this-must-be-redacted" not in str(getattr(caught.value, "detail", ""))


def test_timeout_is_typed_and_temporary_media_is_cleaned(tmp_path: Path) -> None:
    media = make_media(tmp_path, duration=10)

    def timeout_transport(*args):
        raise TimeoutError("Bearer sk-super-secret-key timed out")

    provider = AliyunTranscriptionProvider(config(), transport=timeout_transport, media_preparer=lambda source: media)
    with pytest.raises(ProviderUnavailableError):
        provider.transcribe("https://media.example.com/audio.mp3")
    assert not media.path.exists()


def test_cache_key_is_stable_and_provider_aware() -> None:
    first = transcription_cache_key(
        audio_sha256="A" * 64,
        provider="aliyun-qwen-asr",
        model="qwen3-asr-flash",
        options={"language": "zh", "enable_itn": False},
    )
    same = transcription_cache_key(
        audio_sha256="a" * 64,
        provider="ALIYUN-QWEN-ASR",
        model="qwen3-asr-flash",
        options={"enable_itn": False, "language": "zh"},
    )
    other = transcription_cache_key(
        audio_sha256="a" * 64,
        provider="local-whisper",
        model="qwen3-asr-flash",
        options={"enable_itn": False, "language": "zh"},
    )
    assert first == same
    assert first != other


def test_long_result_can_fall_back_to_sentence_text() -> None:
    text, segments, language = normalize_long_transcription(
        {
            "transcripts": [
                {
                    "sentences": [
                        {"begin_time": 1, "end_time": 2, "text": "只有分句。", "language": "zh"}
                    ]
                }
            ]
        }
    )
    assert text == "只有分句。"
    assert segments[0]["begin_time_ms"] == 1
    assert language == "zh"


def test_url_validation_rejects_non_https_and_private_addresses() -> None:
    for url in ["http://example.com/a.mp3", "https://localhost/a.mp3", "https://127.0.0.1/a.mp3"]:
        with pytest.raises(TranscriptionInputError):
            validate_public_https_url(url)


def test_url_validation_rejects_domain_resolving_to_private_address(monkeypatch) -> None:
    monkeypatch.setattr(
        "mcn_ops.collection.transcription.media.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )

    with pytest.raises(TranscriptionInputError):
        validate_resolved_public_https_url("https://media.example.com/audio.mp3")


def test_url_validation_allows_clash_fake_ip_for_trusted_douyin_cdn(monkeypatch) -> None:
    monkeypatch.setattr(
        "mcn_ops.collection.transcription.media.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("198.18.0.10", 443))],
    )

    validate_resolved_public_https_url(
        "https://sf11-cdn-tos.douyinstatic.com/obj/ies-music/audio.mp3"
    )


def test_url_validation_rejects_clash_fake_ip_for_untrusted_host(monkeypatch) -> None:
    monkeypatch.setattr(
        "mcn_ops.collection.transcription.media.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("198.18.0.10", 443))],
    )

    with pytest.raises(TranscriptionInputError):
        validate_resolved_public_https_url("https://attacker.example/audio.mp3")


def test_non_json_rate_limit_response_is_still_typed(tmp_path: Path) -> None:
    media = make_media(tmp_path, duration=10)
    transport = SequenceTransport([HttpResponse(429, b"rate limited")])
    provider = AliyunTranscriptionProvider(config(), transport=transport, media_preparer=lambda source: media)

    with pytest.raises(ProviderRateLimitError):
        provider.transcribe("https://media.example.com/audio.mp3")


def test_video_container_is_normalized_to_mp3(monkeypatch, tmp_path: Path) -> None:
    source_dir = tmp_path / "video"
    source_dir.mkdir()
    video = source_dir / "input.mp4"
    video.write_bytes(b"video")
    media = PreparedMedia(
        path=video,
        duration_seconds=20,
        size_bytes=5,
        mime_type="video/mp4",
        sha256="v" * 64,
        source_url="https://media.example.com/video.mp4",
        temporary_directory=source_dir,
    )

    def fake_normalize(source: Path, destination: Path):
        assert source == video
        destination.write_bytes(b"mp3")
        return destination

    monkeypatch.setattr("mcn_ops.collection.transcription.media.normalize_audio", fake_normalize)
    normalized = normalize_prepared_media(media)

    assert normalized.mime_type == "audio/mpeg"
    assert normalized.path.name == "normalized.mp3"
    assert normalized.source_url is None


def test_long_task_resumes_persisted_task_id_without_resubmitting(tmp_path: Path) -> None:
    cache = SqliteTranscriptionCache(tmp_path / "resume.sqlite")
    uploaded_url = "https://bucket.example.com/resume.mp3?signature=fake"
    cleaned: list[str] = []
    first_media = make_media(tmp_path, duration=361, content=b"same-long-audio")
    first_transport = SequenceTransport(
        [HttpResponse(200, fixture("long_submit.json")), HttpResponse(200, fixture("long_running.json"))]
    )
    first_clock = iter([0.0, 0.0, 2.0])
    first = AliyunTranscriptionProvider(
        config(poll_timeout_seconds=1),
        transport=first_transport,
        media_preparer=lambda source: first_media,
        cache=cache,
        url_uploader=lambda path: uploaded_url,
        uploaded_url_cleanup=cleaned.append,
        monotonic=lambda: next(first_clock),
    )

    with pytest.raises(ProviderUnavailableError, match="polling timed out"):
        first.transcribe(str(tmp_path / "local-long.mp3"))
    assert len(first_transport.calls) == 2
    assert cleaned == [], "a running cloud task must retain its uploaded media"

    second_media = make_media(tmp_path, duration=361, content=b"same-long-audio")
    second_transport = SequenceTransport(
        [HttpResponse(200, fixture("long_succeeded.json")), HttpResponse(200, fixture("long_result.json"))]
    )
    second = AliyunTranscriptionProvider(
        config(),
        transport=second_transport,
        media_preparer=lambda source: second_media,
        cache=SqliteTranscriptionCache(tmp_path / "resume.sqlite"),
        url_uploader=lambda path: (_ for _ in ()).throw(AssertionError("must reuse persisted upload")),
        uploaded_url_cleanup=cleaned.append,
    )
    result = second.transcribe(str(tmp_path / "local-long.mp3"))

    assert result["normalized"]["text"] == "第一句话。第二句话。"
    assert [call["method"] for call in second_transport.calls] == ["GET", "GET"]
    key = transcription_cache_key(
        audio_sha256="a" * 64,
        provider="aliyun-qwen-asr",
        model="qwen3-asr-flash-filetrans",
        options={"enable_itn": False, "enable_words": False, "language": "zh"},
    )
    assert cache.get_job(key) is None
    assert cleaned == [uploaded_url]


def test_recursive_scrubbing_removes_keys_tokens_and_signed_queries() -> None:
    scrubbed = scrub_sensitive(
        {
            "authorization": "Bearer sk-secret-value",
            "result_url": "https://example.com/result.json?Signature=secret",
            "message": "request Bearer abc and sk-1234567890 failed",
        }
    )
    serialized = json.dumps(scrubbed)
    assert "Signature" not in serialized
    assert "sk-1234567890" not in serialized
    assert "Bearer abc" not in serialized


def test_local_whisper_adapter_reads_cli_output_and_cleans_temp(tmp_path: Path) -> None:
    media = tmp_path / "speech.mp3"
    media.write_bytes(b"audio")
    seen: dict[str, object] = {}

    def runner(command, **kwargs):
        seen["command"] = command
        output_dir = Path(command[command.index("--output-dir") + 1])
        output_dir.joinpath("transcript.txt").write_text("本地转写文本。", encoding="utf-8")
        seen["output_dir"] = output_dir
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    adapter = LocalWhisperAdapter(runner=runner)
    result = adapter.transcribe(str(media), source_package={"work_id": "work-1"})

    assert result["normalized"]["text"] == "本地转写文本。"
    assert result["normalized"]["source_package"]["work_id"] == "work-1"
    assert result["usage"]["cloud_cost_cny"] == 0
    assert not Path(seen["output_dir"]).exists()
