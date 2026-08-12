from __future__ import annotations

import json
import hashlib
import re
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .migrations.material_inventory_v1 import ensure_material_inventory_schema

DEFAULT_DB_PATH = Path("data/mcn_ops.sqlite")


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    report_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS content_packages (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    media_paths_json TEXT NOT NULL DEFAULT '[]',
    cover_path TEXT,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
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
    confirmation_status TEXT NOT NULL DEFAULT 'draft',
    confirmed_at TEXT,
    needs_reconfirm INTEGER NOT NULL DEFAULT 0,
    profile_version INTEGER NOT NULL DEFAULT 1,
    role_baseline TEXT NOT NULL DEFAULT '',
    life_stage TEXT NOT NULL DEFAULT '',
    core_temperament TEXT NOT NULL DEFAULT '',
    speaking_posture TEXT NOT NULL DEFAULT '',
    target_audience_json TEXT NOT NULL DEFAULT '{}',
    fit_themes_json TEXT NOT NULL DEFAULT '[]',
    avoid_themes_json TEXT NOT NULL DEFAULT '[]',
    style_anchors_json TEXT NOT NULL DEFAULT '{}',
    expression_constraints_json TEXT NOT NULL DEFAULT '{}',
    forbidden_expressions_json TEXT NOT NULL DEFAULT '[]',
    typical_topics_json TEXT NOT NULL DEFAULT '[]',
    theme_map_json TEXT NOT NULL DEFAULT '{}',
    persona_packet_json TEXT NOT NULL DEFAULT '{}',
    source_evidence_json TEXT NOT NULL DEFAULT '{}',
    agent_suggestions_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ip_role_versions (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL DEFAULT '{}',
    change_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(role_id) REFERENCES ip_roles(id)
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

CREATE TABLE IF NOT EXISTS source_authors (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    platform_author_id TEXT NOT NULL,
    uid TEXT,
    account_id TEXT,
    display_name TEXT,
    signature TEXT,
    avatar_url TEXT,
    profile_url TEXT,
    ip_location TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    work_count INTEGER,
    total_favorited INTEGER,
    raw_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(platform, platform_author_id)
);

CREATE TABLE IF NOT EXISTS source_works (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    platform_work_id TEXT NOT NULL,
    author_id TEXT,
    source_url TEXT,
    short_url TEXT,
    title TEXT,
    caption_text TEXT,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    published_at TEXT,
    duration_ms INTEGER,
    cover_url TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(platform, platform_work_id),
    FOREIGN KEY(author_id) REFERENCES source_authors(id)
);

CREATE TABLE IF NOT EXISTS source_observations (
    id TEXT PRIMARY KEY,
    source_work_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_row_id TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    payload_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL,
    UNIQUE(source_table, source_row_id),
    FOREIGN KEY(source_work_id) REFERENCES source_works(id)
);

CREATE TABLE IF NOT EXISTS material_transcriptions (
    id TEXT PRIMARY KEY,
    source_work_id TEXT NOT NULL,
    identity_key TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    audio_sha256 TEXT,
    transcript_text TEXT NOT NULL,
    language TEXT,
    options_json TEXT NOT NULL DEFAULT '{}',
    provider_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(source_work_id) REFERENCES source_works(id)
);

CREATE TABLE IF NOT EXISTS collection_candidates (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT,
    role_id TEXT,
    source_work_id TEXT NOT NULL,
    status TEXT NOT NULL,
    selection_reason TEXT,
    skip_reason TEXT,
    skip_detail TEXT,
    threshold_mode TEXT,
    material_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, source_work_id),
    FOREIGN KEY(run_id) REFERENCES collection_runs(id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(source_work_id) REFERENCES source_works(id),
    FOREIGN KEY(material_id) REFERENCES collected_materials(id)
);

CREATE TABLE IF NOT EXISTS collected_materials (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT,
    role_id TEXT,
    source_role_id TEXT,
    source_work_id TEXT NOT NULL,
    transcription_id TEXT,
    clean_title TEXT,
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
    material_eligibility_json TEXT NOT NULL DEFAULT '{}',
    eligibility_status TEXT NOT NULL DEFAULT 'accepted',
    eligibility_provider TEXT NOT NULL DEFAULT 'local-rules',
    eligibility_version TEXT NOT NULL DEFAULT 'material-eligibility-v1',
    eligibility_reason_json TEXT NOT NULL DEFAULT '[]',
    content_form TEXT,
    knowledge_core_score REAL NOT NULL DEFAULT 0,
    oral_script_fit_score REAL NOT NULL DEFAULT 0,
    ip_fit_score REAL NOT NULL DEFAULT 0,
    reject_reason TEXT,
    material_understanding_json TEXT NOT NULL DEFAULT '{}',
    understanding_provider TEXT NOT NULL DEFAULT 'codex-agent',
    understanding_model TEXT NOT NULL DEFAULT 'gpt-5.5',
    sample_pool_clues_json TEXT NOT NULL DEFAULT '[]',
    understanding_status TEXT NOT NULL DEFAULT 'pending',
    status TEXT NOT NULL DEFAULT 'collected',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES collection_runs(id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(source_work_id) REFERENCES source_works(id),
    FOREIGN KEY(transcription_id) REFERENCES material_transcriptions(id)
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

CREATE TABLE IF NOT EXISTS creation_tasks (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    goal TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL,
    target_count INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    provider TEXT NOT NULL DEFAULT 'codex-agent',
    model TEXT NOT NULL DEFAULT 'gpt-5.5',
    allow_reuse_material INTEGER NOT NULL DEFAULT 0,
    context_json TEXT NOT NULL DEFAULT '{}',
    content_package_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(content_package_id) REFERENCES content_packages(id)
);

CREATE TABLE IF NOT EXISTS creation_stage_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    stage_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'needs_confirmation',
    provider TEXT NOT NULL DEFAULT 'codex-agent',
    model TEXT NOT NULL DEFAULT 'gpt-5.5',
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    output_markdown TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmed_at TEXT,
    FOREIGN KEY(task_id) REFERENCES creation_tasks(id)
);

CREATE TABLE IF NOT EXISTS creation_material_selections (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    selection_status TEXT NOT NULL DEFAULT 'selected',
    score REAL NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(task_id, material_id),
    FOREIGN KEY(task_id) REFERENCES creation_tasks(id),
    FOREIGN KEY(material_id) REFERENCES collected_materials(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id)
);

CREATE TABLE IF NOT EXISTS creation_drafts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    stage_run_id TEXT,
    draft_type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES creation_tasks(id),
    FOREIGN KEY(stage_run_id) REFERENCES creation_stage_runs(id)
);

CREATE TABLE IF NOT EXISTS creation_delivery_packages (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    content_package_id TEXT,
    platform TEXT NOT NULL,
    package_json TEXT NOT NULL DEFAULT '{}',
    markdown_path TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES creation_tasks(id),
    FOREIGN KEY(content_package_id) REFERENCES content_packages(id)
);

CREATE TABLE IF NOT EXISTS creation_feedback_events (
    id TEXT PRIMARY KEY,
    content_package_id TEXT NOT NULL,
    task_id TEXT,
    role_id TEXT,
    platform TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    notice TEXT NOT NULL DEFAULT '',
    human_note TEXT NOT NULL DEFAULT '',
    judgment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(content_package_id) REFERENCES content_packages(id),
    FOREIGN KEY(task_id) REFERENCES creation_tasks(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id)
);

CREATE TABLE IF NOT EXISTS risk_term_observations (
    id TEXT PRIMARY KEY,
    role_id TEXT,
    content_package_id TEXT,
    task_id TEXT,
    term TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    position TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '待验证',
    source TEXT NOT NULL DEFAULT 'creation',
    sample_text TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(content_package_id) REFERENCES content_packages(id),
    FOREIGN KEY(task_id) REFERENCES creation_tasks(id)
);

CREATE TABLE IF NOT EXISTS creation_learning_updates (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    source_event_ids_json TEXT NOT NULL DEFAULT '[]',
    target_file TEXT NOT NULL,
    proposed_markdown TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    applied_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(role_id) REFERENCES ip_roles(id)
);

CREATE TABLE IF NOT EXISTS provider_call_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    provider TEXT NOT NULL DEFAULT 'direct',
    operation TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER NOT NULL,
    cache_hit INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES collection_runs(id)
);

CREATE TABLE IF NOT EXISTS provider_call_cache (
    provider TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    operation TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(provider, request_fingerprint)
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
CREATE INDEX IF NOT EXISTS idx_collected_materials_source_work ON collected_materials(source_work_id);
CREATE INDEX IF NOT EXISTS idx_source_authors_display_name ON source_authors(platform, display_name);
CREATE INDEX IF NOT EXISTS idx_source_works_author ON source_works(author_id);
CREATE INDEX IF NOT EXISTS idx_source_observations_work ON source_observations(source_work_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_material_transcriptions_work ON material_transcriptions(source_work_id, created_at);
CREATE INDEX IF NOT EXISTS idx_provider_call_logs_run ON provider_call_logs(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_material_role_matches_material_id ON material_role_matches(material_id);
CREATE INDEX IF NOT EXISTS idx_material_role_matches_role_id ON material_role_matches(role_id);
CREATE INDEX IF NOT EXISTS idx_material_creations_material_id ON material_creations(material_id);
CREATE INDEX IF NOT EXISTS idx_material_creations_role_id ON material_creations(role_id);
CREATE INDEX IF NOT EXISTS idx_ip_role_versions_role_id ON ip_role_versions(role_id);
CREATE INDEX IF NOT EXISTS idx_creation_tasks_role_id ON creation_tasks(role_id);
CREATE INDEX IF NOT EXISTS idx_creation_stage_runs_task_stage ON creation_stage_runs(task_id, stage_key);
CREATE INDEX IF NOT EXISTS idx_creation_material_selections_task_id ON creation_material_selections(task_id);
CREATE INDEX IF NOT EXISTS idx_creation_feedback_events_role_id ON creation_feedback_events(role_id);
CREATE INDEX IF NOT EXISTS idx_risk_term_observations_role_id ON risk_term_observations(role_id);
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
    "material_eligibility_json": "TEXT NOT NULL DEFAULT '{}'",
    "eligibility_status": "TEXT NOT NULL DEFAULT 'accepted'",
    "eligibility_provider": "TEXT NOT NULL DEFAULT 'local-rules'",
    "eligibility_version": "TEXT NOT NULL DEFAULT 'material-eligibility-v1'",
    "eligibility_reason_json": "TEXT NOT NULL DEFAULT '[]'",
    "content_form": "TEXT",
    "knowledge_core_score": "REAL NOT NULL DEFAULT 0",
    "oral_script_fit_score": "REAL NOT NULL DEFAULT 0",
    "ip_fit_score": "REAL NOT NULL DEFAULT 0",
    "reject_reason": "TEXT",
}


IP_ROLE_CONFIRMATION_STATUSES = {"draft", "agent_suggested", "confirmed", "needs_reconfirm"}
MATERIAL_INVENTORY_CLASSES = {"formal_rewrite_base", "topic_clue"}
MATERIAL_INVENTORY_REVIEW_STATUSES = {"pending", "reviewed", "rejected"}

IP_ROLE_V2_COLUMNS: dict[str, str] = {
    "confirmation_status": "TEXT NOT NULL DEFAULT 'draft'",
    "confirmed_at": "TEXT",
    "needs_reconfirm": "INTEGER NOT NULL DEFAULT 0",
    "profile_version": "INTEGER NOT NULL DEFAULT 1",
    "role_baseline": "TEXT NOT NULL DEFAULT ''",
    "life_stage": "TEXT NOT NULL DEFAULT ''",
    "core_temperament": "TEXT NOT NULL DEFAULT ''",
    "speaking_posture": "TEXT NOT NULL DEFAULT ''",
    "target_audience_json": "TEXT NOT NULL DEFAULT '{}'",
    "fit_themes_json": "TEXT NOT NULL DEFAULT '[]'",
    "avoid_themes_json": "TEXT NOT NULL DEFAULT '[]'",
    "style_anchors_json": "TEXT NOT NULL DEFAULT '{}'",
    "expression_constraints_json": "TEXT NOT NULL DEFAULT '{}'",
    "forbidden_expressions_json": "TEXT NOT NULL DEFAULT '[]'",
    "typical_topics_json": "TEXT NOT NULL DEFAULT '[]'",
    "theme_map_json": "TEXT NOT NULL DEFAULT '{}'",
    "persona_packet_json": "TEXT NOT NULL DEFAULT '{}'",
    "source_evidence_json": "TEXT NOT NULL DEFAULT '{}'",
    "agent_suggestions_json": "TEXT NOT NULL DEFAULT '{}'",
    "notes": "TEXT NOT NULL DEFAULT ''",
}

IP_ROLE_RECONFIRM_FIELDS = {
    "positioning",
    "target_directions",
    "search_keywords",
    "avoid_directions",
    "preferred_content",
    "forbidden_content",
    "role_baseline",
    "life_stage",
    "core_temperament",
    "speaking_posture",
    "target_audience",
    "fit_themes",
    "avoid_themes",
    "style_anchors",
    "expression_constraints",
    "forbidden_expressions",
    "typical_topics",
    "theme_map",
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
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> Path:
        initialize_inventory_schema = not self.db_path.exists() or self.db_path.stat().st_size == 0
        with self.connect() as conn:
            if _has_legacy_collection_schema(conn):
                raise RuntimeError(
                    "Legacy collection schema detected. Run the explicit collection schema v3 migration first."
                )
            conn.executescript(SCHEMA)
            _migrate_ip_role_v2(conn)
            _migrate_schema_v2(conn)
            _migrate_creation_schema(conn)
            if initialize_inventory_schema:
                ensure_material_inventory_schema(conn)
        return self.db_path

    def create_content_package(
        self,
        *,
        title: str,
        body: str,
        media_paths: list[str],
        cover_path: str | None = None,
        hashtags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        content_id = new_id("content")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO content_packages(
                    id, title, body, media_paths_json, cover_path,
                    hashtags_json, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content_id,
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
        positioning: str | None = "",
        target_directions: list[str] | None = None,
        search_keywords: list[str] | None = None,
        avoid_directions: list[str] | None = None,
        preferred_content: list[str] | None = None,
        forbidden_content: list[str] | None = None,
        confirmation_status: str | None = None,
        role_baseline: str | None = None,
        life_stage: str | None = None,
        core_temperament: str | None = None,
        speaking_posture: str | None = None,
        target_audience: Any = None,
        fit_themes: list[str] | None = None,
        avoid_themes: list[str] | None = None,
        style_anchors: Any = None,
        expression_constraints: Any = None,
        forbidden_expressions: list[str] | None = None,
        typical_topics: list[str] | None = None,
        theme_map: Any = None,
        source_evidence: Any = None,
        agent_suggestions: Any = None,
        notes: str | None = None,
        enabled: bool | None = True,
    ) -> str:
        role_name = name.strip()
        if not role_name:
            raise ValueError("role name is required")
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM ip_roles WHERE name = ?", (role_name,)).fetchone()
            existing = _role_row_to_dict(row) if row else None
            role_id = existing["id"] if existing else new_id("role")
            status = _role_confirmation_status(
                confirmation_status
                or (str(existing.get("confirmation_status")) if existing else None)
                or "draft"
            )
            prepared = {
                "id": role_id,
                "name": role_name,
                "positioning": _preserve_text(positioning, existing, "positioning"),
                "target_directions": _preserve_list(target_directions, existing, "target_directions"),
                "search_keywords": _preserve_list(search_keywords, existing, "search_keywords"),
                "avoid_directions": _preserve_list(avoid_directions, existing, "avoid_directions"),
                "preferred_content": _preserve_list(preferred_content, existing, "preferred_content"),
                "forbidden_content": _preserve_list(forbidden_content, existing, "forbidden_content"),
                "confirmation_status": status,
                "confirmed_at": existing.get("confirmed_at") if existing else None,
                "needs_reconfirm": bool(existing.get("needs_reconfirm")) if existing else False,
                "profile_version": int(existing.get("profile_version") or 1) if existing else 1,
                "role_baseline": _preserve_text(role_baseline, existing, "role_baseline"),
                "life_stage": _preserve_text(life_stage, existing, "life_stage"),
                "core_temperament": _preserve_text(core_temperament, existing, "core_temperament"),
                "speaking_posture": _preserve_text(speaking_posture, existing, "speaking_posture"),
                "target_audience": _preserve_json(target_audience, existing, "target_audience", {}),
                "fit_themes": _preserve_list(fit_themes, existing, "fit_themes"),
                "avoid_themes": _preserve_list(avoid_themes, existing, "avoid_themes"),
                "style_anchors": _preserve_json(style_anchors, existing, "style_anchors", {}),
                "expression_constraints": _preserve_json(expression_constraints, existing, "expression_constraints", {}),
                "forbidden_expressions": _preserve_list(forbidden_expressions, existing, "forbidden_expressions"),
                "typical_topics": _preserve_list(typical_topics, existing, "typical_topics"),
                "theme_map": _preserve_json(theme_map, existing, "theme_map", {}),
                "source_evidence": _preserve_json(source_evidence, existing, "source_evidence", {}),
                "agent_suggestions": _preserve_json(agent_suggestions, existing, "agent_suggestions", {}),
                "notes": _preserve_text(notes, existing, "notes"),
                "enabled": bool(existing.get("enabled")) if enabled is None and existing else (True if enabled is None else bool(enabled)),
                "created_at": existing.get("created_at") if existing else timestamp,
                "updated_at": timestamp,
            }
            if existing and _ip_role_needs_reconfirm(existing, prepared):
                prepared["confirmation_status"] = "needs_reconfirm"
                prepared["needs_reconfirm"] = True
            elif prepared["confirmation_status"] == "confirmed":
                prepared["needs_reconfirm"] = False
            prepared["persona_packet"] = build_ip_role_persona_packet(prepared)
            conn.execute(
                """
                INSERT INTO ip_roles(
                    id, name, positioning, target_directions_json, search_keywords_json,
                    avoid_directions_json, preferred_content_json, forbidden_content_json,
                    confirmation_status, confirmed_at, needs_reconfirm, profile_version,
                    role_baseline, life_stage, core_temperament, speaking_posture,
                    target_audience_json, fit_themes_json, avoid_themes_json,
                    style_anchors_json, expression_constraints_json, forbidden_expressions_json,
                    typical_topics_json, theme_map_json, persona_packet_json,
                    source_evidence_json, agent_suggestions_json, notes,
                    enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    positioning = excluded.positioning,
                    target_directions_json = excluded.target_directions_json,
                    search_keywords_json = excluded.search_keywords_json,
                    avoid_directions_json = excluded.avoid_directions_json,
                    preferred_content_json = excluded.preferred_content_json,
                    forbidden_content_json = excluded.forbidden_content_json,
                    confirmation_status = excluded.confirmation_status,
                    confirmed_at = excluded.confirmed_at,
                    needs_reconfirm = excluded.needs_reconfirm,
                    profile_version = excluded.profile_version,
                    role_baseline = excluded.role_baseline,
                    life_stage = excluded.life_stage,
                    core_temperament = excluded.core_temperament,
                    speaking_posture = excluded.speaking_posture,
                    target_audience_json = excluded.target_audience_json,
                    fit_themes_json = excluded.fit_themes_json,
                    avoid_themes_json = excluded.avoid_themes_json,
                    style_anchors_json = excluded.style_anchors_json,
                    expression_constraints_json = excluded.expression_constraints_json,
                    forbidden_expressions_json = excluded.forbidden_expressions_json,
                    typical_topics_json = excluded.typical_topics_json,
                    theme_map_json = excluded.theme_map_json,
                    persona_packet_json = excluded.persona_packet_json,
                    source_evidence_json = excluded.source_evidence_json,
                    agent_suggestions_json = excluded.agent_suggestions_json,
                    notes = excluded.notes,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    role_id,
                    role_name,
                    prepared["positioning"],
                    dumps(prepared["target_directions"]),
                    dumps(prepared["search_keywords"]),
                    dumps(prepared["avoid_directions"]),
                    dumps(prepared["preferred_content"]),
                    dumps(prepared["forbidden_content"]),
                    prepared["confirmation_status"],
                    prepared["confirmed_at"],
                    int(prepared["needs_reconfirm"]),
                    prepared["profile_version"],
                    prepared["role_baseline"],
                    prepared["life_stage"],
                    prepared["core_temperament"],
                    prepared["speaking_posture"],
                    dumps(prepared["target_audience"]),
                    dumps(prepared["fit_themes"]),
                    dumps(prepared["avoid_themes"]),
                    dumps(prepared["style_anchors"]),
                    dumps(prepared["expression_constraints"]),
                    dumps(prepared["forbidden_expressions"]),
                    dumps(prepared["typical_topics"]),
                    dumps(prepared["theme_map"]),
                    dumps(prepared["persona_packet"]),
                    dumps(prepared["source_evidence"]),
                    dumps(prepared["agent_suggestions"]),
                    prepared["notes"],
                    int(prepared["enabled"]),
                    prepared["created_at"],
                    prepared["updated_at"],
                ),
            )
        return role_id

    def list_ip_roles(self, *, enabled_only: bool = False, confirmed_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM ip_roles"
        params: list[Any] = []
        where: list[str] = []
        if enabled_only or confirmed_only:
            where.append("enabled = 1")
        if confirmed_only:
            where.append("confirmation_status = ?")
            where.append("needs_reconfirm = 0")
            params.append("confirmed")
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at, name"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
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

    def export_ip_roles(self) -> list[dict[str, Any]]:
        return self.list_ip_roles()

    def build_ip_role_persona_packet(self, role_id: str | None = None, *, name: str | None = None) -> dict[str, Any]:
        role = self.get_ip_role(role_id, name=name)
        if not role:
            raise KeyError("role not found")
        packet = build_ip_role_persona_packet(role)
        with self.connect() as conn:
            conn.execute(
                "UPDATE ip_roles SET persona_packet_json = ?, updated_at = ? WHERE id = ?",
                (dumps(packet), now_iso(), role["id"]),
            )
        return packet

    def confirm_ip_role(self, role_id: str, *, change_reason: str = "") -> dict[str, Any]:
        role = self.get_ip_role(role_id)
        if not role:
            raise KeyError(f"role not found: {role_id}")
        timestamp = now_iso()
        has_confirmed_before = bool(role.get("confirmed_at"))
        next_version = int(role.get("profile_version") or 1) + (1 if has_confirmed_before else 0)
        role = {**role, "confirmation_status": "confirmed", "needs_reconfirm": False, "profile_version": next_version}
        packet = build_ip_role_persona_packet(role)
        snapshot = {**role, "persona_packet": packet, "confirmed_at": timestamp}
        version_id = new_id("rver")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE ip_roles
                SET confirmation_status = 'confirmed',
                    confirmed_at = ?,
                    needs_reconfirm = 0,
                    profile_version = ?,
                    persona_packet_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (timestamp, next_version, dumps(packet), timestamp, role_id),
            )
            conn.execute(
                """
                INSERT INTO ip_role_versions(
                    id, role_id, profile_version, snapshot_json, change_reason, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (version_id, role_id, next_version, dumps(snapshot), change_reason, timestamp),
            )
        updated = self.get_ip_role(role_id)
        return {
            "role_id": role_id,
            "version_id": version_id,
            "profile_version": next_version,
            "role": updated,
        }

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

    def _persist_source_package(
        self,
        source_package: dict[str, Any],
        *,
        raw: dict[str, Any] | None,
        run_id: str | None,
        observation_kind: str,
        provider: str | None = None,
    ) -> tuple[str, str, str | None]:
        platform = str(source_package.get("source_platform") or source_package.get("source_type") or "").strip().lower()
        source_url = str(source_package.get("source_link") or source_package.get("source_url") or "").strip()
        if not platform:
            platform = "douyin" if "douyin.com" in source_url else "unknown"
        platform_work_id = _source_package_platform_work_id(source_package, source_url=source_url, platform=platform)
        if not platform_work_id:
            raise ValueError("source package has no authoritative platform work id")

        author_id: str | None = None
        platform_author_id = str(source_package.get("author_sec_uid") or "").strip()
        display_name = str(source_package.get("author_name") or "").strip()
        if platform_author_id and display_name:
            author_id = self.upsert_source_author(
                platform=platform,
                platform_author_id=platform_author_id,
                platform_user_id=source_package.get("author_uid"),
                handle=source_package.get("author_douyin_id"),
                display_name=display_name,
                profile_url=source_package.get("author_profile_url"),
                profile=source_package.get("author_profile") or {},
            )

        caption = str(source_package.get("caption_text") or source_package.get("platform_caption") or "").strip()
        parsed = parse_caption(title=str(source_package.get("title") or ""), caption=caption)
        source_work_id = self.upsert_source_work(
            platform=platform,
            platform_work_id=platform_work_id,
            author_id=author_id,
            canonical_url=source_url or None,
            title=source_package.get("title"),
            caption_text=parsed["caption_text"],
            hashtags=source_package.get("hashtags") or parsed["hashtags"],
            published_at=source_package.get("post_time"),
            duration_ms=_optional_int(source_package.get("duration_ms")),
        )
        observation_id = self.insert_source_observation(
            source_work_id=source_work_id,
            provider=provider or str(source_package.get("provider") or "runtime"),
            observation_kind=observation_kind,
            run_id=run_id,
            metrics=source_package.get("public_metrics") or {},
            media={
                "cover_url": source_package.get("cover_url"),
                "video_url": source_package.get("video_url"),
                "audio_url": source_package.get("audio_url"),
            },
            raw=raw or {},
        )

        transcription_id: str | None = None
        transcript = str(source_package.get("transcript_text") or "").strip()
        if transcript:
            transcription_provider = str(source_package.get("transcription_provider") or provider or "runtime")
            transcription_model = str(source_package.get("transcription_model") or "unknown")
            transcription_result = (
                source_package.get("transcription_result")
                if isinstance(source_package.get("transcription_result"), dict)
                else {}
            )
            text_hash = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
            identity_key = f"runtime:{source_work_id}:{transcription_provider}:{transcription_model}:{text_hash}"
            transcription_id = self.insert_material_transcription(
                source_work_id=source_work_id,
                provider=transcription_provider,
                model=transcription_model,
                options_fingerprint=str(source_package.get("transcription_options_fingerprint") or "none"),
                identity_key=identity_key,
                transcript_text=transcript,
                audio_sha256=source_package.get("audio_sha256"),
                status=str(transcription_result.get("status") or "success"),
                audio_seconds=_optional_float(transcription_result.get("audio_seconds")),
                estimated_cost=_optional_float(transcription_result.get("estimated_cost")),
                cache_hit=bool(transcription_result.get("cache_hit")),
                provider_job_id=transcription_result.get("provider_job_id"),
                raw_result=(
                    transcription_result.get("raw_result")
                    if isinstance(transcription_result.get("raw_result"), dict)
                    else {}
                ),
            )
        return source_work_id, observation_id, transcription_id

    def source_package_for_work(
        self,
        source_work_id: str,
        *,
        transcription_id: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            work = conn.execute("SELECT * FROM source_works WHERE id = ?", (source_work_id,)).fetchone()
            if work is None:
                raise KeyError(f"source work not found: {source_work_id}")
            author = None
            if work["author_id"]:
                author = conn.execute("SELECT * FROM source_authors WHERE id = ?", (work["author_id"],)).fetchone()
            observation = conn.execute(
                """
                SELECT * FROM source_observations
                WHERE source_work_id = ?
                ORDER BY observed_at DESC, id DESC
                LIMIT 1
                """,
                (source_work_id,),
            ).fetchone()
            transcription = None
            if transcription_id:
                transcription = conn.execute(
                    "SELECT * FROM material_transcriptions WHERE id = ?",
                    (transcription_id,),
                ).fetchone()
            elif _table_exists(conn, "material_transcriptions"):
                transcription = conn.execute(
                    """
                    SELECT * FROM material_transcriptions
                    WHERE source_work_id = ?
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """,
                    (source_work_id,),
                ).fetchone()
        payload = _row_json(observation, "payload_json", {}) if observation else {}
        media = payload.get("media") or {}
        return {
            "source_work_id": source_work_id,
            "work_id": work["platform_work_id"],
            "source_link": work["source_url"],
            "work_short_url": work["short_url"],
            "source_platform": work["platform"],
            "title": work["title"],
            "platform_caption": work["caption_text"],
            "caption_text": work["caption_text"],
            "hashtags": _row_json(work, "hashtags_json", []),
            "post_time": work["published_at"],
            "duration_ms": work["duration_ms"],
            "cover_url": work["cover_url"] or media.get("cover_url"),
            "public_metrics": _row_json(observation, "metrics_json", {}) if observation else {},
            "author_name": author["display_name"] if author else None,
            "author_sec_uid": author["platform_author_id"] if author and work["platform"] == "douyin" else None,
            "author_profile_url": author["profile_url"] if author else None,
            "author_douyin_id": author["account_id"] if author and work["platform"] == "douyin" else None,
            "transcript_text": transcription["transcript_text"] if transcription else "",
            "transcription_provider": transcription["provider"] if transcription else None,
            "transcription_model": transcription["model"] if transcription else None,
            "transcription_result": _row_json(transcription, "provider_payload_json", {}) if transcription else {},
        }

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
        source_work_id, _, _ = self._persist_source_package(
            source_package,
            raw=candidate.get("raw") or {},
            run_id=run_id,
            observation_kind="search",
            provider=str(candidate.get("provider") or source_package.get("provider") or "runtime"),
        )
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM collection_candidates WHERE run_id = ? AND source_work_id = ?",
                (run_id, source_work_id),
            ).fetchone()
            candidate_id = existing["id"] if existing else new_id("cand")
            conn.execute(
                """
                INSERT INTO collection_candidates(
                    id, run_id, task_id, role_id, source_work_id, status,
                    selection_reason, skip_reason, skip_detail, threshold_mode,
                    material_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, source_work_id) DO UPDATE SET
                    task_id = excluded.task_id,
                    role_id = excluded.role_id,
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
                    source_work_id,
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
        result: list[dict[str, Any]] = []
        for row in rows:
            package = self.source_package_for_work(row["source_work_id"])
            result.append(
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "task_id": row["task_id"],
                    "role_id": row["role_id"],
                    "source_work_id": row["source_work_id"],
                    "source_key": package.get("source_link") or package.get("work_id"),
                    "source_url": package.get("source_link"),
                    "title": package.get("title"),
                    "author_name": package.get("author_name"),
                    "platform_caption": package.get("platform_caption"),
                    "metrics": package.get("public_metrics") or {},
                    "source_package": package,
                    "raw": {},
                    "status": row["status"],
                    "selection_reason": row["selection_reason"],
                    "skip_reason": row["skip_reason"],
                    "skip_detail": row["skip_detail"],
                    "threshold_mode": row["threshold_mode"],
                    "material_id": row["material_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

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
        provider = str(material_understanding.get("understanding_provider") or "codex-agent")
        model = str(material_understanding.get("understanding_model") or "gpt-5.5")
        promoted = _material_promoted_values(source_package, material_understanding, raw)
        eligibility = _material_eligibility_values(source_package)
        canonical_package = {
            **source_package,
            "caption_text": source_package.get("caption_text") or promoted["caption_text"],
            "hashtags": source_package.get("hashtags") or promoted["hashtags"],
            "post_time": source_package.get("post_time") or promoted["post_time"],
            "duration_ms": source_package.get("duration_ms") or promoted["duration_ms"],
            "cover_url": source_package.get("cover_url") or promoted["cover_url"],
            "video_url": source_package.get("video_url") or promoted["video_url"],
            "audio_url": source_package.get("audio_url") or promoted["audio_url"],
        }
        source_work_id, _, transcription_id = self._persist_source_package(
            canonical_package,
            raw=raw,
            run_id=run_id,
            observation_kind="material",
            provider=str(source_package.get("provider") or "runtime"),
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO collected_materials(
                    id, run_id, task_id, role_id, source_role_id, source_work_id,
                    transcription_id, clean_title, summary_text, hook_text, core_claim,
                    content_type, oral_script_pattern, audience, emotion_trigger,
                    risk_level, content_structure_json, key_points_json,
                    rewrite_angles_json, usable_quotes_json, risk_notes_json,
                    recommended_platforms_json, next_collection_keywords_json,
                    material_eligibility_json, eligibility_status, eligibility_provider,
                    eligibility_version, eligibility_reason_json, content_form,
                    knowledge_core_score, oral_script_fit_score, ip_fit_score, reject_reason,
                    material_understanding_json, understanding_provider,
                    understanding_model, sample_pool_clues_json, understanding_status,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_id,
                    run_id,
                    source_package.get("task_id"),
                    source_package.get("role_id"),
                    source_package.get("source_role_id") or source_package.get("role_id"),
                    source_work_id,
                    transcription_id,
                    promoted["clean_title"],
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
                    dumps(scrub_for_storage(eligibility["material_eligibility"])),
                    eligibility["eligibility_status"],
                    eligibility["eligibility_provider"],
                    eligibility["eligibility_version"],
                    dumps(scrub_for_storage(eligibility["eligibility_reasons"])),
                    eligibility["content_form"],
                    eligibility["knowledge_core_score"],
                    eligibility["oral_script_fit_score"],
                    eligibility["ip_fit_score"],
                    eligibility["reject_reason"],
                    dumps(scrub_for_storage(material_understanding)),
                    provider,
                    model,
                    dumps(scrub_for_storage(source_package.get("sample_pool_clues") or [])),
                    source_package.get("understanding_status") or "success",
                    timestamp,
                    timestamp,
                ),
            )
        return material_id

    def get_collected_material(self, material_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM collected_materials WHERE id = ?", (material_id,)).fetchone()
        return self._material_row_to_runtime_dict(row) if row else None

    def _material_row_to_runtime_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        package = self.source_package_for_work(
            row["source_work_id"],
            transcription_id=row["transcription_id"],
        )
        understanding = _row_json(row, "material_understanding_json", {})
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "task_id": row["task_id"],
            "role_id": row["role_id"],
            "source_role_id": row["source_role_id"],
            "source_work_id": row["source_work_id"],
            "transcription_id": row["transcription_id"],
            "source_url": package.get("source_link"),
            "title": package.get("title"),
            "clean_title": row["clean_title"],
            "platform_caption": package.get("platform_caption"),
            "caption_text": package.get("caption_text"),
            "hashtags": package.get("hashtags") or [],
            "transcript_text": package.get("transcript_text") or "",
            "transcription_provider": package.get("transcription_provider"),
            "transcription_model": package.get("transcription_model"),
            "transcription_result": package.get("transcription_result") or {},
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
            "author_name": package.get("author_name"),
            "author_sec_uid": package.get("author_sec_uid"),
            "author_profile_url": package.get("author_profile_url"),
            "author_douyin_id": package.get("author_douyin_id"),
            "work_id": package.get("work_id"),
            "work_short_url": package.get("work_short_url"),
            "source_platform": package.get("source_platform"),
            "post_time": package.get("post_time"),
            "duration_ms": package.get("duration_ms"),
            "cover_url": package.get("cover_url"),
            "video_url": None,
            "audio_url": None,
            "author_identity_confidence": None,
            "metrics": package.get("public_metrics") or {},
            "material_eligibility": _row_json(row, "material_eligibility_json", {}),
            "eligibility_status": row["eligibility_status"],
            "eligibility_provider": row["eligibility_provider"],
            "eligibility_version": row["eligibility_version"],
            "eligibility_reasons": _row_json(row, "eligibility_reason_json", []),
            "content_form": row["content_form"],
            "knowledge_core_score": row["knowledge_core_score"],
            "oral_script_fit_score": row["oral_script_fit_score"],
            "ip_fit_score": row["ip_fit_score"],
            "reject_reason": row["reject_reason"],
            "material_understanding": understanding,
            "understanding_provider": row["understanding_provider"],
            "understanding_model": row["understanding_model"],
            "sample_pool_clues": _row_json(row, "sample_pool_clues_json", []),
            "understanding_status": row["understanding_status"],
            "source_package": package,
            "raw": {},
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

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
        return [self._material_row_to_runtime_dict(row) for row in rows]

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

    def update_material_eligibility(
        self,
        material_id: str,
        *,
        eligibility: dict[str, Any],
        status: str | None = None,
    ) -> None:
        material = self.get_collected_material(material_id)
        if not material:
            raise KeyError(f"material not found: {material_id}")
        values = _material_eligibility_values({"material_eligibility": eligibility})
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE collected_materials
                SET material_eligibility_json = ?,
                    eligibility_status = ?,
                    eligibility_provider = ?,
                    eligibility_version = ?,
                    eligibility_reason_json = ?,
                    content_form = ?,
                    knowledge_core_score = ?,
                    oral_script_fit_score = ?,
                    ip_fit_score = ?,
                    reject_reason = ?,
                    status = COALESCE(?, status),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    dumps(scrub_for_storage(values["material_eligibility"])),
                    values["eligibility_status"],
                    values["eligibility_provider"],
                    values["eligibility_version"],
                    dumps(scrub_for_storage(values["eligibility_reasons"])),
                    values["content_form"],
                    values["knowledge_core_score"],
                    values["oral_script_fit_score"],
                    values["ip_fit_score"],
                    values["reject_reason"],
                    status,
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
        material = self.get_collected_material(material_id)
        if not material:
            raise KeyError(f"material not found: {material_id}")
        package = material.get("source_package") or {}
        sec_uid = str(author_sec_uid or package.get("author_sec_uid") or "").strip()
        display_name = str(author_name or package.get("author_name") or "").strip()
        author_id: str | None = None
        if sec_uid and display_name:
            author_id = self.upsert_source_author(
                platform=str(package.get("source_platform") or "douyin"),
                platform_author_id=sec_uid,
                handle=author_douyin_id or package.get("author_douyin_id"),
                display_name=display_name,
                profile_url=author_profile_url or package.get("author_profile_url"),
            )
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE source_works
                SET author_id = COALESCE(?, author_id),
                    platform_work_id = COALESCE(?, platform_work_id),
                    last_seen_at = ?
                WHERE id = ?
                """,
                (
                    author_id,
                    work_id,
                    now_iso(),
                    material["source_work_id"],
                ),
            )

    def upsert_source_author(
        self,
        *,
        platform: str,
        platform_author_id: str,
        display_name: str,
        platform_user_id: str | None = None,
        handle: str | None = None,
        signature: str | None = None,
        avatar_url: str | None = None,
        profile_url: str | None = None,
        profile: dict[str, Any] | None = None,
    ) -> str:
        platform = platform.strip().lower()
        platform_author_id = platform_author_id.strip()
        display_name = display_name.strip()
        if not platform or not platform_author_id or not display_name:
            raise ValueError("platform, platform_author_id and display_name are required")
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM source_authors WHERE platform = ? AND platform_author_id = ?",
                (platform, platform_author_id),
            ).fetchone()
            author_id = existing["id"] if existing else new_id("author")
            conn.execute(
                """
                INSERT INTO source_authors(
                    id, platform, platform_author_id, uid, account_id,
                    display_name, signature, avatar_url, profile_url, ip_location,
                    follower_count, following_count, work_count, total_favorited,
                    raw_json, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, platform_author_id) DO UPDATE SET
                    uid = COALESCE(excluded.uid, source_authors.uid),
                    account_id = COALESCE(excluded.account_id, source_authors.account_id),
                    display_name = excluded.display_name,
                    signature = COALESCE(excluded.signature, source_authors.signature),
                    avatar_url = COALESCE(excluded.avatar_url, source_authors.avatar_url),
                    profile_url = COALESCE(excluded.profile_url, source_authors.profile_url),
                    ip_location = COALESCE(excluded.ip_location, source_authors.ip_location),
                    follower_count = COALESCE(excluded.follower_count, source_authors.follower_count),
                    following_count = COALESCE(excluded.following_count, source_authors.following_count),
                    work_count = COALESCE(excluded.work_count, source_authors.work_count),
                    total_favorited = COALESCE(excluded.total_favorited, source_authors.total_favorited),
                    raw_json = excluded.raw_json,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    author_id,
                    platform,
                    platform_author_id,
                    platform_user_id,
                    handle,
                    display_name,
                    signature,
                    avatar_url,
                    profile_url,
                    (profile or {}).get("ip_location"),
                    _optional_int((profile or {}).get("follower_count")),
                    _optional_int((profile or {}).get("following_count")),
                    _optional_int((profile or {}).get("aweme_count") or (profile or {}).get("work_count")),
                    _optional_int((profile or {}).get("total_favorited")),
                    dumps(scrub_for_storage(profile or {})),
                    timestamp,
                    timestamp,
                ),
            )
        return author_id

    def get_source_author(self, author_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM source_authors WHERE id = ?", (author_id,)).fetchone()
        return _source_author_row_to_dict(row) if row else None

    def get_source_author_by_platform_id(
        self,
        platform: str,
        platform_author_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM source_authors WHERE platform = ? AND platform_author_id = ?",
                (platform.strip().lower(), platform_author_id.strip()),
            ).fetchone()
        return _source_author_row_to_dict(row) if row else None

    def list_source_authors(self, *, platform: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM source_authors"
        params: tuple[Any, ...] = ()
        if platform:
            query += " WHERE platform = ?"
            params = (platform.strip().lower(),)
        query += " ORDER BY last_seen_at DESC, display_name"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_source_author_row_to_dict(row) for row in rows]

    def upsert_source_work(
        self,
        *,
        platform: str,
        platform_work_id: str,
        author_id: str | None = None,
        canonical_url: str | None = None,
        title: str | None = None,
        caption_text: str | None = None,
        hashtags: list[str] | None = None,
        published_at: str | None = None,
        duration_ms: int | None = None,
    ) -> str:
        platform = platform.strip().lower()
        platform_work_id = platform_work_id.strip()
        if not platform or not platform_work_id:
            raise ValueError("platform and platform_work_id are required")
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM source_works WHERE platform = ? AND platform_work_id = ?",
                (platform, platform_work_id),
            ).fetchone()
            work_id = existing["id"] if existing else new_id("work")
            conn.execute(
                """
                INSERT INTO source_works(
                    id, platform, platform_work_id, author_id, source_url, title,
                    caption_text, hashtags_json, published_at, duration_ms,
                    raw_json, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                ON CONFLICT(platform, platform_work_id) DO UPDATE SET
                    author_id = COALESCE(excluded.author_id, source_works.author_id),
                    source_url = COALESCE(excluded.source_url, source_works.source_url),
                    title = COALESCE(excluded.title, source_works.title),
                    caption_text = COALESCE(excluded.caption_text, source_works.caption_text),
                    hashtags_json = excluded.hashtags_json,
                    published_at = COALESCE(excluded.published_at, source_works.published_at),
                    duration_ms = COALESCE(excluded.duration_ms, source_works.duration_ms),
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    work_id,
                    platform,
                    platform_work_id,
                    author_id,
                    canonical_url,
                    title,
                    caption_text,
                    dumps(_clean_list(hashtags)),
                    published_at,
                    duration_ms,
                    timestamp,
                    timestamp,
                ),
            )
        return work_id

    def get_source_work_by_platform_id(self, platform: str, platform_work_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM source_works WHERE platform = ? AND platform_work_id = ?",
                (platform.strip().lower(), platform_work_id.strip()),
            ).fetchone()
        return _source_work_row_to_dict(row) if row else None

    def list_source_works(self, *, author_id: str | None = None, platform: str | None = None) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if author_id:
            where.append("author_id = ?")
            params.append(author_id)
        if platform:
            where.append("platform = ?")
            params.append(platform.strip().lower())
        query = "SELECT * FROM source_works"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY published_at DESC, first_seen_at DESC, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_source_work_row_to_dict(row) for row in rows]

    def insert_source_observation(
        self,
        *,
        source_work_id: str,
        provider: str,
        observation_kind: str,
        run_id: str | None = None,
        metrics: dict[str, Any] | None = None,
        media: dict[str, Any] | None = None,
        raw: dict[str, Any] | None = None,
        observed_at: str | None = None,
    ) -> str:
        observation_id = new_id("obs")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_observations(
                    id, source_work_id, provider, observation_type, source_table,
                    source_row_id, metrics_json, payload_json, observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    source_work_id,
                    provider,
                    observation_kind,
                    f"runtime:{observation_kind}",
                    observation_id,
                    dumps(scrub_for_storage(metrics or {})),
                    dumps(scrub_for_storage({"run_id": run_id, "media": media or {}, "raw": raw or {}})),
                    observed_at or timestamp,
                ),
            )
        return observation_id

    def insert_material_transcription(
        self,
        *,
        source_work_id: str,
        provider: str,
        model: str,
        options_fingerprint: str,
        identity_key: str,
        transcript_text: str,
        status: str = "success",
        options: dict[str, Any] | None = None,
        audio_sha256: str | None = None,
        audio_seconds: float | None = None,
        estimated_cost: float | None = None,
        cache_hit: bool = False,
        provider_job_id: str | None = None,
        raw_result: dict[str, Any] | None = None,
    ) -> str:
        transcription_id = new_id("transcription")
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM material_transcriptions WHERE identity_key = ?",
                (identity_key,),
            ).fetchone()
            if existing:
                transcription_id = existing["id"]
            conn.execute(
                """
                INSERT INTO material_transcriptions(
                    id, source_work_id, identity_key, provider, model, audio_sha256,
                    transcript_text, options_json, provider_payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_key) DO UPDATE SET
                    transcript_text = excluded.transcript_text,
                    provider_payload_json = excluded.provider_payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    transcription_id,
                    source_work_id,
                    identity_key,
                    provider,
                    model,
                    audio_sha256,
                    transcript_text,
                    dumps(scrub_for_storage({**(options or {}), "options_fingerprint": options_fingerprint})),
                    dumps(
                        scrub_for_storage(
                            {
                                "status": status,
                                "audio_seconds": audio_seconds,
                                "estimated_cost": estimated_cost,
                                "cache_hit": cache_hit,
                                "provider_job_id": provider_job_id,
                                "raw_result": raw_result or {},
                            }
                        )
                    ),
                    timestamp,
                    timestamp,
                ),
            )
        return transcription_id

    def replace_material_transcription_text(
        self,
        material_id: str,
        transcript_text: str,
        *,
        provider: str = "manual",
        model: str = "manual",
    ) -> str:
        material = self.get_collected_material(material_id)
        if not material:
            raise KeyError(f"material not found: {material_id}")
        text_hash = hashlib.sha256(transcript_text.encode("utf-8")).hexdigest()
        transcription_id = self.insert_material_transcription(
            source_work_id=material["source_work_id"],
            provider=provider,
            model=model,
            options_fingerprint="manual",
            identity_key=f"manual:{material_id}:{text_hash}",
            transcript_text=transcript_text,
        )
        with self.connect() as conn:
            conn.execute(
                "UPDATE collected_materials SET transcription_id = ?, updated_at = ? WHERE id = ?",
                (transcription_id, now_iso(), material_id),
            )
        return transcription_id

    # Douyin normalization helpers backed by the provider-neutral source tables.
    def upsert_douyin_author(
        self,
        profile: dict[str, Any],
        *,
        source_material_id: str | None = None,
        source_work_id: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> str:
        del source_material_id, source_work_id
        raw_profile = raw or profile.get("raw") or {}
        if not isinstance(raw_profile, dict):
            raw_profile = {}
        sec_uid = str(profile.get("sec_uid") or raw_profile.get("sec_uid") or "").strip()
        nickname = str(profile.get("nickname") or raw_profile.get("nickname") or "").strip()
        avatar_url = profile.get("avatar_url") or _first_url(
            raw_profile.get("avatar_thumb"), raw_profile.get("avatar_medium"), raw_profile.get("avatar_larger")
        )
        share_info = raw_profile.get("share_info") if isinstance(raw_profile.get("share_info"), dict) else {}
        profile_url = profile.get("profile_url") or profile.get("share_url") or share_info.get("share_url")
        self.upsert_source_author(
            platform="douyin",
            platform_author_id=sec_uid,
            platform_user_id=profile.get("uid") or raw_profile.get("uid"),
            handle=profile.get("douyin_id") or raw_profile.get("unique_id") or raw_profile.get("short_id"),
            display_name=nickname,
            signature=profile.get("signature") or raw_profile.get("signature"),
            avatar_url=avatar_url,
            profile_url=profile_url,
            profile={**raw_profile, **{key: value for key, value in profile.items() if key != "raw"}},
        )
        return sec_uid

    def get_douyin_author(self, sec_uid: str) -> dict[str, Any] | None:
        author = self.get_source_author_by_platform_id("douyin", sec_uid)
        return _source_author_to_douyin_compat(author) if author else None

    def list_douyin_authors(self) -> list[dict[str, Any]]:
        return [_source_author_to_douyin_compat(author) for author in self.list_source_authors(platform="douyin")]

    def upsert_douyin_author_video(
        self,
        author_sec_uid: str,
        video: dict[str, Any],
        *,
        source_material_id: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> str:
        del source_material_id
        author = self.get_source_author_by_platform_id("douyin", author_sec_uid)
        if not author:
            raise KeyError(f"source author not found: douyin/{author_sec_uid}")
        raw_video = raw or video.get("raw") or {}
        if not isinstance(raw_video, dict):
            raw_video = {}
        platform_work_id = str(
            video.get("work_id") or video.get("id") or raw_video.get("aweme_id") or raw_video.get("id") or ""
        ).strip()
        caption = str(
            video.get("platform_caption") or video.get("caption") or raw_video.get("desc") or raw_video.get("caption") or ""
        ).strip()
        title = str(video.get("title") or raw_video.get("title") or caption).strip()
        parsed = parse_caption(title=title, caption=caption)
        work_id = self.upsert_source_work(
            platform="douyin",
            platform_work_id=platform_work_id,
            author_id=author["id"],
            canonical_url=video.get("source_url") or video.get("source_link") or video.get("share_url"),
            title=title or None,
            caption_text=parsed["caption_text"],
            hashtags=parsed["hashtags"],
            published_at=video.get("post_time") or raw_video.get("post_time") or raw_video.get("create_time"),
            duration_ms=_optional_int(video.get("duration_ms") or video.get("duration") or raw_video.get("duration")),
        )
        self.insert_source_observation(
            source_work_id=work_id,
            provider=str(video.get("provider") or "legacy"),
            observation_kind="author_post",
            metrics=video.get("metrics") or video.get("public_metrics") or {},
            media={"cover_url": video.get("cover_url") or raw_video.get("cover")},
            raw=raw_video,
        )
        return work_id

    def list_douyin_author_videos(self, author_sec_uid: str) -> list[dict[str, Any]]:
        author = self.get_source_author_by_platform_id("douyin", author_sec_uid)
        if not author:
            return []
        works = self.list_source_works(author_id=author["id"], platform="douyin")
        result: list[dict[str, Any]] = []
        with self.connect() as conn:
            for work in works:
                observation = conn.execute(
                    """
                    SELECT * FROM source_observations
                    WHERE source_work_id = ?
                    ORDER BY observed_at DESC, id DESC
                    LIMIT 1
                    """,
                    (work["id"],),
                ).fetchone()
                item = _source_work_to_douyin_compat(work, author_sec_uid)
                if observation:
                    item["metrics"] = _row_json(observation, "metrics_json", {})
                    payload = _row_json(observation, "payload_json", {})
                    media = payload.get("media") or {}
                    item["cover_url"] = media.get("cover_url")
                    item["raw"] = payload.get("raw") or {}
                item["source_package"] = {
                    "work_id": work["platform_work_id"],
                    "source_link": work.get("canonical_url"),
                    "title": work.get("title"),
                    "platform_caption": work.get("caption_text"),
                    "caption_text": work.get("caption_text"),
                    "hashtags": work.get("hashtags") or [],
                    "post_time": work.get("published_at"),
                    "duration_ms": work.get("duration_ms"),
                    "public_metrics": item["metrics"],
                    "author_name": author.get("display_name"),
                    "author_sec_uid": author_sec_uid,
                    "source_platform": "douyin",
                }
                result.append(item)
        return result

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

    def classify_material_inventory(
        self,
        *,
        material_id: str,
        role_id: str,
        topic_direction: str,
        content_mechanism: str,
        material_class: str,
        review_status: str,
        decision_source: str,
        classification_reasons: list[str],
        knowledge_subtype: str | None = None,
        reviewer: str | None = None,
        is_primary: bool = False,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            _require_material_inventory_schema(conn)
            classification_id = self._classify_material_inventory_conn(
                conn,
                material_id=material_id,
                role_id=role_id,
                topic_direction=topic_direction,
                content_mechanism=content_mechanism,
                material_class=material_class,
                is_primary=is_primary,
                review_status=review_status,
                decision_source=decision_source,
                classification_reasons=classification_reasons,
                knowledge_subtype=knowledge_subtype,
                reviewer=reviewer,
            )
            row = conn.execute(
                "SELECT * FROM material_inventory_classifications WHERE id = ?",
                (classification_id,),
            ).fetchone()
        return _material_inventory_classification_row_to_dict(row)

    def import_material_inventory(
        self,
        *,
        role_id: str,
        classifications: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not isinstance(classifications, list) or not classifications:
            raise ValueError("classifications must be a non-empty list")
        imported_ids: list[str] = []
        with self.connect() as conn:
            _require_material_inventory_schema(conn)
            for index, item in enumerate(classifications):
                if not isinstance(item, dict):
                    raise ValueError(f"classification at index {index} must be an object")
                required_fields = (
                    "material_id",
                    "topic_direction",
                    "content_mechanism",
                    "material_class",
                    "review_status",
                    "decision_source",
                    "classification_reasons",
                )
                missing_fields = [field for field in required_fields if field not in item]
                if missing_fields:
                    raise ValueError(
                        f"classification at index {index} is missing {', '.join(missing_fields)}"
                    )
                item_role_id = str(item.get("role_id") or role_id).strip()
                if item_role_id != role_id:
                    raise ValueError(f"classification at index {index} has a different role_id")
                imported_ids.append(
                    self._classify_material_inventory_conn(
                        conn,
                        material_id=item["material_id"],
                        role_id=role_id,
                        topic_direction=item["topic_direction"],
                        content_mechanism=item["content_mechanism"],
                        knowledge_subtype=item.get("knowledge_subtype"),
                        material_class=item["material_class"],
                        is_primary=item.get("is_primary", False),
                        review_status=item["review_status"],
                        reviewer=item.get("reviewer"),
                        decision_source=item["decision_source"],
                        classification_reasons=item["classification_reasons"],
                    )
                )
            rows = conn.execute(
                f"SELECT * FROM material_inventory_classifications WHERE id IN ({','.join('?' for _ in imported_ids)})",
                tuple(imported_ids),
            ).fetchall()
        by_id = {row["id"]: _material_inventory_classification_row_to_dict(row) for row in rows}
        return [by_id[classification_id] for classification_id in imported_ids]

    def list_material_inventory(
        self,
        *,
        role_id: str,
        topic_direction: str | None = None,
        material_class: str | None = None,
        review_status: str | None = None,
        include_used: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.get_ip_role(role_id):
            raise KeyError(f"role not found: {role_id}")
        where = ["mic.role_id = ?"]
        params: list[Any] = [role_id]
        if topic_direction is not None:
            where.append("mic.topic_direction = ?")
            params.append(_normalize_inventory_text(topic_direction, "topic_direction"))
        if material_class is not None:
            where.append("mic.material_class = ?")
            params.append(_inventory_choice(material_class, MATERIAL_INVENTORY_CLASSES, "material_class"))
        if review_status is not None:
            where.append("mic.review_status = ?")
            params.append(_inventory_choice(review_status, MATERIAL_INVENTORY_REVIEW_STATUSES, "review_status"))
        if not include_used:
            where.append(
                "NOT EXISTS (SELECT 1 FROM material_creations mc WHERE mc.material_id = mic.material_id AND mc.role_id = mic.role_id)"
            )
        query = f"""
            SELECT mic.*, cm.source_work_id, cm.clean_title, cm.status AS material_status,
                   cm.eligibility_status, cm.transcription_id,
                   mt.transcript_text, sw.platform, sw.platform_work_id,
                   EXISTS(
                       SELECT 1 FROM material_role_matches mrm
                       WHERE mrm.material_id = mic.material_id
                         AND mrm.role_id = mic.role_id
                         AND mrm.decision = 'accepted'
                   ) AS accepted_role_match
            FROM material_inventory_classifications mic
            JOIN collected_materials cm ON cm.id = mic.material_id
            LEFT JOIN material_transcriptions mt ON mt.id = cm.transcription_id
            JOIN source_works sw ON sw.id = cm.source_work_id
            WHERE {' AND '.join(where)}
            ORDER BY mic.topic_direction, mic.material_class, mic.updated_at DESC, mic.id
        """
        with self.connect() as conn:
            _require_material_inventory_schema(conn)
            rows = conn.execute(query, tuple(params)).fetchall()
            material_ids = sorted({str(row["material_id"]) for row in rows})
            creations: dict[str, list[dict[str, Any]]] = {material_id: [] for material_id in material_ids}
            if material_ids:
                creation_rows = conn.execute(
                    f"SELECT * FROM material_creations WHERE role_id = ? AND material_id IN ({','.join('?' for _ in material_ids)}) ORDER BY created_at, id",
                    (role_id, *material_ids),
                ).fetchall()
                for creation_row in creation_rows:
                    creations[str(creation_row["material_id"])].append(_material_creation_row_to_dict(creation_row))
        result: list[dict[str, Any]] = []
        for row in rows:
            item = _material_inventory_classification_row_to_dict(row)
            references = creations.get(item["material_id"], [])
            item.update(
                source_work_id=row["source_work_id"],
                source_platform=row["platform"],
                platform_work_id=row["platform_work_id"],
                material_title=row["clean_title"],
                material_status=row["material_status"],
                eligibility_status=row["eligibility_status"],
                accepted_role_match=bool(row["accepted_role_match"]),
                used=bool(references),
                creation_references=references,
            )
            item["formal_usable"] = (
                item["material_class"] == "formal_rewrite_base"
                and item["review_status"] == "reviewed"
                and item["material_status"] == "collected"
                and item["eligibility_status"] == "accepted"
                and item["accepted_role_match"]
                and bool(str(row["transcript_text"] or "").strip())
            )
            result.append(item)
        return result

    def list_pending_material_inventory(
        self,
        *,
        role_id: str,
        include_used: bool = False,
        include_pending: bool = False,
        include_rejected: bool = False,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        role = self.get_ip_role(role_id)
        if not role:
            raise KeyError(f"role not found: {role_id}")
        if role["confirmation_status"] != "confirmed" or role["needs_reconfirm"]:
            raise ValueError(f"role must be confirmed before inventory review: {role_id}")

        where = [
            "cm.status = 'collected'",
            "cm.eligibility_status = 'accepted'",
            "length(trim(mt.transcript_text)) > 0",
            "EXISTS (SELECT 1 FROM material_role_matches mrm WHERE mrm.material_id = cm.id AND mrm.role_id = ? AND mrm.decision = 'accepted')",
            "NOT EXISTS (SELECT 1 FROM collected_materials cm_reviewed JOIN material_inventory_classifications mic_reviewed ON mic_reviewed.material_id = cm_reviewed.id WHERE cm_reviewed.source_work_id = cm.source_work_id AND mic_reviewed.role_id = ? AND mic_reviewed.review_status = 'reviewed')",
        ]
        params: list[Any] = [role_id, role_id]
        allowed_existing: list[str] = []
        if include_pending:
            allowed_existing.append("'pending'")
        if include_rejected:
            allowed_existing.append("'rejected'")
        if allowed_existing:
            where.append(
                "(NOT EXISTS (SELECT 1 FROM collected_materials cm_any JOIN material_inventory_classifications mic_any ON mic_any.material_id = cm_any.id WHERE cm_any.source_work_id = cm.source_work_id AND mic_any.role_id = ?) "
                "OR EXISTS (SELECT 1 FROM collected_materials cm_allowed JOIN material_inventory_classifications mic_allowed ON mic_allowed.material_id = cm_allowed.id WHERE cm_allowed.source_work_id = cm.source_work_id AND mic_allowed.role_id = ? AND mic_allowed.review_status IN ("
                + ",".join(allowed_existing)
                + ")))"
            )
            params.extend([role_id, role_id])
        else:
            where.append(
                "NOT EXISTS (SELECT 1 FROM collected_materials cm_any JOIN material_inventory_classifications mic_any ON mic_any.material_id = cm_any.id WHERE cm_any.source_work_id = cm.source_work_id AND mic_any.role_id = ?)"
            )
            params.append(role_id)
        if not include_used:
            where.append(
                "NOT EXISTS (SELECT 1 FROM collected_materials cm_used JOIN material_creations mc ON mc.material_id = cm_used.id WHERE cm_used.source_work_id = cm.source_work_id AND mc.role_id = ?)"
            )
            params.append(role_id)
        if task_id is not None:
            where.append("cm.task_id = ?")
            params.append(_normalize_inventory_text(task_id, "task_id"))
        if run_id is not None:
            where.append("cm.run_id = ?")
            params.append(_normalize_inventory_text(run_id, "run_id"))

        query = f"""
            SELECT cm.id AS material_id, cm.source_work_id, cm.run_id, cm.task_id,
                   cm.clean_title, cm.summary_text, cm.created_at AS material_created_at,
                   mt.id AS transcription_id, mt.transcript_text, mt.provider AS transcription_provider,
                   mt.model AS transcription_model, sw.platform, sw.platform_work_id,
                   sw.source_url AS canonical_url, sw.caption_text,
                   (SELECT MAX(mrm.fit_score) FROM material_role_matches mrm
                    WHERE mrm.material_id = cm.id AND mrm.role_id = ? AND mrm.decision = 'accepted') AS fit_score
            FROM collected_materials cm
            JOIN material_transcriptions mt ON mt.id = cm.transcription_id
            JOIN source_works sw ON sw.id = cm.source_work_id
            WHERE {' AND '.join(where)}
            ORDER BY fit_score DESC, cm.created_at, cm.id
        """
        with self.connect() as conn:
            _require_material_inventory_schema(conn)
            rows = conn.execute(query, (role_id, *params)).fetchall()
            source_work_ids = [str(row["source_work_id"]) for row in rows]
            classifications_by_work: dict[str, list[dict[str, Any]]] = {
                source_work_id: [] for source_work_id in source_work_ids
            }
            if source_work_ids:
                classification_rows = conn.execute(
                    f"""
                    SELECT mic.*, cm.source_work_id
                    FROM material_inventory_classifications mic
                    JOIN collected_materials cm ON cm.id = mic.material_id
                    WHERE mic.role_id = ? AND cm.source_work_id IN ({','.join('?' for _ in source_work_ids)})
                    ORDER BY mic.created_at, mic.id
                    """,
                    (role_id, *source_work_ids),
                ).fetchall()
                for classification_row in classification_rows:
                    classifications_by_work[str(classification_row["source_work_id"])].append(
                        _material_inventory_classification_row_to_dict(classification_row)
                    )

        result: list[dict[str, Any]] = []
        seen_source_works: set[str] = set()
        for row in rows:
            source_work_id = str(row["source_work_id"])
            if source_work_id in seen_source_works:
                continue
            seen_source_works.add(source_work_id)
            result.append(
                {
                    "material_id": row["material_id"],
                    "source_work_id": source_work_id,
                    "run_id": row["run_id"],
                    "task_id": row["task_id"],
                    "title": row["clean_title"],
                    "summary_text": row["summary_text"],
                    "platform": row["platform"],
                    "platform_work_id": row["platform_work_id"],
                    "canonical_url": row["canonical_url"],
                    "caption_text": row["caption_text"],
                    "transcription_id": row["transcription_id"],
                    "transcript_text": row["transcript_text"],
                    "transcription_provider": row["transcription_provider"],
                    "transcription_model": row["transcription_model"],
                    "accepted_role_match_fit_score": row["fit_score"],
                    "existing_classifications": classifications_by_work.get(source_work_id, []),
                    "material_created_at": row["material_created_at"],
                }
            )
        return result

    def summarize_material_inventory(
        self,
        *,
        role_id: str,
        video_allocation: dict[str, int] | None = None,
        formal_base_targets: dict[str, int] | None = None,
        batch_key: str | None = None,
        include_used: bool = False,
    ) -> dict[str, Any]:
        normalized_video_allocation = _normalize_inventory_allocation(video_allocation or {})
        normalized_formal_targets = _normalize_inventory_allocation(formal_base_targets or {})
        rows = self.list_material_inventory(role_id=role_id, include_used=True)
        topic_names = sorted(
            {row["topic_direction"] for row in rows}
            | set(normalized_video_allocation)
            | set(normalized_formal_targets)
        )
        topics_by_material: dict[str, set[str]] = {}
        for row in rows:
            topics_by_material.setdefault(row["material_id"], set()).add(row["topic_direction"])
        overlap_ids = {material_id for material_id, topics in topics_by_material.items() if len(topics) > 1}

        def summarize(items: list[dict[str, Any]], required_count: int | None = None) -> dict[str, Any]:
            material_ids = {item["material_id"] for item in items}
            source_work_ids = {item["source_work_id"] for item in items}
            formal_ids = {
                item["material_id"]
                for item in items
                if item["material_class"] == "formal_rewrite_base" and item["review_status"] == "reviewed"
            }
            reviewed_formal_ids = {
                item["material_id"]
                for item in items
                if item["material_class"] == "formal_rewrite_base" and item["review_status"] == "reviewed"
            }
            clue_ids = {
                item["material_id"]
                for item in items
                if item["material_class"] == "topic_clue" and item["review_status"] == "reviewed"
            }
            rejected_ids = {item["material_id"] for item in items if item["review_status"] == "rejected"}
            used_ids = {item["material_id"] for item in items if item["used"]}
            usable_formal_items = [
                item for item in items if item["formal_usable"] and item["is_primary"]
            ]
            usable_formal_ids = {item["material_id"] for item in usable_formal_items}
            usable_formal_source_ids = {item["source_work_id"] for item in usable_formal_items}
            used_source_ids = {item["source_work_id"] for item in items if item["used"]}
            unused_formal_source_ids = usable_formal_source_ids - used_source_ids
            available_source_ids = usable_formal_source_ids if include_used else unused_formal_source_ids
            result = {
                "total_classified_materials": len(material_ids),
                "distinct_source_works": len(source_work_ids),
                "formal_rewrite_bases": len(formal_ids),
                "reviewed_formal_bases": len(reviewed_formal_ids),
                "primary_reviewed_formal_bases": len(usable_formal_source_ids),
                "topic_clues": len(clue_ids),
                "rejected_materials": len(rejected_ids),
                "unused_formal_rewrite_bases": len(unused_formal_source_ids),
                "used_formal_rewrite_bases": len(usable_formal_source_ids & used_source_ids),
                "used_materials": len(used_ids),
                "cross_topic_overlaps": len(material_ids & overlap_ids),
                "available_formal_rewrite_bases": len(available_source_ids),
            }
            if required_count is not None:
                result.update(
                    target_formal_base_count=required_count,
                    shortage=max(required_count - len(available_source_ids), 0),
                    surplus=max(len(available_source_ids) - required_count, 0),
                )
            return result

        topics = []
        for topic in topic_names:
            topic_rows = [row for row in rows if row["topic_direction"] == topic]
            topic_summary = summarize(
                topic_rows,
                normalized_formal_targets.get(topic) if topic in normalized_formal_targets else None,
            )
            topics.append(
                {
                    "topic_direction": topic,
                    "planned_video_count": normalized_video_allocation.get(topic, 0),
                    **topic_summary,
                }
            )
        return {
            "role_id": role_id,
            "batch_key": batch_key,
            "include_used": include_used,
            "planned_video_total": sum(normalized_video_allocation.values()),
            "target_formal_base_total": sum(normalized_formal_targets.values()),
            "totals": summarize(rows),
            "cross_topic_overlap_materials": [
                {"material_id": material_id, "topic_directions": sorted(topics_by_material[material_id])}
                for material_id in sorted(overlap_ids)
            ],
            "topics": topics,
        }

    def _classify_material_inventory_conn(
        self,
        conn: sqlite3.Connection,
        *,
        material_id: Any,
        role_id: Any,
        topic_direction: Any,
        content_mechanism: Any,
        material_class: Any,
        is_primary: Any,
        review_status: Any,
        decision_source: Any,
        classification_reasons: Any,
        knowledge_subtype: Any = None,
        reviewer: Any = None,
    ) -> str:
        material_id = _normalize_inventory_text(material_id, "material_id")
        role_id = _normalize_inventory_text(role_id, "role_id")
        topic_direction = _normalize_inventory_text(topic_direction, "topic_direction")
        content_mechanism = _normalize_inventory_text(content_mechanism, "content_mechanism")
        knowledge_subtype = _normalize_inventory_optional_text(knowledge_subtype, "knowledge_subtype")
        reviewer = _normalize_inventory_optional_text(reviewer, "reviewer")
        decision_source = _normalize_inventory_text(decision_source, "decision_source")
        material_class = _inventory_choice(material_class, MATERIAL_INVENTORY_CLASSES, "material_class")
        is_primary = _normalize_inventory_bool(is_primary, "is_primary")
        review_status = _inventory_choice(review_status, MATERIAL_INVENTORY_REVIEW_STATUSES, "review_status")
        reasons = _inventory_reasons(classification_reasons)

        role = conn.execute("SELECT * FROM ip_roles WHERE id = ?", (role_id,)).fetchone()
        if role is None:
            raise KeyError(f"role not found: {role_id}")
        if role["confirmation_status"] != "confirmed" or bool(role["needs_reconfirm"]):
            raise ValueError(f"role must be confirmed before inventory classification: {role_id}")
        material = conn.execute(
            """
            SELECT cm.*, mt.transcript_text
            FROM collected_materials cm
            LEFT JOIN material_transcriptions mt ON mt.id = cm.transcription_id
            WHERE cm.id = ?
            """,
            (material_id,),
        ).fetchone()
        if material is None:
            raise KeyError(f"material not found: {material_id}")
        if material_class == "formal_rewrite_base" and review_status == "reviewed":
            accepted_match = conn.execute(
                """
                SELECT 1 FROM material_role_matches
                WHERE material_id = ? AND role_id = ? AND decision = 'accepted'
                LIMIT 1
                """,
                (material_id, role_id),
            ).fetchone()
            if (
                material["status"] != "collected"
                or material["eligibility_status"] != "accepted"
                or not str(material["transcript_text"] or "").strip()
                or accepted_match is None
            ):
                raise ValueError(
                    f"material is not eligible as a reviewed formal rewrite base for role {role_id}: {material_id}"
                )

        existing = conn.execute(
            """
            SELECT id, created_at FROM material_inventory_classifications
            WHERE material_id = ? AND role_id = ? AND topic_direction = ?
            """,
            (material_id, role_id, topic_direction),
        ).fetchone()
        classification_id = existing["id"] if existing else new_id("minv")
        timestamp = now_iso()
        conn.execute(
            """
            INSERT INTO material_inventory_classifications(
                id, material_id, role_id, topic_direction, content_mechanism,
                knowledge_subtype, material_class, is_primary, review_status, reviewer,
                decision_source, classification_reasons_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(material_id, role_id, topic_direction) DO UPDATE SET
                content_mechanism = excluded.content_mechanism,
                knowledge_subtype = excluded.knowledge_subtype,
                material_class = excluded.material_class,
                is_primary = excluded.is_primary,
                review_status = excluded.review_status,
                reviewer = excluded.reviewer,
                decision_source = excluded.decision_source,
                classification_reasons_json = excluded.classification_reasons_json,
                updated_at = excluded.updated_at
            """,
            (
                classification_id,
                material_id,
                role_id,
                topic_direction,
                content_mechanism,
                knowledge_subtype,
                material_class,
                int(is_primary),
                review_status,
                reviewer,
                decision_source,
                dumps(reasons),
                existing["created_at"] if existing else timestamp,
                timestamp,
            ),
        )
        return classification_id

    def create_creation_task(
        self,
        *,
        role_id: str,
        topic: str,
        goal: str,
        platform: str,
        target_count: int,
        provider: str = "codex-agent",
        model: str = "gpt-5.5",
        allow_reuse_material: bool = False,
        context: dict[str, Any] | None = None,
    ) -> str:
        task_id = new_id("createtask")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO creation_tasks(
                    id, role_id, topic, goal, platform, target_count, status,
                    provider, model, allow_reuse_material, context_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    role_id,
                    topic,
                    goal,
                    platform,
                    target_count,
                    "draft",
                    provider,
                    model,
                    int(allow_reuse_material),
                    dumps(scrub_for_storage(context or {})),
                    timestamp,
                    timestamp,
                ),
            )
        return task_id

    def get_creation_task(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM creation_tasks WHERE id = ?", (task_id,)).fetchone()
        return _creation_task_row_to_dict(row) if row else None

    def update_creation_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        content_package_id: str | None = None,
        context: dict[str, Any] | None = None,
        completed: bool = False,
    ) -> None:
        task = self.get_creation_task(task_id)
        if not task:
            raise KeyError(f"creation task not found: {task_id}")
        next_context = task.get("context") or {}
        if context:
            next_context = {**next_context, **context}
        completed_at = now_iso() if completed else task.get("completed_at")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE creation_tasks
                SET status = COALESCE(?, status),
                    content_package_id = COALESCE(?, content_package_id),
                    context_json = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    content_package_id,
                    dumps(scrub_for_storage(next_context)),
                    completed_at,
                    now_iso(),
                    task_id,
                ),
            )

    def insert_creation_stage_run(
        self,
        *,
        task_id: str,
        stage_key: str,
        status: str,
        provider: str,
        model: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        output_markdown: str = "",
        note: str = "",
    ) -> str:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM creation_stage_runs WHERE task_id = ? AND stage_key = ?",
                (task_id, stage_key),
            ).fetchone()
            version = int(row["version"] or 0) + 1
            stage_run_id = new_id("cstage")
            conn.execute(
                """
                INSERT INTO creation_stage_runs(
                    id, task_id, stage_key, status, provider, model, input_json,
                    output_json, output_markdown, note, version, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stage_run_id,
                    task_id,
                    stage_key,
                    status,
                    provider,
                    model,
                    dumps(scrub_for_storage(input_data or {})),
                    dumps(scrub_for_storage(output_data or {})),
                    output_markdown,
                    note,
                    version,
                    timestamp,
                    timestamp,
                ),
            )
        return stage_run_id

    def update_creation_stage_status(self, stage_run_id: str, status: str) -> None:
        confirmed_at = now_iso() if status == "confirmed" else None
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE creation_stage_runs
                SET status = ?, confirmed_at = COALESCE(?, confirmed_at), updated_at = ?
                WHERE id = ?
                """,
                (status, confirmed_at, now_iso(), stage_run_id),
            )

    def list_creation_stage_runs(self, task_id: str, *, stage_key: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM creation_stage_runs WHERE task_id = ?"
        params: list[Any] = [task_id]
        if stage_key:
            query += " AND stage_key = ?"
            params.append(stage_key)
        query += " ORDER BY created_at, version, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_creation_stage_run_row_to_dict(row) for row in rows]

    def latest_creation_stage_run(self, task_id: str, stage_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM creation_stage_runs
                WHERE task_id = ? AND stage_key = ?
                ORDER BY version DESC, created_at DESC
                LIMIT 1
                """,
                (task_id, stage_key),
            ).fetchone()
        return _creation_stage_run_row_to_dict(row) if row else None

    def upsert_creation_material_selection(
        self,
        *,
        task_id: str,
        material_id: str,
        role_id: str,
        selection_status: str,
        score: float,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        selection_id = new_id("csel")
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM creation_material_selections WHERE task_id = ? AND material_id = ?",
                (task_id, material_id),
            ).fetchone()
            if existing:
                selection_id = existing["id"]
            conn.execute(
                """
                INSERT INTO creation_material_selections(
                    id, task_id, material_id, role_id, selection_status, score,
                    reason, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, material_id) DO UPDATE SET
                    role_id = excluded.role_id,
                    selection_status = excluded.selection_status,
                    score = excluded.score,
                    reason = excluded.reason,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    selection_id,
                    task_id,
                    material_id,
                    role_id,
                    selection_status,
                    score,
                    reason,
                    dumps(scrub_for_storage(metadata or {})),
                    timestamp,
                    timestamp,
                ),
            )
        return selection_id

    def list_creation_material_selections(
        self,
        task_id: str,
        *,
        selection_status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM creation_material_selections WHERE task_id = ?"
        params: list[Any] = [task_id]
        if selection_status:
            query += " AND selection_status = ?"
            params.append(selection_status)
        query += " ORDER BY score DESC, created_at, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_creation_material_selection_row_to_dict(row) for row in rows]

    def insert_creation_draft(
        self,
        *,
        task_id: str,
        stage_run_id: str | None,
        draft_type: str,
        title: str,
        body: str,
        status: str = "draft",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        draft_id = new_id("cdraft")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO creation_drafts(
                    id, task_id, stage_run_id, draft_type, title, body, status,
                    metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    task_id,
                    stage_run_id,
                    draft_type,
                    title,
                    body,
                    status,
                    dumps(scrub_for_storage(metadata or {})),
                    timestamp,
                    timestamp,
                ),
            )
        return draft_id

    def list_creation_drafts(self, task_id: str, *, draft_type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM creation_drafts WHERE task_id = ?"
        params: list[Any] = [task_id]
        if draft_type:
            query += " AND draft_type = ?"
            params.append(draft_type)
        query += " ORDER BY created_at, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_creation_draft_row_to_dict(row) for row in rows]

    def insert_creation_delivery_package(
        self,
        *,
        task_id: str,
        platform: str,
        package: dict[str, Any],
        content_package_id: str | None = None,
        markdown_path: str | None = None,
        status: str = "draft",
    ) -> str:
        package_id = new_id("cdeliv")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO creation_delivery_packages(
                    id, task_id, content_package_id, platform, package_json,
                    markdown_path, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    package_id,
                    task_id,
                    content_package_id,
                    platform,
                    dumps(scrub_for_storage(package)),
                    markdown_path,
                    status,
                    timestamp,
                    timestamp,
                ),
            )
        return package_id

    def list_creation_delivery_packages(self, task_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM creation_delivery_packages WHERE task_id = ? ORDER BY created_at, id",
                (task_id,),
            ).fetchall()
        return [_creation_delivery_package_row_to_dict(row) for row in rows]

    def insert_creation_feedback_event(
        self,
        *,
        content_package_id: str,
        platform: str,
        metrics: dict[str, Any] | None = None,
        notice: str = "",
        human_note: str = "",
        judgment: str = "",
        task_id: str | None = None,
        role_id: str | None = None,
    ) -> str:
        feedback_id = new_id("cfeed")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO creation_feedback_events(
                    id, content_package_id, task_id, role_id, platform,
                    metrics_json, notice, human_note, judgment, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    content_package_id,
                    task_id,
                    role_id,
                    platform,
                    dumps(scrub_for_storage(metrics or {})),
                    notice,
                    human_note,
                    judgment,
                    now_iso(),
                ),
            )
        return feedback_id

    def list_creation_feedback_events(
        self,
        *,
        role_id: str | None = None,
        content_package_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if role_id:
            where.append("role_id = ?")
            params.append(role_id)
        if content_package_id:
            where.append("content_package_id = ?")
            params.append(content_package_id)
        query = "SELECT * FROM creation_feedback_events"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at DESC, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_creation_feedback_event_row_to_dict(row) for row in rows]

    def insert_creation_stage_feedback_event(
        self,
        *,
        task_id: str,
        role_id: str,
        stage_key: str,
        platform: str = "",
        human_note: str = "",
        judgment: str = "",
        status: str = "recorded",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        feedback_id = new_id("csfeed")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO creation_stage_feedback_events(
                    id, task_id, role_id, stage_key, platform,
                    human_note, judgment, status, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    task_id,
                    role_id,
                    stage_key,
                    platform,
                    human_note,
                    judgment,
                    status,
                    dumps(scrub_for_storage(metadata or {})),
                    now_iso(),
                ),
            )
        return feedback_id

    def list_creation_stage_feedback_events(
        self,
        *,
        role_id: str | None = None,
        task_id: str | None = None,
        stage_key: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if role_id:
            where.append("role_id = ?")
            params.append(role_id)
        if task_id:
            where.append("task_id = ?")
            params.append(task_id)
        if stage_key:
            where.append("stage_key = ?")
            params.append(stage_key)
        query = "SELECT * FROM creation_stage_feedback_events"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at DESC, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_creation_stage_feedback_event_row_to_dict(row) for row in rows]

    def insert_risk_term_observation(
        self,
        *,
        term: str,
        risk_level: str,
        status: str = "待验证",
        position: str = "",
        source: str = "creation",
        sample_text: str = "",
        role_id: str | None = None,
        content_package_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        observation_id = new_id("riskobs")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO risk_term_observations(
                    id, role_id, content_package_id, task_id, term, risk_level,
                    position, status, source, sample_text, metadata_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    role_id,
                    content_package_id,
                    task_id,
                    term,
                    risk_level,
                    position,
                    status,
                    source,
                    sample_text,
                    dumps(scrub_for_storage(metadata or {})),
                    timestamp,
                    timestamp,
                ),
            )
        return observation_id

    def list_risk_term_observations(self, *, role_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM risk_term_observations"
        params: list[Any] = []
        if role_id:
            query += " WHERE role_id = ?"
            params.append(role_id)
        query += " ORDER BY created_at DESC, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_risk_term_observation_row_to_dict(row) for row in rows]

    def insert_creation_learning_update(
        self,
        *,
        role_id: str,
        target_file: str,
        proposed_markdown: str,
        source_event_ids: list[str] | None = None,
        status: str = "pending",
    ) -> str:
        update_id = new_id("clearn")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO creation_learning_updates(
                    id, role_id, source_event_ids_json, target_file,
                    proposed_markdown, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    update_id,
                    role_id,
                    dumps(_clean_list(source_event_ids)),
                    target_file,
                    proposed_markdown,
                    status,
                    timestamp,
                    timestamp,
                ),
            )
        return update_id

    def get_creation_learning_update(self, update_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM creation_learning_updates WHERE id = ?", (update_id,)).fetchone()
        return _creation_learning_update_row_to_dict(row) if row else None

    def list_creation_learning_updates(
        self,
        *,
        role_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if role_id:
            where.append("role_id = ?")
            params.append(role_id)
        if status:
            where.append("status = ?")
            params.append(status)
        query = "SELECT * FROM creation_learning_updates"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at DESC, id"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_creation_learning_update_row_to_dict(row) for row in rows]

    def update_creation_learning_update_status(self, update_id: str, status: str) -> None:
        applied_at = now_iso() if status == "applied" else None
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE creation_learning_updates
                SET status = ?, applied_at = COALESCE(?, applied_at), updated_at = ?
                WHERE id = ?
                """,
                (status, applied_at, now_iso(), update_id),
            )

    def log_collection_call(
        self,
        *,
        run_id: str | None,
        provider: str,
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
                INSERT INTO provider_call_logs(
                    id, run_id, provider, operation, request_fingerprint, status,
                    error, duration_ms, cache_hit, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    run_id,
                    provider,
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

    def get_cached_collection_call(
        self,
        request_fingerprint: str,
        *,
        provider: str = "legacy",
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT response_json
                FROM provider_call_cache
                WHERE provider = ? AND request_fingerprint = ?
                """,
                (provider, request_fingerprint),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE provider_call_cache
                    SET hit_count = hit_count + 1, updated_at = ?
                    WHERE provider = ? AND request_fingerprint = ?
                    """,
                    (now_iso(), provider, request_fingerprint),
                )
        return loads(row["response_json"], {}) if row else None

    def put_cached_collection_call(
        self,
        tool_name: str,
        request_fingerprint: str,
        response: dict[str, Any],
        *,
        provider: str = "legacy",
    ) -> None:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_call_cache(
                    provider, request_fingerprint, operation, response_json, created_at, updated_at, hit_count
                )
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(provider, request_fingerprint) DO UPDATE SET
                    operation = excluded.operation,
                    response_json = excluded.response_json,
                    updated_at = excluded.updated_at
                """,
                (
                    provider,
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
                SELECT provider, operation, status, COUNT(*) AS count, SUM(cache_hit) AS cache_hits
                FROM provider_call_logs
                WHERE run_id = ?
                GROUP BY provider, operation, status
                ORDER BY provider, operation, status
                """,
                (run_id,),
            ).fetchall()
        return {
            "total_calls": sum(int(row["count"]) for row in rows),
            "cache_hits": sum(int(row["cache_hits"] or 0) for row in rows),
            "by_tool": [
                {
                    "provider": row["provider"],
                    "tool_name": row["operation"],
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
                SELECT l.provider, l.operation, l.status, COUNT(*) AS count, SUM(l.cache_hit) AS cache_hits
                FROM provider_call_logs l
                JOIN collection_runs r ON r.id = l.run_id
                WHERE r.task_id = ?
                GROUP BY l.provider, l.operation, l.status
                ORDER BY l.provider, l.operation, l.status
                """,
                (task_id,),
            ).fetchall()
        return {
            "total_calls": sum(int(row["count"]) for row in rows),
            "cache_hits": sum(int(row["cache_hits"] or 0) for row in rows),
            "by_tool": [
                {
                    "provider": row["provider"],
                    "tool_name": row["operation"],
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


def _json_or_default(value: Any, default: Any) -> Any:
    if value is None:
        return default
    return value


def _preserve_text(value: str | None, existing: dict[str, Any] | None, key: str) -> str:
    if value is None and existing is not None:
        return str(existing.get(key) or "")
    return str(value or "")


def _preserve_list(value: list[str] | None, existing: dict[str, Any] | None, key: str) -> list[str]:
    if value is None and existing is not None:
        return _clean_list(existing.get(key) or [])
    return _clean_list(value)


def _preserve_json(value: Any, existing: dict[str, Any] | None, key: str, default: Any) -> Any:
    if value is None and existing is not None:
        return existing.get(key, default)
    return _json_or_default(value, default)


def _role_confirmation_status(value: str) -> str:
    status = str(value or "draft").strip()
    if status not in IP_ROLE_CONFIRMATION_STATUSES:
        raise ValueError(f"invalid role confirmation_status: {status}")
    return status


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _ip_role_needs_reconfirm(existing: dict[str, Any], prepared: dict[str, Any]) -> bool:
    if existing.get("confirmation_status") != "confirmed" or bool(existing.get("needs_reconfirm")):
        return False
    for field in IP_ROLE_RECONFIRM_FIELDS:
        if _stable_json(existing.get(field)) != _stable_json(prepared.get(field)):
            return True
    return False


def build_ip_role_persona_packet(role: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_ip": role.get("name") or "",
        "role_id": role.get("id"),
        "profile_version": role.get("profile_version") or 1,
        "positioning": role.get("positioning") or "",
        "role_baseline": role.get("role_baseline") or "",
        "life_stage": role.get("life_stage") or "",
        "core_temperament": role.get("core_temperament") or "",
        "speaking_posture": role.get("speaking_posture") or "",
        "target_audience": role.get("target_audience") or {},
        "fit_themes": role.get("fit_themes") or [],
        "avoid_themes": role.get("avoid_themes") or [],
        "target_directions": role.get("target_directions") or [],
        "search_keywords": role.get("search_keywords") or [],
        "avoid_directions": role.get("avoid_directions") or [],
        "preferred_content": role.get("preferred_content") or [],
        "forbidden_content": role.get("forbidden_content") or [],
        "forbidden_expressions": role.get("forbidden_expressions") or [],
        "style_anchors": role.get("style_anchors") or {},
        "expression_constraints": role.get("expression_constraints") or {},
        "typical_topics": role.get("typical_topics") or [],
        "theme_map": role.get("theme_map") or {},
    }


def _row_json(row: sqlite3.Row, key: str, default: Any) -> Any:
    return loads(row[key], default)


def _migrate_ip_role_v2(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "ip_roles"):
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(ip_roles)").fetchall()
        }
        for column, definition in IP_ROLE_V2_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE ip_roles ADD COLUMN {column} {definition}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ip_role_versions (
            id TEXT PRIMARY KEY,
            role_id TEXT NOT NULL,
            profile_version INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL DEFAULT '{}',
            change_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(role_id) REFERENCES ip_roles(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ip_role_versions_role_id ON ip_role_versions(role_id)")


def _migrate_schema_v2(conn: sqlite3.Connection) -> None:
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
def _migrate_creation_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS creation_tasks (
            id TEXT PRIMARY KEY,
            role_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            goal TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL,
            target_count INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'draft',
            provider TEXT NOT NULL DEFAULT 'codex-agent',
            model TEXT NOT NULL DEFAULT 'gpt-5.5',
            allow_reuse_material INTEGER NOT NULL DEFAULT 0,
            context_json TEXT NOT NULL DEFAULT '{}',
            content_package_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(role_id) REFERENCES ip_roles(id),
            FOREIGN KEY(content_package_id) REFERENCES content_packages(id)
        );
        CREATE TABLE IF NOT EXISTS creation_stage_runs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            stage_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'needs_confirmation',
            provider TEXT NOT NULL DEFAULT 'codex-agent',
            model TEXT NOT NULL DEFAULT 'gpt-5.5',
            input_json TEXT NOT NULL DEFAULT '{}',
            output_json TEXT NOT NULL DEFAULT '{}',
            output_markdown TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confirmed_at TEXT,
            FOREIGN KEY(task_id) REFERENCES creation_tasks(id)
        );
        CREATE TABLE IF NOT EXISTS creation_material_selections (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            material_id TEXT NOT NULL,
            role_id TEXT NOT NULL,
            selection_status TEXT NOT NULL DEFAULT 'selected',
            score REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(task_id, material_id),
            FOREIGN KEY(task_id) REFERENCES creation_tasks(id),
            FOREIGN KEY(material_id) REFERENCES collected_materials(id),
            FOREIGN KEY(role_id) REFERENCES ip_roles(id)
        );
        CREATE TABLE IF NOT EXISTS creation_drafts (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            stage_run_id TEXT,
            draft_type TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES creation_tasks(id),
            FOREIGN KEY(stage_run_id) REFERENCES creation_stage_runs(id)
        );
        CREATE TABLE IF NOT EXISTS creation_delivery_packages (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            content_package_id TEXT,
            platform TEXT NOT NULL,
            package_json TEXT NOT NULL DEFAULT '{}',
            markdown_path TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES creation_tasks(id),
            FOREIGN KEY(content_package_id) REFERENCES content_packages(id)
        );
        CREATE TABLE IF NOT EXISTS creation_feedback_events (
            id TEXT PRIMARY KEY,
            content_package_id TEXT NOT NULL,
            task_id TEXT,
            role_id TEXT,
            platform TEXT NOT NULL,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            notice TEXT NOT NULL DEFAULT '',
            human_note TEXT NOT NULL DEFAULT '',
            judgment TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(content_package_id) REFERENCES content_packages(id),
            FOREIGN KEY(task_id) REFERENCES creation_tasks(id),
            FOREIGN KEY(role_id) REFERENCES ip_roles(id)
        );
        CREATE TABLE IF NOT EXISTS creation_stage_feedback_events (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            role_id TEXT NOT NULL,
            stage_key TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT '',
            human_note TEXT NOT NULL DEFAULT '',
            judgment TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'recorded',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES creation_tasks(id),
            FOREIGN KEY(role_id) REFERENCES ip_roles(id)
        );
        CREATE TABLE IF NOT EXISTS risk_term_observations (
            id TEXT PRIMARY KEY,
            role_id TEXT,
            content_package_id TEXT,
            task_id TEXT,
            term TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            position TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '待验证',
            source TEXT NOT NULL DEFAULT 'creation',
            sample_text TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(role_id) REFERENCES ip_roles(id),
            FOREIGN KEY(content_package_id) REFERENCES content_packages(id),
            FOREIGN KEY(task_id) REFERENCES creation_tasks(id)
        );
        CREATE TABLE IF NOT EXISTS creation_learning_updates (
            id TEXT PRIMARY KEY,
            role_id TEXT NOT NULL,
            source_event_ids_json TEXT NOT NULL DEFAULT '[]',
            target_file TEXT NOT NULL,
            proposed_markdown TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            applied_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(role_id) REFERENCES ip_roles(id)
        );
        CREATE INDEX IF NOT EXISTS idx_creation_tasks_role_id ON creation_tasks(role_id);
        CREATE INDEX IF NOT EXISTS idx_creation_stage_runs_task_stage ON creation_stage_runs(task_id, stage_key);
        CREATE INDEX IF NOT EXISTS idx_creation_material_selections_task_id ON creation_material_selections(task_id);
        CREATE INDEX IF NOT EXISTS idx_creation_feedback_events_role_id ON creation_feedback_events(role_id);
        CREATE INDEX IF NOT EXISTS idx_creation_stage_feedback_events_role_id ON creation_stage_feedback_events(role_id);
        CREATE INDEX IF NOT EXISTS idx_creation_stage_feedback_events_task_stage ON creation_stage_feedback_events(task_id, stage_key);
        CREATE INDEX IF NOT EXISTS idx_risk_term_observations_role_id ON risk_term_observations(role_id);
        """
    )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _has_legacy_collection_schema(conn: sqlite3.Connection) -> bool:
    return any(
        _table_exists(conn, table_name)
        for table_name in (
            "douyin_authors",
            "douyin_author_videos",
            "mxnzp_call_logs",
            "mxnzp_call_cache",
        )
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


def _material_eligibility_values(source_package: dict[str, Any]) -> dict[str, Any]:
    value = source_package.get("material_eligibility") if isinstance(source_package.get("material_eligibility"), dict) else {}
    reasons = _as_list(value.get("reasons"))
    return {
        "material_eligibility": value,
        "eligibility_status": str(value.get("eligibility_status") or "accepted"),
        "eligibility_provider": str(value.get("eligibility_provider") or "local-rules"),
        "eligibility_version": str(value.get("eligibility_version") or "material-eligibility-v1"),
        "eligibility_reasons": reasons,
        "content_form": _optional_text(value.get("content_form")),
        "knowledge_core_score": _optional_float(value.get("knowledge_core_score")) or 0.0,
        "oral_script_fit_score": _optional_float(value.get("oral_script_fit_score")) or 0.0,
        "ip_fit_score": _optional_float(value.get("ip_fit_score")) or 0.0,
        "reject_reason": _optional_text(value.get("reject_reason")),
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


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
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
        "confirmation_status": row["confirmation_status"],
        "confirmed_at": row["confirmed_at"],
        "needs_reconfirm": bool(row["needs_reconfirm"]),
        "profile_version": row["profile_version"],
        "role_baseline": row["role_baseline"],
        "life_stage": row["life_stage"],
        "core_temperament": row["core_temperament"],
        "speaking_posture": row["speaking_posture"],
        "target_audience": _row_json(row, "target_audience_json", {}),
        "fit_themes": _row_json(row, "fit_themes_json", []),
        "avoid_themes": _row_json(row, "avoid_themes_json", []),
        "style_anchors": _row_json(row, "style_anchors_json", {}),
        "expression_constraints": _row_json(row, "expression_constraints_json", {}),
        "forbidden_expressions": _row_json(row, "forbidden_expressions_json", []),
        "typical_topics": _row_json(row, "typical_topics_json", []),
        "theme_map": _row_json(row, "theme_map_json", {}),
        "persona_packet": _row_json(row, "persona_packet_json", {}),
        "source_evidence": _row_json(row, "source_evidence_json", {}),
        "agent_suggestions": _row_json(row, "agent_suggestions_json", {}),
        "notes": row["notes"],
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


def _source_author_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    profile = _row_json(row, "raw_json", {})
    profile.update(
        {
            key: row[key]
            for key in (
                "ip_location",
                "follower_count",
                "following_count",
                "work_count",
                "total_favorited",
            )
            if row[key] is not None
        }
    )
    return {
        "id": row["id"],
        "platform": row["platform"],
        "platform_author_id": row["platform_author_id"],
        "platform_user_id": row["uid"],
        "handle": row["account_id"],
        "display_name": row["display_name"],
        "signature": row["signature"],
        "avatar_url": row["avatar_url"],
        "profile_url": row["profile_url"],
        "profile": profile,
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "created_at": row["first_seen_at"],
        "updated_at": row["last_seen_at"],
    }


def _source_work_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "platform": row["platform"],
        "platform_work_id": row["platform_work_id"],
        "author_id": row["author_id"],
        "canonical_url": row["source_url"],
        "title": row["title"],
        "caption_text": row["caption_text"],
        "hashtags": _row_json(row, "hashtags_json", []),
        "published_at": row["published_at"],
        "duration_ms": row["duration_ms"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "created_at": row["first_seen_at"],
        "updated_at": row["last_seen_at"],
    }


def _source_author_to_douyin_compat(author: dict[str, Any]) -> dict[str, Any]:
    profile = author.get("profile") or {}
    return {
        "sec_uid": author["platform_author_id"],
        "uid": author.get("platform_user_id"),
        "douyin_id": author.get("handle"),
        "nickname": author.get("display_name"),
        "signature": author.get("signature"),
        "avatar_url": author.get("avatar_url"),
        "profile_url": author.get("profile_url"),
        "ip_location": profile.get("ip_location"),
        "follower_count": _optional_int(profile.get("follower_count")),
        "following_count": _optional_int(profile.get("following_count")),
        "aweme_count": _optional_int(profile.get("aweme_count") or profile.get("work_count")),
        "total_favorited": _optional_int(profile.get("total_favorited")),
        "source_material_id": None,
        "source_work_id": None,
        "fetched_at": author.get("last_seen_at"),
        "raw": profile,
        "created_at": author.get("created_at"),
        "updated_at": author.get("updated_at"),
    }


def _source_work_to_douyin_compat(work: dict[str, Any], author_sec_uid: str) -> dict[str, Any]:
    return {
        "id": work["id"],
        "author_sec_uid": author_sec_uid,
        "work_id": work["platform_work_id"],
        "source_material_id": None,
        "source_url": work.get("canonical_url"),
        "title": work.get("title"),
        "platform_caption": work.get("caption_text"),
        "caption_text": work.get("caption_text"),
        "hashtags": work.get("hashtags") or [],
        "post_time": work.get("published_at"),
        "duration_ms": work.get("duration_ms"),
        "cover_url": None,
        "metrics": {},
        "source_package": {},
        "raw": {},
        "created_at": work.get("created_at"),
        "updated_at": work.get("updated_at"),
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


def _material_inventory_classification_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "material_id": row["material_id"],
        "role_id": row["role_id"],
        "topic_direction": row["topic_direction"],
        "content_mechanism": row["content_mechanism"],
        "knowledge_subtype": row["knowledge_subtype"],
        "material_class": row["material_class"],
        "is_primary": bool(row["is_primary"]),
        "review_status": row["review_status"],
        "reviewer": row["reviewer"],
        "decision_source": row["decision_source"],
        "classification_reasons": _row_json(row, "classification_reasons_json", []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _require_material_inventory_schema(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'material_inventory_classifications'"
    ).fetchone()
    if row is None:
        raise RuntimeError(
            "material inventory schema is not installed; run `mcn db migrate-material-inventory-v1` explicitly"
        )


def _normalize_inventory_text(value: Any, field: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > 120:
        raise ValueError(f"{field} must be 120 characters or fewer")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} contains control characters")
    return text


def _normalize_inventory_optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _normalize_inventory_text(value, field)


def _normalize_inventory_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"{field} must be a boolean")


def _inventory_choice(value: Any, allowed: set[str], field: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in allowed:
        raise ValueError(f"invalid {field}: {value}")
    return normalized


def _inventory_reasons(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("classification_reasons must be a list")
    reasons = [_normalize_inventory_text(item, "classification_reason") for item in value]
    reasons = _dedupe_strings(reasons)
    if not reasons:
        raise ValueError("classification_reasons must not be empty")
    return reasons


def _normalize_inventory_allocation(value: dict[str, int]) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("allocation must be a JSON object mapping topic directions to counts")
    normalized: dict[str, int] = {}
    for topic, count in value.items():
        normalized_topic = _normalize_inventory_text(topic, "topic_direction")
        if normalized_topic in normalized:
            raise ValueError(f"duplicate normalized allocation topic: {normalized_topic}")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"allocation for {normalized_topic} must be a non-negative integer")
        normalized[normalized_topic] = count
    return normalized


def _creation_task_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "role_id": row["role_id"],
        "topic": row["topic"],
        "goal": row["goal"],
        "platform": row["platform"],
        "target_count": row["target_count"],
        "status": row["status"],
        "provider": row["provider"],
        "model": row["model"],
        "allow_reuse_material": bool(row["allow_reuse_material"]),
        "context": _row_json(row, "context_json", {}),
        "content_package_id": row["content_package_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }


def _creation_stage_run_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "stage_key": row["stage_key"],
        "status": row["status"],
        "provider": row["provider"],
        "model": row["model"],
        "input": _row_json(row, "input_json", {}),
        "output": _row_json(row, "output_json", {}),
        "output_markdown": row["output_markdown"],
        "note": row["note"],
        "version": row["version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "confirmed_at": row["confirmed_at"],
    }


def _creation_material_selection_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "material_id": row["material_id"],
        "role_id": row["role_id"],
        "selection_status": row["selection_status"],
        "score": row["score"],
        "reason": row["reason"],
        "metadata": _row_json(row, "metadata_json", {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _creation_draft_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "stage_run_id": row["stage_run_id"],
        "draft_type": row["draft_type"],
        "title": row["title"],
        "body": row["body"],
        "status": row["status"],
        "metadata": _row_json(row, "metadata_json", {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _creation_delivery_package_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "content_package_id": row["content_package_id"],
        "platform": row["platform"],
        "package": _row_json(row, "package_json", {}),
        "markdown_path": row["markdown_path"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _creation_feedback_event_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "content_package_id": row["content_package_id"],
        "task_id": row["task_id"],
        "role_id": row["role_id"],
        "platform": row["platform"],
        "metrics": _row_json(row, "metrics_json", {}),
        "notice": row["notice"],
        "human_note": row["human_note"],
        "judgment": row["judgment"],
        "created_at": row["created_at"],
    }


def _creation_stage_feedback_event_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "role_id": row["role_id"],
        "stage_key": row["stage_key"],
        "platform": row["platform"],
        "human_note": row["human_note"],
        "judgment": row["judgment"],
        "status": row["status"],
        "metadata": _row_json(row, "metadata_json", {}),
        "created_at": row["created_at"],
    }


def _risk_term_observation_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "role_id": row["role_id"],
        "content_package_id": row["content_package_id"],
        "task_id": row["task_id"],
        "term": row["term"],
        "risk_level": row["risk_level"],
        "position": row["position"],
        "status": row["status"],
        "source": row["source"],
        "sample_text": row["sample_text"],
        "metadata": _row_json(row, "metadata_json", {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _creation_learning_update_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "role_id": row["role_id"],
        "source_event_ids": _row_json(row, "source_event_ids_json", []),
        "target_file": row["target_file"],
        "proposed_markdown": row["proposed_markdown"],
        "status": row["status"],
        "applied_at": row["applied_at"],
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


def _source_package_platform_work_id(
    source_package: dict[str, Any],
    *,
    source_url: str,
    platform: str,
) -> str | None:
    for key in ("work_id", "aweme_id", "platform_work_id", "id"):
        value = str(source_package.get(key) or "").strip()
        if value:
            return value
    if source_url:
        video_match = re.search(r"/video/([^/?#]+)", source_url)
        if video_match:
            return video_match.group(1)
        modal_match = re.search(r"(?:[?&])modal_id=([^&#]+)", source_url)
        if modal_match:
            return modal_match.group(1)
        if platform != "douyin":
            return source_url
    return None


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
