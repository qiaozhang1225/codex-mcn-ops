from __future__ import annotations

import json
import sqlite3

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
    }

    second_process.delete_job("audio-key")
    assert SqliteTranscriptionCache(path).get_job("audio-key") is None


def test_sqlite_cache_never_persists_credentials_or_signed_media_urls(tmp_path) -> None:
    path = tmp_path / "asr.sqlite"
    result = build_provider_result(
        provider="aliyun-qwen-asr",
        method_key="transcribe",
        normalized={
            "text": "safe transcript",
            "source_package": {
                "work_id": "123",
                "audio_url": "https://media.example/audio.mp3?signature=temporary",
                "video_url": "https://media.example/video.mp4?a_bogus=secret",
                "cookie": "sessionid=secret",
                "api_key": "sk-secret",
            },
        },
    )

    SqliteTranscriptionCache(path).put("audio-key", result)
    serialized = path.read_bytes()

    assert b"safe transcript" in serialized
    assert b"signature=temporary" not in serialized
    assert b"a_bogus" not in serialized
    assert b"sessionid=secret" not in serialized
    assert b"sk-secret" not in serialized


def test_sqlite_cache_scrubs_legacy_signed_urls_on_upgrade(tmp_path) -> None:
    path = tmp_path / "asr.sqlite"
    cache = SqliteTranscriptionCache(path)
    cache.put(
        "legacy-key",
        build_provider_result(
            provider="aliyun-qwen-asr",
            method_key="transcribe",
            normalized={"text": "legacy"},
        ),
    )
    unsafe = build_provider_result(
        provider="aliyun-qwen-asr",
        method_key="transcribe",
        normalized={
            "text": "legacy",
            "source_package": {
                "audio_url": "https://media.example/audio.mp3?signature=legacy"
            },
        },
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE transcription_cache SET result_json = ? WHERE cache_key = ?",
            (json.dumps(unsafe), "legacy-key"),
        )
        connection.execute(
            "INSERT INTO transcription_jobs (cache_key, task_id, status, uploaded_url) "
            "VALUES ('legacy-job', 'task-1', 'submitted', "
            "'https://bucket.example/audio.mp3?signature=legacy')"
        )
        connection.execute("PRAGMA user_version = 1")

    upgraded = SqliteTranscriptionCache(path)
    assert upgraded.get("legacy-key")["normalized"]["source_package"] == {}
    assert upgraded.get_job("legacy-job") == {"task_id": "task-1", "status": "submitted"}
    assert b"signature=legacy" not in path.read_bytes()
