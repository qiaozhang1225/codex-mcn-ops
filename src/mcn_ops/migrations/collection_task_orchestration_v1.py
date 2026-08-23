from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..collection.task_contracts import (
    ACQUISITION_ACTION_TYPES,
    ChannelsSessionStatus,
    CollectionActionStatus,
    CollectionActionType,
    CollectionFrontierStatus,
    CollectionFrontierType,
    MaterialReviewOutcome,
)


COLLECTION_TASK_ORCHESTRATION_V1 = "collection_task_orchestration_v1"

REQUIRED_TABLES = {
    "schema_migrations",
    "collection_tasks",
    "collection_runs",
    "collection_candidates",
    "collected_materials",
    "material_role_matches",
    "material_inventory_classifications",
    "ip_roles",
    "source_works",
}


def _sql_choices(values: Any) -> str:
    return ", ".join(f"'{str(value)}'" for value in values)


ACTION_TYPES_SQL = _sql_choices(item.value for item in CollectionActionType)
ACTION_STATUSES_SQL = _sql_choices(item.value for item in CollectionActionStatus)
ACQUISITION_TYPES_SQL = _sql_choices(item.value for item in ACQUISITION_ACTION_TYPES)
FRONTIER_TYPES_SQL = _sql_choices(item.value for item in CollectionFrontierType)
FRONTIER_STATUSES_SQL = _sql_choices(item.value for item in CollectionFrontierStatus)
REVIEW_OUTCOMES_SQL = _sql_choices(item.value for item in MaterialReviewOutcome)
SESSION_STATUSES_SQL = _sql_choices(item.value for item in ChannelsSessionStatus)


CREATE_TABLES_SQL = f"""
CREATE TABLE IF NOT EXISTS collection_task_actions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    input_json TEXT NOT NULL DEFAULT '{{}}',
    result_json TEXT NOT NULL DEFAULT '{{}}',
    error_json TEXT NOT NULL DEFAULT '{{}}',
    lease_owner TEXT,
    lease_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(task_id, idempotency_key),
    CHECK(action_type IN ({ACTION_TYPES_SQL})),
    CHECK(status IN ({ACTION_STATUSES_SQL})),
    CHECK(length(trim(idempotency_key)) > 0),
    CHECK(length(input_hash) = 64),
    CHECK(attempt_count >= 0),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id)
);

CREATE TABLE IF NOT EXISTS collection_task_events (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    action_id TEXT,
    event_seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    payload_json TEXT NOT NULL DEFAULT '{{}}',
    created_at TEXT NOT NULL,
    UNIQUE(task_id, event_seq),
    CHECK(event_seq >= 1),
    CHECK(length(trim(event_type)) > 0),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(action_id) REFERENCES collection_task_actions(id)
);

CREATE TABLE IF NOT EXISTS collection_task_frontiers (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    frontier_type TEXT NOT NULL,
    frontier_key TEXT NOT NULL,
    status TEXT NOT NULL,
    cursor_json TEXT NOT NULL DEFAULT '{{}}',
    page_count INTEGER NOT NULL DEFAULT 0,
    result_count INTEGER NOT NULL DEFAULT 0,
    traversal_complete INTEGER NOT NULL DEFAULT 0,
    last_action_id TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(task_id, frontier_type, frontier_key),
    CHECK(frontier_type IN ({FRONTIER_TYPES_SQL})),
    CHECK(status IN ({FRONTIER_STATUSES_SQL})),
    CHECK(length(trim(frontier_key)) > 0),
    CHECK(page_count >= 0),
    CHECK(result_count >= 0),
    CHECK(traversal_complete IN (0, 1)),
    CHECK(version >= 0),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(last_action_id) REFERENCES collection_task_actions(id)
);

CREATE TABLE IF NOT EXISTS collection_material_reviews (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    source_work_id TEXT NOT NULL,
    review_revision INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    role_decision TEXT NOT NULL,
    fit_score REAL,
    topic_direction TEXT NOT NULL,
    content_mechanism TEXT NOT NULL,
    material_class TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    inventory_review_status TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{{}}',
    reviewer TEXT NOT NULL,
    role_profile_version INTEGER NOT NULL,
    transcript_sha256 TEXT NOT NULL,
    automatic_match_snapshot_json TEXT NOT NULL DEFAULT '{{}}',
    supersedes_review_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(task_id, material_id, role_id, review_revision),
    UNIQUE(action_id),
    CHECK(review_revision >= 1),
    CHECK(outcome IN ({REVIEW_OUTCOMES_SQL})),
    CHECK(role_decision IN ('accepted', 'rejected')),
    CHECK(fit_score IS NULL OR (fit_score >= 0 AND fit_score <= 1)),
    CHECK(material_class IN ('formal_rewrite_base', 'topic_clue')),
    CHECK(is_primary IN (0, 1)),
    CHECK(inventory_review_status IN ('reviewed', 'rejected')),
    CHECK(length(transcript_sha256) = 64),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(action_id) REFERENCES collection_task_actions(id),
    FOREIGN KEY(material_id) REFERENCES collected_materials(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(source_work_id) REFERENCES source_works(id),
    FOREIGN KEY(supersedes_review_id) REFERENCES collection_material_reviews(id)
);

CREATE TABLE IF NOT EXISTS channels_acquisition_sessions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    worker_key TEXT NOT NULL,
    windows_host TEXT NOT NULL,
    status TEXT NOT NULL,
    certificate_thumbprint TEXT NOT NULL,
    worker_executable TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    last_heartbeat_at TEXT,
    cleanup_verified_at TEXT,
    state_version INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{{}}',
    error_json TEXT NOT NULL DEFAULT '{{}}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(status IN ({SESSION_STATUSES_SQL})),
    CHECK(length(trim(worker_key)) > 0),
    CHECK(length(trim(certificate_thumbprint)) > 0),
    CHECK(length(trim(worker_executable)) > 0),
    CHECK(state_version >= 0),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id)
);

CREATE TABLE IF NOT EXISTS channels_acquisition_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    event_seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    payload_json TEXT NOT NULL DEFAULT '{{}}',
    created_at TEXT NOT NULL,
    UNIQUE(session_id, event_seq),
    CHECK(event_seq >= 1),
    CHECK(length(trim(event_type)) > 0),
    FOREIGN KEY(session_id) REFERENCES channels_acquisition_sessions(id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id)
);
"""

INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_collection_runs_action_id ON collection_runs(action_id)",
    "CREATE INDEX IF NOT EXISTS idx_collection_task_actions_task_status "
    "ON collection_task_actions(task_id, status, created_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_collection_task_active_acquisition_action "
    "ON collection_task_actions(task_id) "
    f"WHERE action_type IN ({ACQUISITION_TYPES_SQL}) AND status IN ('claimed', 'running')",
    "CREATE INDEX IF NOT EXISTS idx_collection_task_events_task_seq "
    "ON collection_task_events(task_id, event_seq)",
    "CREATE INDEX IF NOT EXISTS idx_collection_task_frontiers_task_status "
    "ON collection_task_frontiers(task_id, status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_collection_material_reviews_task_role "
    "ON collection_material_reviews(task_id, role_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_collection_material_reviews_source_role "
    "ON collection_material_reviews(source_work_id, role_id, created_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_channels_acquisition_open_worker "
    "ON channels_acquisition_sessions(worker_key) "
    "WHERE status NOT IN ('cleaned', 'expired')",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_channels_acquisition_open_task "
    "ON channels_acquisition_sessions(task_id) "
    "WHERE status NOT IN ('cleaned', 'expired')",
    "CREATE INDEX IF NOT EXISTS idx_channels_acquisition_events_session_seq "
    "ON channels_acquisition_events(session_id, event_seq)",
)

