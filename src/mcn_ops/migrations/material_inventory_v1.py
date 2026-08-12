from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MATERIAL_INVENTORY_V1 = "material_inventory_v1"

REQUIRED_TABLES = {
    "schema_migrations",
    "collected_materials",
    "ip_roles",
    "source_works",
    "material_creations",
}

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS material_inventory_classifications (
    id TEXT PRIMARY KEY,
    material_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    topic_direction TEXT NOT NULL,
    content_mechanism TEXT NOT NULL,
    knowledge_subtype TEXT,
    material_class TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL,
    reviewer TEXT,
    decision_source TEXT NOT NULL,
    classification_reasons_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(material_id, role_id, topic_direction),
    CHECK(length(trim(topic_direction)) BETWEEN 1 AND 120),
    CHECK(length(trim(content_mechanism)) BETWEEN 1 AND 120),
    CHECK(knowledge_subtype IS NULL OR length(trim(knowledge_subtype)) BETWEEN 1 AND 120),
    CHECK(material_class IN ('formal_rewrite_base', 'topic_clue')),
    CHECK(is_primary IN (0, 1)),
    CHECK(review_status IN ('pending', 'reviewed', 'rejected')),
    CHECK(reviewer IS NULL OR length(trim(reviewer)) BETWEEN 1 AND 120),
    CHECK(length(trim(decision_source)) BETWEEN 1 AND 120),
    FOREIGN KEY(material_id) REFERENCES collected_materials(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id)
)
"""

INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_material_inventory_role_topic "
    "ON material_inventory_classifications(role_id, topic_direction)",
    "CREATE INDEX IF NOT EXISTS idx_material_inventory_material "
    "ON material_inventory_classifications(material_id)",
    "CREATE INDEX IF NOT EXISTS idx_material_inventory_role_class_review "
    "ON material_inventory_classifications(role_id, material_class, review_status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_material_inventory_primary_topic "
    "ON material_inventory_classifications(material_id, role_id) WHERE is_primary = 1",
)

EXPECTED_COLUMNS = {
    "id",
    "material_id",
    "role_id",
    "topic_direction",
    "content_mechanism",
    "knowledge_subtype",
    "material_class",
    "is_primary",
    "review_status",
    "reviewer",
    "decision_source",
    "classification_reasons_json",
    "created_at",
    "updated_at",
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


def _validate_inventory_schema(conn: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(material_inventory_classifications)")}
    missing_columns = sorted(EXPECTED_COLUMNS - columns)
    if missing_columns:
        raise RuntimeError(
            "material inventory table is missing required columns: " + ", ".join(missing_columns)
        )

    foreign_keys = {
        (str(row[3]), str(row[2]), str(row[4]))
        for row in conn.execute("PRAGMA foreign_key_list(material_inventory_classifications)")
    }
    expected_foreign_keys = {
        ("material_id", "collected_materials", "id"),
        ("role_id", "ip_roles", "id"),
    }
    if not expected_foreign_keys.issubset(foreign_keys):
        raise RuntimeError("material inventory table does not have the required foreign keys")

    unique_keys: set[tuple[str, ...]] = set()
    for index_row in conn.execute("PRAGMA index_list(material_inventory_classifications)"):
        if not bool(index_row[2]):
            continue
        index_name = str(index_row[1]).replace("'", "''")
        unique_keys.add(
            tuple(
                str(column_row[2])
                for column_row in conn.execute(f"PRAGMA index_info('{index_name}')")
            )
        )
    if ("material_id", "role_id", "topic_direction") not in unique_keys:
        raise RuntimeError("material inventory table does not have the required uniqueness constraint")
    primary_index = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'uq_material_inventory_primary_topic'"
    ).fetchone()
    primary_sql = str(primary_index[0] or "").lower() if primary_index else ""
    if "material_id" not in primary_sql or "role_id" not in primary_sql or "where is_primary = 1" not in primary_sql:
        raise RuntimeError("material inventory table does not enforce one primary topic per material and role")


def ensure_material_inventory_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    missing = sorted(REQUIRED_TABLES - _tables(conn))
    if missing:
        raise RuntimeError(f"material inventory migration requires tables: {', '.join(missing)}")

    already_applied = "material_inventory_classifications" in _tables(conn)
    conn.execute(CREATE_TABLE_SQL)
    for statement in INDEX_SQL:
        conn.execute(statement)
    _validate_inventory_schema(conn)

    applied_at = _now()
    report = {
        "migration": MATERIAL_INVENTORY_V1,
        "status": "already_applied" if already_applied else "applied",
        "table": "material_inventory_classifications",
        "additive": True,
        "existing_rows_backfilled": 0,
        "applied_at": applied_at,
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, applied_at, report_json)
        VALUES (?, ?, ?)
        """,
        (MATERIAL_INVENTORY_V1, applied_at, json.dumps(report, ensure_ascii=False, sort_keys=True)),
    )
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"foreign key check failed after material inventory migration: {violations}")
    return report


def migrate_material_inventory_v1(database_path: Path | str) -> dict[str, Any]:
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        report = ensure_material_inventory_schema(conn)
        conn.commit()
        return {**report, "database": str(path)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
