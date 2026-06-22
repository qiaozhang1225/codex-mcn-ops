from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = Path("data/mcn_ops.sqlite")


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ip_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    positioning TEXT NOT NULL DEFAULT '',
    keywords_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_packages (
    id TEXT PRIMARY KEY,
    ip_profile_id TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    media_paths_json TEXT NOT NULL DEFAULT '[]',
    cover_path TEXT,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(ip_profile_id) REFERENCES ip_profiles(id)
);

CREATE TABLE IF NOT EXISTS publish_jobs (
    id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    device_serial TEXT,
    status TEXT NOT NULL DEFAULT 'prepared',
    stop_before_submit INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(content_id) REFERENCES content_packages(id)
);

CREATE TABLE IF NOT EXISTS android_devices (
    serial TEXT PRIMARY KEY,
    label TEXT NOT NULL DEFAULT '',
    model TEXT,
    status TEXT NOT NULL DEFAULT 'unknown',
    last_seen_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_accounts (
    id TEXT PRIMARY KEY,
    device_serial TEXT NOT NULL,
    platform TEXT NOT NULL,
    account_label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown',
    last_checked_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(device_serial) REFERENCES android_devices(serial)
);

CREATE TABLE IF NOT EXISTS publish_run_logs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    device_serial TEXT,
    step_name TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    artifact_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES publish_jobs(id)
);

CREATE TABLE IF NOT EXISTS tracking_snapshots (
    id TEXT PRIMARY KEY,
    publish_job_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    result_url TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'manual',
    captured_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(publish_job_id) REFERENCES publish_jobs(id)
);

CREATE TABLE IF NOT EXISTS ip_roles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    positioning TEXT NOT NULL DEFAULT '',
    target_directions_json TEXT NOT NULL DEFAULT '[]',
    search_keywords_json TEXT NOT NULL DEFAULT '[]',
    avoid_directions_json TEXT NOT NULL DEFAULT '[]',
    preferred_content_json TEXT NOT NULL DEFAULT '[]',
    forbidden_content_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_tasks (
    id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    target_scope TEXT NOT NULL,
    target_count_per_role INTEGER NOT NULL,
    topic TEXT,
    status TEXT NOT NULL,
    parsed_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}',
    error TEXT
);

CREATE TABLE IF NOT EXISTS collection_task_roles (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    target_count INTEGER NOT NULL,
    saved_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(task_id, role_id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id)
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    role_id TEXT,
    topic TEXT NOT NULL,
    target_count INTEGER NOT NULL,
    like_floor INTEGER NOT NULL,
    super_like_threshold INTEGER NOT NULL,
    tool_provider TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id)
);

CREATE TABLE IF NOT EXISTS collection_candidates (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT,
    role_id TEXT,
    source_key TEXT NOT NULL,
    source_url TEXT,
    title TEXT,
    author_name TEXT,
    platform_caption TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    source_package_json TEXT NOT NULL DEFAULT '{}',
    raw_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    selection_reason TEXT,
    skip_reason TEXT,
    skip_detail TEXT,
    threshold_mode TEXT,
    material_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, source_key),
    FOREIGN KEY(run_id) REFERENCES collection_runs(id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(material_id) REFERENCES collected_materials(id)
);

CREATE TABLE IF NOT EXISTS collected_materials (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT,
    role_id TEXT,
    source_role_id TEXT,
    source_url TEXT,
    title TEXT,
    clean_title TEXT,
    platform_caption TEXT,
    caption_text TEXT,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    transcript_text TEXT NOT NULL,
    summary_text TEXT,
    hook_text TEXT,
    core_claim TEXT,
    content_type TEXT,
    oral_script_pattern TEXT,
    audience TEXT,
    emotion_trigger TEXT,
    risk_level TEXT,
    content_structure_json TEXT NOT NULL DEFAULT '[]',
    key_points_json TEXT NOT NULL DEFAULT '[]',
    rewrite_angles_json TEXT NOT NULL DEFAULT '[]',
    usable_quotes_json TEXT NOT NULL DEFAULT '[]',
    risk_notes_json TEXT NOT NULL DEFAULT '[]',
    recommended_platforms_json TEXT NOT NULL DEFAULT '[]',
    next_collection_keywords_json TEXT NOT NULL DEFAULT '[]',
    author_name TEXT,
    author_sec_uid TEXT,
    author_profile_url TEXT,
    author_douyin_id TEXT,
    work_id TEXT,
    work_short_url TEXT,
    source_platform TEXT,
    post_time TEXT,
    duration_ms INTEGER,
    cover_url TEXT,
    video_url TEXT,
    audio_url TEXT,
    author_identity_confidence TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    material_understanding_json TEXT NOT NULL DEFAULT '{}',
    understanding_provider TEXT NOT NULL DEFAULT 'codex-agent',
    understanding_model TEXT NOT NULL DEFAULT 'gpt-5.5',
    sample_pool_clues_json TEXT NOT NULL DEFAULT '[]',
    understanding_status TEXT NOT NULL DEFAULT 'pending',
    source_package_json TEXT NOT NULL DEFAULT '{}',
    raw_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'collected',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES collection_runs(id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id)
);

CREATE TABLE IF NOT EXISTS douyin_authors (
    sec_uid TEXT PRIMARY KEY,
    uid TEXT,
    douyin_id TEXT,
    nickname TEXT NOT NULL,
    signature TEXT,
    avatar_url TEXT,
    profile_url TEXT,
    ip_location TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    aweme_count INTEGER,
    total_favorited INTEGER,
    source_material_id TEXT,
    source_work_id TEXT,
    fetched_at TEXT NOT NULL,
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(source_material_id) REFERENCES collected_materials(id)
);

CREATE TABLE IF NOT EXISTS douyin_author_videos (
    id TEXT PRIMARY KEY,
    author_sec_uid TEXT NOT NULL,
    work_id TEXT NOT NULL,
    source_material_id TEXT,
    source_url TEXT,
    title TEXT,
    platform_caption TEXT,
    caption_text TEXT,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    post_time TEXT,
    duration_ms INTEGER,
    cover_url TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    source_package_json TEXT NOT NULL DEFAULT '{}',
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(author_sec_uid, work_id),
    FOREIGN KEY(author_sec_uid) REFERENCES douyin_authors(sec_uid),
    FOREIGN KEY(source_material_id) REFERENCES collected_materials(id)
);

CREATE TABLE IF NOT EXISTS material_role_matches (
    id TEXT PRIMARY KEY,
    material_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    task_id TEXT,
    fit_score REAL NOT NULL,
    decision TEXT NOT NULL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    matched_keywords_json TEXT NOT NULL DEFAULT '[]',
    avoidance_notes_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(material_id, role_id, task_id),
    FOREIGN KEY(material_id) REFERENCES collected_materials(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id)
);

CREATE TABLE IF NOT EXISTS material_creations (
    id TEXT PRIMARY KEY,
    material_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    content_package_id TEXT NOT NULL,
    task_id TEXT,
    platform TEXT NOT NULL,
    rewrite_angle TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(material_id, role_id, content_package_id),
    FOREIGN KEY(material_id) REFERENCES collected_materials(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(content_package_id) REFERENCES content_packages(id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id)
);

CREATE TABLE IF NOT EXISTS mxnzp_call_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    tool_name TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER NOT NULL,
    cache_hit INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES collection_runs(id)
);

CREATE TABLE IF NOT EXISTS mxnzp_call_cache (
    request_fingerprint TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS material_understanding_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    material_id TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    output_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES collection_runs(id),
    FOREIGN KEY(material_id) REFERENCES collected_materials(id)
);