TRIGGER_SQL = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_collection_task_events_no_update
    BEFORE UPDATE ON collection_task_events
    BEGIN SELECT RAISE(ABORT, 'collection task events are append-only'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_collection_task_events_no_delete
    BEFORE DELETE ON collection_task_events
    BEGIN SELECT RAISE(ABORT, 'collection task events are append-only'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_collection_material_reviews_no_update
    BEFORE UPDATE ON collection_material_reviews
    BEGIN SELECT RAISE(ABORT, 'collection material reviews are immutable'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_collection_material_reviews_no_delete
    BEFORE DELETE ON collection_material_reviews
    BEGIN SELECT RAISE(ABORT, 'collection material reviews are immutable'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_channels_acquisition_events_no_update
    BEFORE UPDATE ON channels_acquisition_events
    BEGIN SELECT RAISE(ABORT, 'channels acquisition events are append-only'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_channels_acquisition_events_no_delete
    BEFORE DELETE ON channels_acquisition_events
    BEGIN SELECT RAISE(ABORT, 'channels acquisition events are append-only'); END
    """,
)

EXPECTED_COLUMNS = {
    "collection_task_actions": {
        "id", "task_id", "action_type", "status", "idempotency_key", "input_hash",
        "reason", "input_json", "result_json", "error_json", "lease_owner",
        "lease_expires_at", "attempt_count", "created_at", "updated_at", "started_at",
        "completed_at",
    },
    "collection_task_events": {
        "id", "task_id", "action_id", "event_seq", "event_type", "from_status",
        "to_status", "payload_json", "created_at",
    },
    "collection_task_frontiers": {
        "id", "task_id", "frontier_type", "frontier_key", "status", "cursor_json",
        "page_count", "result_count", "traversal_complete", "last_action_id", "version",
        "created_at", "updated_at",
    },
    "collection_material_reviews": {
        "id", "task_id", "action_id", "material_id", "role_id", "source_work_id",
        "review_revision", "outcome", "role_decision", "fit_score", "topic_direction",
        "content_mechanism", "material_class", "is_primary", "inventory_review_status",
        "evidence_json", "reviewer", "role_profile_version", "transcript_sha256",
        "automatic_match_snapshot_json", "supersedes_review_id", "created_at",
    },
    "channels_acquisition_sessions": {
        "id", "task_id", "worker_key", "windows_host", "status", "certificate_thumbprint",
        "worker_executable", "lease_expires_at", "last_heartbeat_at", "cleanup_verified_at",
        "state_version", "metadata_json", "error_json", "created_at", "updated_at",
    },
    "channels_acquisition_events": {
        "id", "session_id", "task_id", "event_seq", "event_type", "from_status",
        "to_status", "payload_json", "created_at",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    safe_table = table.replace("'", "''")
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info('{safe_table}')")}


def _add_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> bool:
    if column in _columns(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    return True


def _validate_schema(conn: sqlite3.Connection) -> None:
    for table, expected in EXPECTED_COLUMNS.items():
        missing = sorted(expected - _columns(conn, table))
        if missing:
            raise RuntimeError(f"{table} is missing required columns: {', '.join(missing)}")
    for table, columns in {
        "collection_tasks": {"state_version", "updated_at"},
        "collection_runs": {"action_id"},
        "material_role_matches": {"decision_source", "review_id", "updated_at"},
    }.items():
        missing = sorted(columns - _columns(conn, table))
        if missing:
            raise RuntimeError(f"{table} is missing required orchestration columns: {', '.join(missing)}")


def ensure_collection_task_orchestration_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    missing_tables = sorted(REQUIRED_TABLES - _tables(conn))
    if missing_tables:
        raise RuntimeError(
            "collection task orchestration migration requires tables: " + ", ".join(missing_tables)
        )

    already_applied = COLLECTION_TASK_ORCHESTRATION_V1 in {
        str(row[0]) for row in conn.execute("SELECT version FROM schema_migrations")
    }
    added_columns: list[str] = []
    if _add_column(conn, "collection_tasks", "state_version", "INTEGER NOT NULL DEFAULT 0"):
        added_columns.append("collection_tasks.state_version")
    if _add_column(conn, "collection_tasks", "updated_at", "TEXT"):
        added_columns.append("collection_tasks.updated_at")
    if _add_column(
        conn,
        "collection_runs",
        "action_id",
        "TEXT REFERENCES collection_task_actions(id)",
    ):
        added_columns.append("collection_runs.action_id")

    conn.executescript(CREATE_TABLES_SQL)

    if _add_column(
        conn,
        "material_role_matches",
        "decision_source",
        "TEXT NOT NULL DEFAULT 'automatic_rules'",
    ):
        added_columns.append("material_role_matches.decision_source")
    if _add_column(
        conn,
        "material_role_matches",
        "review_id",
        "TEXT REFERENCES collection_material_reviews(id)",
    ):
        added_columns.append("material_role_matches.review_id")
    if _add_column(conn, "material_role_matches", "updated_at", "TEXT"):
        added_columns.append("material_role_matches.updated_at")

    now = _now()
    conn.execute("UPDATE collection_tasks SET updated_at = COALESCE(updated_at, started_at, ?)", (now,))
    legacy_running_count = int(
        conn.execute("SELECT COUNT(*) FROM collection_tasks WHERE status = 'running'").fetchone()[0]
    )
    if legacy_running_count:
        conn.execute(
            """
            UPDATE collection_tasks
            SET status = 'awaiting_strategy', state_version = state_version + 1, updated_at = ?
            WHERE status = 'running'
            """,
            (now,),
        )
    conn.execute("UPDATE material_role_matches SET updated_at = COALESCE(updated_at, created_at, ?)", (now,))
    for statement in INDEX_SQL:
        conn.execute(statement)
    for statement in TRIGGER_SQL:
        conn.execute(statement)
    _validate_schema(conn)

    report = {
        "migration": COLLECTION_TASK_ORCHESTRATION_V1,
        "status": "already_applied" if already_applied else "applied",
        "additive": True,
        "added_columns": added_columns,
        "tables": sorted(EXPECTED_COLUMNS),
        "legacy_status_mappings": {"running_to_awaiting_strategy": legacy_running_count},
        "applied_at": now,
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, applied_at, report_json)
        VALUES (?, ?, ?)
        """,
        (
            COLLECTION_TASK_ORCHESTRATION_V1,
            now,
            json.dumps(report, ensure_ascii=False, sort_keys=True),
        ),
    )
    integrity = conn.execute("PRAGMA integrity_check").fetchone()
    if not integrity or str(integrity[0]).lower() != "ok":
        raise RuntimeError(f"integrity check failed after collection task orchestration migration: {integrity}")
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(
            f"foreign key check failed after collection task orchestration migration: {violations}"
        )
    return report


def migrate_collection_task_orchestration_v1(database_path: Path | str) -> dict[str, Any]:
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        report = ensure_collection_task_orchestration_schema(conn)
        conn.commit()
        return {**report, "database": str(path)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
