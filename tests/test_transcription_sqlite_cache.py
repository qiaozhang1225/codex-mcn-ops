from __future__ import annotations

from mcn_ops.collection.douyin.contracts import build_provider_result
from mcn_ops.collection.transcription.sqlite_cache import SqliteTranscriptionCache


def test_sqlite_cache_survives_new_instance(tmp_path) -> None:
    path = tmp_path / "asr.sqlite"
    result = build_provider_result(
        provider="aliyun-qwen-asr",
        method_key="transcribe",
        normalized={"text": "缓存文案"},
    )

    SqliteTranscriptionCache(path).put("audio-key", result)
    cached = SqliteTranscriptionCache(path).get("audio-key")

    assert cached == result
    assert path.exists()


def test_sqlite_cache_returns_independent_copy(tmp_path) -> None:
    path = tmp_path / "asr.sqlite"
    result = build_provider_result(
        provider="aliyun-qwen-asr",
        method_key="transcribe",
        normalized={"text": "original"},
    )
    cache = SqliteTranscriptionCache(path)
    cache.put("audio-key", result)

    first = cache.get("audio-key")
    assert first is not None
    first["normalized"]["text"] = "changed"

    second = cache.get("audio-key")
    assert second is not None
    assert second["normalized"]["text"] == "original"


def test_sqlite_cache_persists_and_clears_async_job(tmp_path) -> None:
    path = tmp_path / "asr.sqlite"
    SqliteTranscriptionCache(path).put_job(
        "audio-key",
        "task-123",
        uploaded_url="https://bucket.example.com/audio.mp3?signature=fake",
    )

    second_process = SqliteTranscriptionCache(path)
    assert second_process.get_job("audio-key") == {
        "task_id": "task-123",
        "status": "submitted",
        "uploaded_url": "https://bucket.example.com/audio.mp3?signature=fake",
    }

    second_process.delete_job("audio-key")
    assert SqliteTranscriptionCache(path).get_job("audio-key") is None