CREATE INDEX IF NOT EXISTS idx_collection_candidates_run_id ON collection_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_collection_candidates_status ON collection_candidates(status);
CREATE INDEX IF NOT EXISTS idx_collected_materials_run_id ON collected_materials(run_id);
CREATE INDEX IF NOT EXISTS idx_collected_materials_role_id ON collected_materials(role_id);
CREATE INDEX IF NOT EXISTS idx_collected_materials_work_id ON collected_materials(work_id);
CREATE INDEX IF NOT EXISTS idx_douyin_authors_nickname ON douyin_authors(nickname);
CREATE INDEX IF NOT EXISTS idx_douyin_author_videos_author ON douyin_author_videos(author_sec_uid);
CREATE INDEX IF NOT EXISTS idx_douyin_author_videos_work_id ON douyin_author_videos(work_id);
CREATE INDEX IF NOT EXISTS idx_material_role_matches_material_id ON material_role_matches(material_id);
CREATE INDEX IF NOT EXISTS idx_material_role_matches_role_id ON material_role_matches(role_id);
CREATE INDEX IF NOT EXISTS idx_material_creations_material_id ON material_creations(material_id);
CREATE INDEX IF NOT EXISTS idx_material_creations_role_id ON material_creations(role_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def scrub_for_storage(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(token in lowered for token in ["secret", "cookie", "api_key", "apikey", "authorization"]):
                scrubbed[key] = "<redacted>"
            else:
                scrubbed[key] = scrub_for_storage(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_for_storage(item) for item in value]
    return value


MATERIAL_V2_COLUMNS: dict[str, str] = {
    "source_role_id": "TEXT",
    "clean_title": "TEXT",
    "caption_text": "TEXT",
    "hashtags_json": "TEXT NOT NULL DEFAULT '[]'",
    "hook_text": "TEXT",
    "core_claim": "TEXT",
    "content_type": "TEXT",
    "oral_script_pattern": "TEXT",
    "audience": "TEXT",
    "emotion_trigger": "TEXT",
    "risk_level": "TEXT",
    "content_structure_json": "TEXT NOT NULL DEFAULT '[]'",
    "key_points_json": "TEXT NOT NULL DEFAULT '[]'",
    "rewrite_angles_json": "TEXT NOT NULL DEFAULT '[]'",
    "usable_quotes_json": "TEXT NOT NULL DEFAULT '[]'",
    "risk_notes_json": "TEXT NOT NULL DEFAULT '[]'",
    "recommended_platforms_json": "TEXT NOT NULL DEFAULT '[]'",
    "next_collection_keywords_json": "TEXT NOT NULL DEFAULT '[]'",
    "post_time": "TEXT",
    "duration_ms": "INTEGER",
    "cover_url": "TEXT",
    "video_url": "TEXT",
    "audio_url": "TEXT",
}


class Store:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> Path:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            _migrate_schema_v2(conn)
            _backfill_material_v2_columns(conn)
        return self.db_path

    def upsert_device(self, serial: str, *, model: str | None = None, status: str = "device") -> None:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO android_devices(serial, model, status, last_seen_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(serial) DO UPDATE SET
                    model = COALESCE(excluded.model, android_devices.model),
                    status = excluded.status,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                (serial, model, status, timestamp, timestamp, timestamp),
            )

    def create_content_package(
        self,
        *,
        title: str,
        body: str,
        media_paths: list[str],
        cover_path: str | None = None,
        hashtags: list[str] | None = None,
        ip_profile_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        content_id = new_id("content")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO content_packages(
                    id, ip_profile_id, title, body, media_paths_json, cover_path,
                    hashtags_json, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content_id,
                    ip_profile_id,
                    title,
                    body,
                    dumps(media_paths),
                    cover_path,
                    dumps(hashtags or []),
                    dumps(metadata or {}),
                    timestamp,
                    timestamp,
                ),
            )
        return content_id

    def get_content_package(self, content_id: str) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM content_packages WHERE id = ?", (content_id,)).fetchone()
        if row is None:
            raise KeyError(f"content package not found: {content_id}")
        return row

    def create_publish_job(
        self,
        *,
        content_id: str,
        platform: str,
        device_serial: str | None = None,
        stop_before_submit: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self.get_content_package(content_id)
        job_id = new_id("job")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO publish_jobs(
                    id, content_id, platform, device_serial, stop_before_submit,
                    metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    content_id,
                    platform,
                    device_serial,
                    int(stop_before_submit),
                    dumps(metadata or {}),
                    timestamp,
                    timestamp,
                ),
            )
        return job_id

    def get_publish_job(self, job_id: str) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM publish_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"publish job not found: {job_id}")
        return row

    def get_job_with_content(self, job_id: str) -> tuple[sqlite3.Row, sqlite3.Row]:
        job = self.get_publish_job(job_id)
        content = self.get_content_package(job["content_id"])
        return job, content

    def update_publish_job_status(self, job_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE publish_jobs SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), job_id),
            )

    def add_run_log(
        self,
        *,
        job_id: str,
        platform: str,
        device_serial: str | None,
        step_name: str,
        status: str,
        message: str = "",
        artifact_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        log_id = new_id("log")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO publish_run_logs(
                    id, job_id, platform, device_serial, step_name, status,
                    message, artifact_path, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    job_id,
                    platform,
                    device_serial,
                    step_name,
                    status,
                    message,
                    artifact_path,
                    dumps(metadata or {}),
                    now_iso(),
                ),
            )
        return log_id

    def add_tracking_snapshot(
        self,
        *,
        publish_job_id: str,
        platform: str,
        result_url: str | None,
        metrics: dict[str, Any] | None = None,
        source: str = "manual",
    ) -> str:
        snapshot_id = new_id("track")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tracking_snapshots(
                    id, publish_job_id, platform, result_url, metrics_json,
                    source, captured_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    publish_job_id,
                    platform,
                    result_url,
                    dumps(metrics or {}),
                    source,
                    timestamp,
                    timestamp,
                ),
            )
        return snapshot_id

    def upsert_ip_role(
        self,
        *,
        name: str,
        positioning: str = "",
        target_directions: list[str] | None = None,
        search_keywords: list[str] | None = None,
        avoid_directions: list[str] | None = None,
        preferred_content: list[str] | None = None,
        forbidden_content: list[str] | None = None,
        enabled: bool = True,
    ) -> str:
        role_name = name.strip()
        if not role_name:
            raise ValueError("role name is required")
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM ip_roles WHERE name = ?", (role_name,)).fetchone()
            role_id = row["id"] if row else new_id("role")
            conn.execute(
                """
                INSERT INTO ip_roles(
                    id, name, positioning, target_directions_json, search_keywords_json,
                    avoid_directions_json, preferred_content_json, forbidden_content_json,
                    enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    positioning = excluded.positioning,
                    target_directions_json = excluded.target_directions_json,
                    search_keywords_json = excluded.search_keywords_json,
                    avoid_directions_json = excluded.avoid_directions_json,
                    preferred_content_json = excluded.preferred_content_json,
                    forbidden_content_json = excluded.forbidden_content_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    role_id,
                    role_name,
                    positioning,
                    dumps(_clean_list(target_directions)),
                    dumps(_clean_list(search_keywords)),
                    dumps(_clean_list(avoid_directions)),
                    dumps(_clean_list(preferred_content)),
                    dumps(_clean_list(forbidden_content)),
                    int(enabled),
                    timestamp,
                    timestamp,
                ),
            )
        return role_id

    def list_ip_roles(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM ip_roles"
        params: tuple[Any, ...] = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at, name"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_role_row_to_dict(row) for row in rows]

    def get_ip_role(self, role_id: str | None = None, *, name: str | None = None) -> dict[str, Any] | None:
        if not role_id and not name:
            raise ValueError("role_id or name is required")
        with self.connect() as conn:
            if role_id:
                row = conn.execute("SELECT * FROM ip_roles WHERE id = ?", (role_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM ip_roles WHERE name = ?", (name,)).fetchone()
        return _role_row_to_dict(row) if row else None

    def create_collection_task(
        self,
        *,
        command: str,
        target_scope: str,
        target_count_per_role: int,
        topic: str | None,
        parsed: dict[str, Any] | None = None,
    ) -> str:
        task_id = new_id("ctask")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO collection_tasks(
                    id, command, target_scope, target_count_per_role, topic,
                    status, parsed_json, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    command,
                    target_scope,
                    target_count_per_role,
                    topic,
                    "running",
                    dumps(scrub_for_storage(parsed or {})),
                    now_iso(),
                ),
            )
        return task_id

    def finish_collection_task(
        self,
        task_id: str,
        status: str,
        summary: dict[str, Any],
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE collection_tasks
                SET status = ?, completed_at = ?, summary_json = ?, error = ?
                WHERE id = ?
                """,
                (status, now_iso(), dumps(scrub_for_storage(summary)), error, task_id),
            )

    def upsert_collection_task_role(
        self,
        *,
        task_id: str,
        role_id: str,
        target_count: int,
        saved_count: int = 0,
        status: str = "running",
        summary: dict[str, Any] | None = None,
    ) -> None:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM collection_task_roles WHERE task_id = ? AND role_id = ?",
                (task_id, role_id),
            ).fetchone()
            link_id = row["id"] if row else new_id("ctrole")
            conn.execute(
                """
                INSERT INTO collection_task_roles(
                    id, task_id, role_id, target_count, saved_count, status,
                    summary_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, role_id) DO UPDATE SET
                    target_count = excluded.target_count,
                    saved_count = excluded.saved_count,
                    status = excluded.status,
                    summary_json = excluded.summary_json,
                    updated_at = excluded.updated_at
                """,
                (
                    link_id,
                    task_id,
                    role_id,
                    target_count,
                    saved_count,
                    status,
                    dumps(scrub_for_storage(summary or {})),
                    timestamp,
                    timestamp,
                ),
            )

    def collection_task_summary(self, task_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            task = conn.execute("SELECT * FROM collection_tasks WHERE id = ?", (task_id,)).fetchone()
            rows = conn.execute(
                """
                SELECT ctr.*, r.name AS role_name
                FROM collection_task_roles ctr
                JOIN ip_roles r ON r.id = ctr.role_id
                WHERE ctr.task_id = ?
                ORDER BY ctr.created_at
                """,
                (task_id,),
            ).fetchall()
        return {
            "task": _task_row_to_dict(task) if task else None,
            "roles": [_task_role_row_to_dict(row) for row in rows],
        }

    def get_collection_task(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM collection_tasks WHERE id = ?", (task_id,)).fetchone()
        return _task_row_to_dict(row) if row else None

    def create_collection_run(
        self,
        *,
        task_id: str | None,
        role_id: str | None,
        topic: str,
        target_count: int,
        like_floor: int,
        super_like_threshold: int,
        tool_provider: str,
    ) -> str:
        run_id = new_id("crun")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO collection_runs(
                    id, task_id, role_id, topic, target_count, like_floor,
                    super_like_threshold, tool_provider, status, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    role_id,
                    topic,
                    target_count,
                    like_floor,
                    super_like_threshold,
                    tool_provider,
                    "running",
                    now_iso(),
                ),
            )
        return run_id

    def finish_collection_run(
        self,
        run_id: str,
        status: str,
        summary: dict[str, Any],
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE collection_runs
                SET status = ?, completed_at = ?, summary_json = ?, error = ?
                WHERE id = ?
                """,
                (status, now_iso(), dumps(scrub_for_storage(summary)), error, run_id),
            )

    def get_collection_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM collection_runs WHERE id = ?", (run_id,)).fetchone()
        return _collection_run_row_to_dict(row) if row else None

    def list_collection_runs(self, *, task_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM collection_runs"
        params: tuple[Any, ...] = ()
        if task_id is not None:
            query += " WHERE task_id = ?"
            params = (task_id,)
        query += " ORDER BY started_at, id"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_collection_run_row_to_dict(row) for row in rows]

    def upsert_collection_candidate(
        self,
        run_id: str,
        candidate: dict[str, Any],
        *,
        status: str = "discovered",
        selection_reason: str = "",
        skip_reason: str = "",
        skip_detail: str = "",
        threshold_mode: str = "",
        material_id: str | None = None,
    ) -> str:
        source_package = dict(candidate.get("source_package") or {})
        metrics = source_package.get("public_metrics") or {}
        source_key = _candidate_source_key(candidate)
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM collection_candidates WHERE run_id = ? AND source_key = ?",
                (run_id, source_key),
            ).fetchone()
            candidate_id = existing["id"] if existing else new_id("cand")
            conn.execute(
                """
                INSERT INTO collection_candidates(
                    id, run_id, task_id, role_id, source_key, source_url, title,
                    author_name, platform_caption, metrics_json, source_package_json,
                    raw_json, status, selection_reason, skip_reason, skip_detail,
                    threshold_mode, material_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, source_key) DO UPDATE SET
                    task_id = excluded.task_id,
                    role_id = excluded.role_id,
                    source_url = excluded.source_url,
                    title = excluded.title,
                    author_name = excluded.author_name,
                    platform_caption = excluded.platform_caption,
                    metrics_json = excluded.metrics_json,
                    source_package_json = excluded.source_package_json,
                    raw_json = excluded.raw_json,
                    status = excluded.status,
                    selection_reason = excluded.selection_reason,
                    skip_reason = excluded.skip_reason,
                    skip_detail = excluded.skip_detail,
                    threshold_mode = excluded.threshold_mode,
                    material_id = excluded.material_id,
                    updated_at = excluded.updated_at
                """,
                (
                    candidate_id,
                    run_id,
                    source_package.get("task_id"),
                    source_package.get("role_id"),
                    source_key,
                    source_package.get("source_link"),
                    source_package.get("title"),
                    source_package.get("author_name"),
                    source_package.get("platform_caption"),
                    dumps(scrub_for_storage(metrics)),
                    dumps(scrub_for_storage(source_package)),
                    dumps(scrub_for_storage(candidate.get("raw") or {})),
                    status,
                    selection_reason,
                    skip_reason,
                    skip_detail,
                    threshold_mode,
                    material_id,
                    timestamp,
                    timestamp,
                ),
            )
        return candidate_id

    def list_collection_candidates(
        self,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        role_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if task_id is not None:
            where.append("task_id = ?")
            params.append(task_id)
        if run_id is not None:
            where.append("run_id = ?")
            params.append(run_id)
        if role_id is not None:
            where.append("role_id = ?")
            params.append(role_id)
        if status is not None:
            where.append("status = ?")
            params.append(status)
        query = "SELECT * FROM collection_candidates"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_candidate_row_to_dict(row) for row in rows]

    def insert_collected_material(
        self,
        *,
        run_id: str,
        source_package: dict[str, Any],
        material_understanding: dict[str, Any],
        raw: dict[str, Any],
    ) -> str:
        material_id = new_id("mat")
        timestamp = now_iso()
        metrics = source_package.get("public_metrics") or {}
        provider = str(material_understanding.get("understanding_provider") or "codex-agent")
        model = str(material_understanding.get("understanding_model") or "gpt-5.5")
        promoted = _material_promoted_values(source_package, material_understanding, raw)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO collected_materials(
                    id, run_id, task_id, role_id, source_role_id, source_url, title, clean_title,
                    platform_caption, caption_text, hashtags_json,
                    transcript_text, summary_text, hook_text, core_claim,
                    content_type, oral_script_pattern, audience, emotion_trigger,
                    risk_level, content_structure_json, key_points_json,
                    rewrite_angles_json, usable_quotes_json, risk_notes_json,
                    recommended_platforms_json, next_collection_keywords_json,
                    author_name, author_sec_uid, author_profile_url, author_douyin_id,
                    work_id, work_short_url, source_platform, post_time, duration_ms,
                    cover_url, video_url, audio_url, author_identity_confidence, metrics_json,
                    material_understanding_json, understanding_provider,
                    understanding_model, sample_pool_clues_json, understanding_status,
                    source_package_json, raw_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_id,
                    run_id,
                    source_package.get("task_id"),
                    source_package.get("role_id"),
                    source_package.get("source_role_id") or source_package.get("role_id"),
                    source_package.get("source_link"),
                    source_package.get("title"),
                    promoted["clean_title"],
                    source_package.get("platform_caption"),
                    promoted["caption_text"],
                    dumps(promoted["hashtags"]),
                    source_package.get("transcript_text") or "",
                    promoted["summary_text"],
                    promoted["hook_text"],
                    promoted["core_claim"],
                    promoted["content_type"],
                    promoted["oral_script_pattern"],
                    promoted["audience"],
                    promoted["emotion_trigger"],
                    promoted["risk_level"],
                    dumps(promoted["content_structure"]),
                    dumps(promoted["key_points"]),
                    dumps(promoted["rewrite_angles"]),
                    dumps(promoted["usable_quotes"]),
                    dumps(promoted["risk_notes"]),
                    dumps(promoted["recommended_platforms"]),
                    dumps(promoted["next_collection_keywords"]),
                    source_package.get("author_name"),
                    source_package.get("author_sec_uid"),
                    source_package.get("author_profile_url"),
                    source_package.get("author_douyin_id"),
                    source_package.get("work_id"),
                    source_package.get("work_short_url"),
                    source_package.get("source_platform") or source_package.get("source_type"),
                    promoted["post_time"],
                    promoted["duration_ms"],
                    promoted["cover_url"],
                    promoted["video_url"],
                    promoted["audio_url"],
                    (source_package.get("author_identity") or {}).get("confidence")
                    or source_package.get("author_identity_confidence"),
                    dumps(scrub_for_storage(metrics)),
                    dumps(scrub_for_storage(material_understanding)),
                    provider,
                    model,
                    dumps(scrub_for_storage(source_package.get("sample_pool_clues") or [])),
                    source_package.get("understanding_status") or "success",
                    dumps(scrub_for_storage(source_package)),
                    dumps(scrub_for_storage(raw)),
                    timestamp,
                    timestamp,
                ),
            )
        return material_id

    def get_collected_material(self, material_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM collected_materials WHERE id = ?", (material_id,)).fetchone()
        return _material_row_to_dict(row) if row else None

    def list_collected_materials(
        self,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        role_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if task_id is not None:
            where.append("task_id = ?")
            params.append(task_id)
        if run_id is not None:
            where.append("run_id = ?")
            params.append(run_id)
        if role_id is not None:
            where.append(
                """
                (
                    role_id = ?
                    OR source_role_id = ?
                    OR EXISTS (
                        SELECT 1 FROM material_role_matches mrm
                        WHERE mrm.material_id = collected_materials.id
                          AND mrm.role_id = ?
                    )
                )
                """
            )
            params.extend([role_id, role_id, role_id])
        if status is not None:
            where.append("status = ?")
            params.append(status)
        query = "SELECT * FROM collected_materials"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_material_row_to_dict(row) for row in rows]

    def update_material_understanding(
        self,
        material_id: str,
        *,
        understanding: dict[str, Any],
        provider: str,
        model: str,
    ) -> None:
        material = self.get_collected_material(material_id)
        if not material:
            raise KeyError(f"material not found: {material_id}")
        promoted = _material_promoted_values(material.get("source_package") or {}, understanding, material.get("raw") or {})
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE collected_materials
                SET summary_text = ?,
                    hook_text = ?,
                    core_claim = ?,
                    content_type = ?,
                    oral_script_pattern = ?,
                    audience = ?,
                    emotion_trigger = ?,
                    risk_level = ?,
                    content_structure_json = ?,
                    key_points_json = ?,
                    rewrite_angles_json = ?,
                    usable_quotes_json = ?,
                    risk_notes_json = ?,
                    recommended_platforms_json = ?,
                    next_collection_keywords_json = ?,
                    material_understanding_json = ?,
                    understanding_provider = ?,
                    understanding_model = ?,
                    understanding_status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    promoted["summary_text"],
                    promoted["hook_text"],
                    promoted["core_claim"],
                    promoted["content_type"],
                    promoted["oral_script_pattern"],
                    promoted["audience"],
                    promoted["emotion_trigger"],
                    promoted["risk_level"],
                    dumps(promoted["content_structure"]),
                    dumps(promoted["key_points"]),
                    dumps(promoted["rewrite_angles"]),
                    dumps(promoted["usable_quotes"]),
                    dumps(promoted["risk_notes"]),
                    dumps(promoted["recommended_platforms"]),
                    dumps(promoted["next_collection_keywords"]),
                    dumps(scrub_for_storage(understanding)),
                    provider,
                    model,
                    str(understanding.get("status") or "success"),
                    now_iso(),
                    material_id,
                ),
            )

    def log_material_understanding(
        self,
        *,
        run_id: str | None,
        material_id: str | None,
        provider: str,
        model: str,
        status: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> str:
        log_id = new_id("ulog")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO material_understanding_logs(
                    id, run_id, material_id, provider, model, status,
                    output_json, error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    run_id,
                    material_id,
                    provider,
                    model,
                    status,
                    dumps(scrub_for_storage(output or {})),
                    error,
                    now_iso(),
                ),
            )
        return log_id

    def update_collected_material_author(
        self,
        material_id: str,
        *,
        author_name: str | None = None,
        author_sec_uid: str | None = None,
        author_profile_url: str | None = None,
        author_douyin_id: str | None = None,
        work_id: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE collected_materials
                SET author_name = COALESCE(?, author_name),
                    author_sec_uid = COALESCE(?, author_sec_uid),
                    author_profile_url = COALESCE(?, author_profile_url),
                    author_douyin_id = COALESCE(?, author_douyin_id),
                    work_id = COALESCE(?, work_id),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    author_name,
                    author_sec_uid,
                    author_profile_url,
                    author_douyin_id,
                    work_id,
                    now_iso(),
                    material_id,
                ),
            )

    def upsert_douyin_author(
        self,
        profile: dict[str, Any],
        *,
        source_material_id: str | None = None,
        source_work_id: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> str:
        raw_profile = raw or profile.get("raw") or {}
        if not isinstance(raw_profile, dict):
            raw_profile = {}
        sec_uid = str(profile.get("sec_uid") or raw_profile.get("sec_uid") or "").strip()
        if not sec_uid:
            raise ValueError("douyin author sec_uid is required")
        nickname = str(profile.get("nickname") or raw_profile.get("nickname") or "").strip()
        if not nickname:
            raise ValueError("douyin author nickname is required")
        timestamp = now_iso()
        avatar_url = profile.get("avatar_url") or _first_url(
            raw_profile.get("avatar_thumb"),
            raw_profile.get("avatar_medium"),
            raw_profile.get("avatar_168x168"),
            raw_profile.get("avatar_larger"),
        )
        share_info = raw_profile.get("share_info") if isinstance(raw_profile.get("share_info"), dict) else {}
        profile_url = profile.get("profile_url") or profile.get("share_url") or share_info.get("share_url")
        if profile_url and str(profile_url).startswith("www."):
            profile_url = "https://" + str(profile_url)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO douyin_authors(
                    sec_uid, uid, douyin_id, nickname, signature, avatar_url,
                    profile_url, ip_location, follower_count, following_count,
                    aweme_count, total_favorited, source_material_id, source_work_id,
                    fetched_at, raw_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sec_uid) DO UPDATE SET
                    uid = COALESCE(excluded.uid, douyin_authors.uid),
                    douyin_id = COALESCE(excluded.douyin_id, douyin_authors.douyin_id),
                    nickname = excluded.nickname,
                    signature = COALESCE(excluded.signature, douyin_authors.signature),
                    avatar_url = COALESCE(excluded.avatar_url, douyin_authors.avatar_url),
                    profile_url = COALESCE(excluded.profile_url, douyin_authors.profile_url),
                    ip_location = COALESCE(excluded.ip_location, douyin_authors.ip_location),
                    follower_count = COALESCE(excluded.follower_count, douyin_authors.follower_count),
                    following_count = COALESCE(excluded.following_count, douyin_authors.following_count),
                    aweme_count = COALESCE(excluded.aweme_count, douyin_authors.aweme_count),
                    total_favorited = COALESCE(excluded.total_favorited, douyin_authors.total_favorited),
                    source_material_id = COALESCE(excluded.source_material_id, douyin_authors.source_material_id),
                    source_work_id = COALESCE(excluded.source_work_id, douyin_authors.source_work_id),
                    fetched_at = excluded.fetched_at,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    sec_uid,
                    profile.get("uid") or raw_profile.get("uid"),
                    profile.get("douyin_id") or raw_profile.get("unique_id") or raw_profile.get("short_id"),
                    nickname,
                    profile.get("signature") or raw_profile.get("signature"),
                    avatar_url,
                    profile_url,
                    profile.get("ip_location") or raw_profile.get("ip_location"),
                    _optional_int(profile.get("follower_count") or raw_profile.get("follower_count")),
                    _optional_int(profile.get("following_count") or raw_profile.get("following_count")),
                    _optional_int(profile.get("aweme_count") or raw_profile.get("aweme_count")),
                    _optional_int(profile.get("total_favorited") or raw_profile.get("total_favorited")),
                    source_material_id,
                    source_work_id,
                    timestamp,
                    dumps(scrub_for_storage(raw_profile)),
                    timestamp,
                    timestamp,
                ),
            )
        return sec_uid

    def get_douyin_author(self, sec_uid: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM douyin_authors WHERE sec_uid = ?", (sec_uid,)).fetchone()
        return _douyin_author_row_to_dict(row) if row else None

    def list_douyin_authors(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM douyin_authors ORDER BY updated_at DESC, nickname").fetchall()
        return [_douyin_author_row_to_dict(row) for row in rows]

    def upsert_douyin_author_video(
        self,
        author_sec_uid: str,
        video: dict[str, Any],
        *,
        source_material_id: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> str:
        raw_video = raw or video.get("raw") or {}
        if not isinstance(raw_video, dict):
            raw_video = {}
        work_id = str(
            video.get("work_id")
            or video.get("id")
            or raw_video.get("aweme_id")
            or raw_video.get("id")
            or ""
        ).strip()
        if not work_id:
            raise ValueError("douyin author video work_id is required")
        caption = str(video.get("platform_caption") or video.get("caption") or raw_video.get("desc") or raw_video.get("caption") or "").strip()
        title = str(video.get("title") or raw_video.get("title") or caption).strip()
        parsed = parse_caption(title=title, caption=caption)
        metrics = video.get("metrics") or video.get("public_metrics") or {
            "digg_count": raw_video.get("digg_count") or raw_video.get("diggCount"),
            "collect_count": raw_video.get("collect_count") or raw_video.get("collectCount"),
            "comment_count": raw_video.get("comment_count") or raw_video.get("commentCount"),
            "share_count": raw_video.get("share_count") or raw_video.get("shareCount"),
            "play_count": raw_video.get("play_count") or raw_video.get("playCount"),
        }
        timestamp = now_iso()
        row_id = new_id("avideo")
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM douyin_author_videos WHERE author_sec_uid = ? AND work_id = ?",
                (author_sec_uid, work_id),
            ).fetchone()
            if existing:
                row_id = existing["id"]
            conn.execute(
                """
                INSERT INTO douyin_author_videos(
                    id, author_sec_uid, work_id, source_material_id, source_url,
                    title, platform_caption, caption_text, hashtags_json, post_time,
                    duration_ms, cover_url, metrics_json, source_package_json,
                    raw_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(author_sec_uid, work_id) DO UPDATE SET
                    source_material_id = COALESCE(excluded.source_material_id, douyin_author_videos.source_material_id),
                    source_url = COALESCE(excluded.source_url, douyin_author_videos.source_url),
                    title = COALESCE(excluded.title, douyin_author_videos.title),
                    platform_caption = COALESCE(excluded.platform_caption, douyin_author_videos.platform_caption),
                    caption_text = COALESCE(excluded.caption_text, douyin_author_videos.caption_text),
                    hashtags_json = excluded.hashtags_json,
                    post_time = COALESCE(excluded.post_time, douyin_author_videos.post_time),
                    duration_ms = COALESCE(excluded.duration_ms, douyin_author_videos.duration_ms),
                    cover_url = COALESCE(excluded.cover_url, douyin_author_videos.cover_url),
                    metrics_json = excluded.metrics_json,
                    source_package_json = excluded.source_package_json,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    row_id,
                    author_sec_uid,
                    work_id,
                    source_material_id,
                    video.get("source_url") or video.get("source_link") or video.get("share_url") or raw_video.get("share_url") or raw_video.get("shareUrl"),
                    title or None,
                    caption or None,
                    parsed["caption_text"],
                    dumps(parsed["hashtags"]),
                    video.get("post_time") or raw_video.get("post_time") or raw_video.get("create_time"),
                    _optional_int(video.get("duration_ms") or video.get("duration") or raw_video.get("duration")),
                    video.get("cover_url") or raw_video.get("cover"),
                    dumps(scrub_for_storage(metrics or {})),
                    dumps(scrub_for_storage(video)),
                    dumps(scrub_for_storage(raw_video)),
                    timestamp,
                    timestamp,
                ),
            )
        return row_id

    def list_douyin_author_videos(self, author_sec_uid: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM douyin_author_videos WHERE author_sec_uid = ? ORDER BY created_at DESC, id",
                (author_sec_uid,),
            ).fetchall()
        return [_douyin_author_video_row_to_dict(row) for row in rows]

    def insert_material_role_match(
        self,
        *,
        material_id: str,
        role_id: str,
        task_id: str | None,
        fit_score: float,
        decision: str,
        reasons: list[str] | None = None,
        matched_keywords: list[str] | None = None,
        avoidance_notes: list[str] | None = None,
    ) -> str:
        match_id = new_id("match")
        with self.connect() as conn:
            if task_id is None:
                existing = conn.execute(
                    """
                    SELECT id FROM material_role_matches
                    WHERE material_id = ? AND role_id = ? AND task_id IS NULL
                    """,
                    (material_id, role_id),
                ).fetchone()
            else:
                existing = conn.execute(
                    """
                    SELECT id FROM material_role_matches
                    WHERE material_id = ? AND role_id = ? AND task_id = ?
                    """,
                    (material_id, role_id, task_id),
                ).fetchone()
            if existing:
                match_id = existing["id"]
                conn.execute(
                    """
                    UPDATE material_role_matches
                    SET fit_score = ?, decision = ?, reasons_json = ?,
                        matched_keywords_json = ?, avoidance_notes_json = ?,
                        created_at = ?
                    WHERE id = ?
                    """,
                    (
                        fit_score,
                        decision,
                        dumps(_clean_list(reasons)),
                        dumps(_clean_list(matched_keywords)),
                        dumps(_clean_list(avoidance_notes)),
                        now_iso(),
                        match_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO material_role_matches(
                        id, material_id, role_id, task_id, fit_score, decision,
                        reasons_json, matched_keywords_json, avoidance_notes_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        match_id,
                        material_id,
                        role_id,
                        task_id,
                        fit_score,
                        decision,
                        dumps(_clean_list(reasons)),
                        dumps(_clean_list(matched_keywords)),
                        dumps(_clean_list(avoidance_notes)),
                        now_iso(),
                    ),
                )
        return match_id

    def list_material_role_matches(
        self,
        *,
        material_id: str | None = None,
        role_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if material_id is not None:
            where.append("material_id = ?")
            params.append(material_id)
        if role_id is not None:
            where.append("role_id = ?")
            params.append(role_id)
        if task_id is not None:
            where.append("task_id = ?")
            params.append(task_id)
        query = "SELECT * FROM material_role_matches"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY fit_score DESC, created_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_role_match_row_to_dict(row) for row in rows]

    def insert_material_creation(
        self,
        *,
        material_id: str,
        role_id: str,
        content_package_id: str,
        task_id: str | None,
        platform: str,
        rewrite_angle: str | None = None,
        status: str = "draft",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        creation_id = new_id("mcreate")
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM material_creations
                WHERE material_id = ? AND role_id = ? AND content_package_id = ?
                """,
                (material_id, role_id, content_package_id),
            ).fetchone()
            if existing:
                creation_id = existing["id"]
                conn.execute(
                    """
                    UPDATE material_creations
                    SET task_id = ?, platform = ?, rewrite_angle = ?, status = ?,
                        metadata_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        task_id,
                        platform,
                        rewrite_angle,
                        status,
                        dumps(scrub_for_storage(metadata or {})),
                        timestamp,
                        creation_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO material_creations(
                        id, material_id, role_id, content_package_id, task_id,
                        platform, rewrite_angle, status, metadata_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        creation_id,
                        material_id,
                        role_id,
                        content_package_id,
                        task_id,
                        platform,
                        rewrite_angle,
                        status,
                        dumps(scrub_for_storage(metadata or {})),
                        timestamp,
                        timestamp,
                    ),
                )
        return creation_id

    def list_material_creations(
        self,
        *,
        material_id: str | None = None,
        role_id: str | None = None,
        content_package_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if material_id is not None:
            where.append("material_id = ?")
            params.append(material_id)
        if role_id is not None:
            where.append("role_id = ?")
            params.append(role_id)
        if content_package_id is not None:
            where.append("content_package_id = ?")
            params.append(content_package_id)
        query = "SELECT * FROM material_creations"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at DESC, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_material_creation_row_to_dict(row) for row in rows]

    def log_mxnzp_call(
        self,
        *,
        run_id: str | None,
        tool_name: str,
        request_fingerprint: str,
        status: str,
        duration_ms: int,
        cache_hit: bool,
        error: str | None = None,
    ) -> str:
        log_id = new_id("call")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO mxnzp_call_logs(
                    id, run_id, tool_name, request_fingerprint, status,
                    error, duration_ms, cache_hit, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    run_id,
                    tool_name,
                    request_fingerprint,
                    status,
                    error,
                    duration_ms,
                    int(cache_hit),
                    now_iso(),
                ),
            )
        return log_id

    def get_cached_collection_call(self, request_fingerprint: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT response_json FROM mxnzp_call_cache WHERE request_fingerprint = ?",
                (request_fingerprint,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE mxnzp_call_cache
                    SET hit_count = hit_count + 1, updated_at = ?
                    WHERE request_fingerprint = ?
                    """,
                    (now_iso(), request_fingerprint),
                )
        return loads(row["response_json"], {}) if row else None

    def put_cached_collection_call(
        self,
        tool_name: str,
        request_fingerprint: str,
        response: dict[str, Any],
    ) -> None:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO mxnzp_call_cache(
                    request_fingerprint, tool_name, response_json, created_at, updated_at, hit_count
                )
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(request_fingerprint) DO UPDATE SET
                    tool_name = excluded.tool_name,
                    response_json = excluded.response_json,
                    updated_at = excluded.updated_at
                """,
                (
                    request_fingerprint,
                    tool_name,
                    dumps(scrub_for_storage(response)),
                    timestamp,
                    timestamp,
                ),
            )

    def collection_call_summary(self, run_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT tool_name, status, COUNT(*) AS count, SUM(cache_hit) AS cache_hits
                FROM mxnzp_call_logs
                WHERE run_id = ?
                GROUP BY tool_name, status
                ORDER BY tool_name, status
                """,
                (run_id,),
            ).fetchall()
        return {
            "total_calls": sum(int(row["count"]) for row in rows),
            "cache_hits": sum(int(row["cache_hits"] or 0) for row in rows),
            "by_tool": [
                {
                    "tool_name": row["tool_name"],
                    "status": row["status"],
                    "count": row["count"],
                    "cache_hits": row["cache_hits"] or 0,
                }
                for row in rows
            ],
        }

    def task_call_summary(self, task_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT l.tool_name, l.status, COUNT(*) AS count, SUM(l.cache_hit) AS cache_hits
                FROM mxnzp_call_logs l
                JOIN collection_runs r ON r.id = l.run_id
                WHERE r.task_id = ?
                GROUP BY l.tool_name, l.status
                ORDER BY l.tool_name, l.status
                """,
                (task_id,),
            ).fetchall()
        return {
            "total_calls": sum(int(row["count"]) for row in rows),
            "cache_hits": sum(int(row["cache_hits"] or 0) for row in rows),
            "by_tool": [
                {
                    "tool_name": row["tool_name"],
                    "status": row["status"],
                    "count": row["count"],
                    "cache_hits": row["cache_hits"] or 0,
                }
                for row in rows
            ],
        }

    def build_collection_report(self, run_id: str) -> dict[str, Any]:
        run = self.get_collection_run(run_id)
        if not run:
            raise KeyError(f"collection run not found: {run_id}")
        materials = self.list_collected_materials(run_id=run_id)
        candidates = self.list_collection_candidates(run_id=run_id)
        skipped = [
            candidate
            for candidate in candidates
            if candidate["status"] in {"rejected", "below_threshold", "skipped"}
        ]
        next_keywords: list[str] = []
        for material in materials:
            understanding = material.get("material_understanding") or {}
            next_keywords.extend(material.get("next_collection_keywords") or understanding.get("next_collection_keywords") or [])
        return {
            "run": run,
            "saved_count": len(materials),
            "candidate_count": len(candidates),
            "materials": materials,
            "skipped": skipped,
            "call_summary": self.collection_call_summary(run_id),
            "next_collection_keywords": _dedupe_strings(next_keywords),
            "promotable_material_ids": [material["id"] for material in materials if material.get("status") == "collected"],
        }

    def promote_material_to_content_package(
        self,
        material_id: str,
        *,
        platform: str,
        role_id: str | None = None,
        task_id: str | None = None,
        rewrite_angle: str | None = None,
        title: str | None = None,
        body: str | None = None,
        hashtags: list[str] | None = None,
    ) -> str:
        material = self.get_collected_material(material_id)
        if not material:
            raise KeyError(f"material not found: {material_id}")
        understanding = material.get("material_understanding") or {}
        rewrite_angles = list(material.get("rewrite_angles") or understanding.get("rewrite_angles") or [])
        content_title = title or str(material.get("clean_title") or material.get("title") or material.get("summary_text") or "素材二创草稿")[:40]
        content_body = body or str(
            material.get("summary_text")
            or "\n".join(str(item) for item in rewrite_angles[:3])
            or material.get("transcript_text")
            or ""
        )
        content_id = self.create_content_package(
            title=content_title,
            body=content_body,
            media_paths=[],
            hashtags=hashtags or list(material.get("next_collection_keywords") or understanding.get("next_collection_keywords") or [])[:3],
            metadata={
                "source": "collected_material",
                "source_material_id": material_id,
                "source_role_id": material.get("source_role_id") or material.get("role_id"),
                "role_id": role_id or material.get("source_role_id") or material.get("role_id"),
                "task_id": task_id or material.get("task_id"),
                "source_platform": material.get("source_platform"),
                "target_platform": platform,
                "material_summary": material.get("summary_text"),
                "rewrite_angle": rewrite_angle,
            },
        )
        creation_role_id = role_id or material.get("source_role_id") or material.get("role_id")
        if creation_role_id:
            self.insert_material_creation(
                material_id=material_id,
                role_id=creation_role_id,
                content_package_id=content_id,
                task_id=task_id or material.get("task_id"),
                platform=platform,
                rewrite_angle=rewrite_angle,
                status="draft",
                metadata={
                    "source": "material_promote",
                    "material_summary": material.get("summary_text"),
                },
            )
        return content_id

    def list_tables(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [row["name"] for row in rows]


def _clean_list(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _row_json(row: sqlite3.Row, key: str, default: Any) -> Any:
    return loads(row[key], default)


def _migrate_schema_v2(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "collected_materials"):
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(collected_materials)").fetchall()
        }
        for column, definition in MATERIAL_V2_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE collected_materials ADD COLUMN {column} {definition}")
        conn.execute("UPDATE collected_materials SET source_role_id = COALESCE(source_role_id, role_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_creations (
            id TEXT PRIMARY KEY,
            material_id TEXT NOT NULL,
            role_id TEXT NOT NULL,
            content_package_id TEXT NOT NULL,
            task_id TEXT,
            platform TEXT NOT NULL,
            rewrite_angle TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(material_id, role_id, content_package_id),
            FOREIGN KEY(material_id) REFERENCES collected_materials(id),
            FOREIGN KEY(role_id) REFERENCES ip_roles(id),
            FOREIGN KEY(content_package_id) REFERENCES content_packages(id),
            FOREIGN KEY(task_id) REFERENCES collection_tasks(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_material_role_matches_role_id ON material_role_matches(role_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_material_creations_material_id ON material_creations(material_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_material_creations_role_id ON material_creations(role_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS douyin_authors (
            sec_uid TEXT PRIMARY KEY,
            uid TEXT,
            douyin_id TEXT,
            nickname TEXT NOT NULL,
            signature TEXT,
            avatar_url TEXT,
            profile_url TEXT,
            ip_location TEXT,
            follower_count INTEGER,
            following_count INTEGER,
            aweme_count INTEGER,
            total_favorited INTEGER,
            source_material_id TEXT,
            source_work_id TEXT,
            fetched_at TEXT NOT NULL,
            raw_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(source_material_id) REFERENCES collected_materials(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS douyin_author_videos (
            id TEXT PRIMARY KEY,
            author_sec_uid TEXT NOT NULL,
            work_id TEXT NOT NULL,
            source_material_id TEXT,
            source_url TEXT,
            title TEXT,
            platform_caption TEXT,
            caption_text TEXT,
            hashtags_json TEXT NOT NULL DEFAULT '[]',
            post_time TEXT,
            duration_ms INTEGER,
            cover_url TEXT,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            source_package_json TEXT NOT NULL DEFAULT '{}',
            raw_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(author_sec_uid, work_id),
            FOREIGN KEY(author_sec_uid) REFERENCES douyin_authors(sec_uid),
            FOREIGN KEY(source_material_id) REFERENCES collected_materials(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_douyin_authors_nickname ON douyin_authors(nickname)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_douyin_author_videos_author ON douyin_author_videos(author_sec_uid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_douyin_author_videos_work_id ON douyin_author_videos(work_id)")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _backfill_material_v2_columns(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "collected_materials"):
        return
    rows = conn.execute("SELECT * FROM collected_materials").fetchall()
    for row in rows:
        source_package = _row_json(row, "source_package_json", {})
        raw = _row_json(row, "raw_json", {})
        understanding = _row_json(row, "material_understanding_json", {})
        if not isinstance(source_package, dict):
            source_package = {}
        if not isinstance(raw, dict):
            raw = {}
        if not isinstance(understanding, dict):
            understanding = {}
        source_package = {
            **source_package,
            "title": source_package.get("title") or row["title"],
            "platform_caption": source_package.get("platform_caption") or row["platform_caption"],
            "transcript_text": source_package.get("transcript_text") or row["transcript_text"],
        }
        promoted = _material_promoted_values(source_package, understanding, raw)
        summary = row["summary_text"]
        if row["understanding_status"] == "pending_raw_transcript" and _is_transcript_prefix(summary, row["transcript_text"]):
            summary = None
        elif promoted["summary_text"]:
            summary = promoted["summary_text"]
        conn.execute(
            """
            UPDATE collected_materials
            SET clean_title = COALESCE(NULLIF(clean_title, ''), ?),
                caption_text = COALESCE(NULLIF(caption_text, ''), ?),
                hashtags_json = ?,
                summary_text = ?,
                hook_text = COALESCE(NULLIF(hook_text, ''), ?),
                core_claim = COALESCE(NULLIF(core_claim, ''), ?),
                content_type = COALESCE(NULLIF(content_type, ''), ?),
                oral_script_pattern = COALESCE(NULLIF(oral_script_pattern, ''), ?),
                audience = COALESCE(NULLIF(audience, ''), ?),
                emotion_trigger = COALESCE(NULLIF(emotion_trigger, ''), ?),
                risk_level = COALESCE(NULLIF(risk_level, ''), ?),
                content_structure_json = ?,
                key_points_json = ?,
                rewrite_angles_json = ?,
                usable_quotes_json = ?,
                risk_notes_json = ?,
                recommended_platforms_json = ?,
                next_collection_keywords_json = ?,
                post_time = COALESCE(NULLIF(post_time, ''), ?),
                duration_ms = COALESCE(duration_ms, ?),
                cover_url = COALESCE(NULLIF(cover_url, ''), ?),
                video_url = COALESCE(NULLIF(video_url, ''), ?),
                audio_url = COALESCE(NULLIF(audio_url, ''), ?)
            WHERE id = ?
            """,
            (
                promoted["clean_title"],
                promoted["caption_text"],
                dumps(promoted["hashtags"]),
                summary,
                promoted["hook_text"],
                promoted["core_claim"],
                promoted["content_type"],
                promoted["oral_script_pattern"],
                promoted["audience"],
                promoted["emotion_trigger"],
                promoted["risk_level"],
                dumps(promoted["content_structure"]),
                dumps(promoted["key_points"]),
                dumps(promoted["rewrite_angles"]),
                dumps(promoted["usable_quotes"]),
                dumps(promoted["risk_notes"]),
                dumps(promoted["recommended_platforms"]),
                dumps(promoted["next_collection_keywords"]),
                promoted["post_time"],
                promoted["duration_ms"],
                promoted["cover_url"],
                promoted["video_url"],
                promoted["audio_url"],
                row["id"],
            ),
        )


def _material_promoted_values(
    source_package: dict[str, Any],
    understanding: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    raw_douyin = _extract_raw_douyin_info(raw)
    source_caption = str(source_package.get("platform_caption") or "").strip()
    raw_caption = str(raw_douyin.get("desc") or "").strip()
    caption = raw_caption if raw_caption and "#" in raw_caption and "#" not in source_caption else source_caption
    if not caption:
        caption = raw_caption or str(source_package.get("title") or "").strip()
    title = str(
        source_package.get("title")
        or raw_douyin.get("title")
        or caption
    ).strip()
    parsed = parse_caption(title=title, caption=caption)
    status = str(understanding.get("status") or "")
    summary = str(understanding.get("topic_summary") or "").strip() or None
    if status in {"pending_deep_understanding", "pending_raw_transcript"}:
        summary = None
    return {
        "clean_title": source_package.get("clean_title") or parsed["clean_title"],
        "caption_text": source_package.get("caption_text") or parsed["caption_text"],
        "hashtags": _as_list(source_package.get("hashtags") or source_package.get("hashtags_json") or parsed["hashtags"]),
        "summary_text": summary,
        "hook_text": _optional_text(understanding.get("hook")),
        "core_claim": _optional_text(understanding.get("core_claim")),
        "content_type": _optional_text(understanding.get("content_type")),
        "oral_script_pattern": _optional_text(understanding.get("oral_script_pattern")),
        "audience": _optional_text(understanding.get("audience")),
        "emotion_trigger": _optional_text(understanding.get("emotion_trigger")),
        "risk_level": _optional_text(understanding.get("risk_level")),
        "content_structure": _as_list(understanding.get("content_structure")),
        "key_points": _as_list(understanding.get("key_points")),
        "rewrite_angles": _as_list(understanding.get("rewrite_angles")),
        "usable_quotes": _as_list(understanding.get("usable_quotes")),
        "risk_notes": _as_list(understanding.get("risk_notes")),
        "recommended_platforms": _as_list(understanding.get("recommended_platforms")),
        "next_collection_keywords": _as_list(understanding.get("next_collection_keywords")),
        "post_time": source_package.get("post_time") or raw_douyin.get("postTime") or raw_douyin.get("post_time"),
        "duration_ms": _optional_int(source_package.get("duration_ms") or raw_douyin.get("videoDuration") or raw_douyin.get("duration")),
        "cover_url": source_package.get("cover_url") or raw_douyin.get("cover"),
        "video_url": source_package.get("video_url") or raw_douyin.get("videoUrl") or raw_douyin.get("video_url"),
        "audio_url": source_package.get("audio_url") or raw_douyin.get("audioUrl") or raw_douyin.get("audio_url"),
    }


def parse_caption(*, title: str | None, caption: str | None) -> dict[str, Any]:
    raw_caption = str(caption or title or "").strip()
    tags = _dedupe_strings([match.group(1).strip() for match in re.finditer(r"#([^\s#]+)", raw_caption)])
    caption_text = re.sub(r"#([^\s#]+)", "", raw_caption).strip()
    caption_text = re.sub(r"\s+", " ", caption_text).strip()
    clean_title = re.sub(r"#([^\s#]+)", "", str(title or caption_text or raw_caption)).strip()
    clean_title = re.sub(r"\s+", " ", clean_title).strip()
    return {"clean_title": clean_title, "caption_text": caption_text, "hashtags": tags}


def _extract_raw_douyin_info(raw: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        raw.get("video_to_text_v2_result", {}).get("raw", {}).get("data", {}).get("douyinInfo"),
        raw.get("raw", {}).get("data", {}).get("douyinInfo"),
        raw.get("douyinInfo"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def _is_transcript_prefix(summary: str | None, transcript: str | None) -> bool:
    if not summary or not transcript:
        return False
    return str(transcript).startswith(str(summary))


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _first_url(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, dict):
            url_list = value.get("url_list")
            if isinstance(url_list, list) and url_list:
                return str(url_list[0])
            if value.get("url"):
                return str(value["url"])
        if isinstance(value, list) and value:
            found = _first_url(*value)
            if found:
                return found
        if isinstance(value, str) and value:
            return value
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return decoded
        except json.JSONDecodeError:
            return [value] if value else []
    if isinstance(value, list):
        return value
    return [value]


def _role_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "positioning": row["positioning"],
        "target_directions": _row_json(row, "target_directions_json", []),
        "search_keywords": _row_json(row, "search_keywords_json", []),
        "avoid_directions": _row_json(row, "avoid_directions_json", []),
        "preferred_content": _row_json(row, "preferred_content_json", []),
        "forbidden_content": _row_json(row, "forbidden_content_json", []),
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _task_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "command": row["command"],
        "target_scope": row["target_scope"],
        "target_count_per_role": row["target_count_per_role"],
        "topic": row["topic"],
        "status": row["status"],
        "parsed": _row_json(row, "parsed_json", {}),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "summary": _row_json(row, "summary_json", {}),
        "error": row["error"],
    }


def _task_role_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "role_id": row["role_id"],
        "role_name": row["role_name"],
        "target_count": row["target_count"],
        "saved_count": row["saved_count"],
        "status": row["status"],
        "summary": _row_json(row, "summary_json", {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _collection_run_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "role_id": row["role_id"],
        "topic": row["topic"],
        "target_count": row["target_count"],
        "like_floor": row["like_floor"],
        "super_like_threshold": row["super_like_threshold"],
        "tool_provider": row["tool_provider"],
        "status": row["status"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "summary": _row_json(row, "summary_json", {}),
        "error": row["error"],
    }


def _candidate_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "task_id": row["task_id"],
        "role_id": row["role_id"],
        "source_key": row["source_key"],
        "source_url": row["source_url"],
        "title": row["title"],
        "author_name": row["author_name"],
        "platform_caption": row["platform_caption"],
        "metrics": _row_json(row, "metrics_json", {}),
        "source_package": _row_json(row, "source_package_json", {}),
        "raw": _row_json(row, "raw_json", {}),
        "status": row["status"],
        "selection_reason": row["selection_reason"],
        "skip_reason": row["skip_reason"],
        "skip_detail": row["skip_detail"],
        "threshold_mode": row["threshold_mode"],
        "material_id": row["material_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _material_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "task_id": row["task_id"],
        "role_id": row["role_id"],
        "source_role_id": row["source_role_id"],
        "source_url": row["source_url"],
        "title": row["title"],
        "clean_title": row["clean_title"],
        "platform_caption": row["platform_caption"],
        "caption_text": row["caption_text"],
        "hashtags": _row_json(row, "hashtags_json", []),
        "transcript_text": row["transcript_text"],
        "summary_text": row["summary_text"],
        "hook_text": row["hook_text"],
        "core_claim": row["core_claim"],
        "content_type": row["content_type"],
        "oral_script_pattern": row["oral_script_pattern"],
        "audience": row["audience"],
        "emotion_trigger": row["emotion_trigger"],
        "risk_level": row["risk_level"],
        "content_structure": _row_json(row, "content_structure_json", []),
        "key_points": _row_json(row, "key_points_json", []),
        "rewrite_angles": _row_json(row, "rewrite_angles_json", []),
        "usable_quotes": _row_json(row, "usable_quotes_json", []),
        "risk_notes": _row_json(row, "risk_notes_json", []),
        "recommended_platforms": _row_json(row, "recommended_platforms_json", []),
        "next_collection_keywords": _row_json(row, "next_collection_keywords_json", []),
        "author_name": row["author_name"],
        "author_sec_uid": row["author_sec_uid"],
        "author_profile_url": row["author_profile_url"],
        "author_douyin_id": row["author_douyin_id"],
        "work_id": row["work_id"],
        "work_short_url": row["work_short_url"],
        "source_platform": row["source_platform"],
        "post_time": row["post_time"],
        "duration_ms": row["duration_ms"],
        "cover_url": row["cover_url"],
        "video_url": row["video_url"],
        "audio_url": row["audio_url"],
        "author_identity_confidence": row["author_identity_confidence"],
        "metrics": _row_json(row, "metrics_json", {}),
        "material_understanding": _row_json(row, "material_understanding_json", {}),
        "understanding_provider": row["understanding_provider"],
        "understanding_model": row["understanding_model"],
        "sample_pool_clues": _row_json(row, "sample_pool_clues_json", []),
        "understanding_status": row["understanding_status"],
        "source_package": _row_json(row, "source_package_json", {}),
        "raw": _row_json(row, "raw_json", {}),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _douyin_author_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "sec_uid": row["sec_uid"],
        "uid": row["uid"],
        "douyin_id": row["douyin_id"],
        "nickname": row["nickname"],
        "signature": row["signature"],
        "avatar_url": row["avatar_url"],
        "profile_url": row["profile_url"],
        "ip_location": row["ip_location"],
        "follower_count": row["follower_count"],
        "following_count": row["following_count"],
        "aweme_count": row["aweme_count"],
        "total_favorited": row["total_favorited"],
        "source_material_id": row["source_material_id"],
        "source_work_id": row["source_work_id"],
        "fetched_at": row["fetched_at"],
        "raw": _row_json(row, "raw_json", {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _douyin_author_video_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "author_sec_uid": row["author_sec_uid"],
        "work_id": row["work_id"],
        "source_material_id": row["source_material_id"],
        "source_url": row["source_url"],
        "title": row["title"],
        "platform_caption": row["platform_caption"],
        "caption_text": row["caption_text"],
        "hashtags": _row_json(row, "hashtags_json", []),
        "post_time": row["post_time"],
        "duration_ms": row["duration_ms"],
        "cover_url": row["cover_url"],
        "metrics": _row_json(row, "metrics_json", {}),
        "source_package": _row_json(row, "source_package_json", {}),
        "raw": _row_json(row, "raw_json", {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _role_match_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "material_id": row["material_id"],
        "role_id": row["role_id"],
        "task_id": row["task_id"],
        "fit_score": row["fit_score"],
        "decision": row["decision"],
        "reasons": _row_json(row, "reasons_json", []),
        "matched_keywords": _row_json(row, "matched_keywords_json", []),
        "avoidance_notes": _row_json(row, "avoidance_notes_json", []),
        "created_at": row["created_at"],
    }


def _material_creation_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "material_id": row["material_id"],
        "role_id": row["role_id"],
        "content_package_id": row["content_package_id"],
        "task_id": row["task_id"],
        "platform": row["platform"],
        "rewrite_angle": row["rewrite_angle"],
        "status": row["status"],
        "metadata": _row_json(row, "metadata_json", {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _candidate_source_key(candidate: dict[str, Any]) -> str:
    source_package = candidate.get("source_package") or {}
    value = (
        source_package.get("source_link")
        or source_package.get("work_id")
        or source_package.get("title")
        or dumps(scrub_for_storage(source_package))
    )
    return str(value)


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
