from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

from ..douyin.contracts import ProviderResult


class SqliteTranscriptionCache:
    """Persistent ASR result cache shared by separate CLI invocations."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get(self, key: str) -> ProviderResult | None:
        self._initialize()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT result_json FROM transcription_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE transcription_cache
                SET hit_count = hit_count + 1, last_hit_at = CURRENT_TIMESTAMP
                WHERE cache_key = ?
                """,
                (key,),
            )
        value = json.loads(str(row[0]))
        if not isinstance(value, dict):
            return None
        return copy.deepcopy(value)

    def put(self, key: str, result: ProviderResult) -> None:
        self._initialize()
        serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO transcription_cache (cache_key, result_json)
                VALUES (?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    result_json = excluded.result_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, serialized),
            )

    def get_job(self, key: str) -> dict[str, str] | None:
        self._initialize()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT task_id, status, uploaded_url FROM transcription_jobs WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        result = {"task_id": str(row[0]), "status": str(row[1])}
        if row[2]:
            result["uploaded_url"] = str(row[2])
        return result

    def put_job(
        self,
        key: str,
        task_id: str,
        *,
        status: str = "submitted",
        uploaded_url: str | None = None,
    ) -> None:
        self._initialize()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO transcription_jobs (cache_key, task_id, status, uploaded_url)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    task_id = excluded.task_id,
                    status = excluded.status,
                    uploaded_url = excluded.uploaded_url,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, task_id, status, uploaded_url),
            )

    def delete_job(self, key: str) -> None:
        self._initialize()
        with sqlite3.connect(self.path) as connection:
            connection.execute("DELETE FROM transcription_jobs WHERE cache_key = ?", (key,))

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS transcription_cache (
                    cache_key TEXT PRIMARY KEY,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_hit_at TEXT,
                    hit_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS transcription_jobs (
                    cache_key TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    uploaded_url TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(transcription_jobs)").fetchall()
            }
            if "uploaded_url" not in columns:
                connection.execute("ALTER TABLE transcription_jobs ADD COLUMN uploaded_url TEXT")
