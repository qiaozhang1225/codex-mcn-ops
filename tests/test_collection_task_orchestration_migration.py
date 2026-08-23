from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mcn_ops.migrations import (
    COLLECTION_TASK_ORCHESTRATION_V1,
    migrate_collection_task_orchestration_v1,
)
from mcn_ops.store import Store


def test_orchestration_migration_is_explicit_additive_and_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "mcn.sqlite"
    store = Store(database)
    store.init_db()
    task_id = store.create_collection_task(
        command="collect task keyword",
        target_scope="keyword",
        target_count_per_role=20,
        topic="青春期孩子",
        parsed={"role_id": "future-role"},
    )

    with pytest.raises(RuntimeError, match="orchestration schema is not installed"):
        store.create_collection_task_action(
            task_id=task_id,
            action_type="search_keyword",
            idempotency_key="before-migration",
            input_payload={"keyword": "青春期孩子"},
        )

    with store.connect() as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("collection_tasks", "collection_runs", "source_works", "collected_materials")
        }

    first = migrate_collection_task_orchestration_v1(database)
    second = migrate_collection_task_orchestration_v1(database)

    assert first["status"] == "applied"
    assert first["additive"] is True
    assert first["legacy_status_mappings"]["running_to_awaiting_strategy"] == 1
    assert second["status"] == "already_applied"
    with store.connect() as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        assert after == before
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (COLLECTION_TASK_ORCHESTRATION_V1,),
        ).fetchone()[0] == 1
        assert {
            "state_version",
            "updated_at",
        }.issubset({row["name"] for row in conn.execute("PRAGMA table_info(collection_tasks)")})
        assert {
            "decision_source",
            "review_id",
            "updated_at",
        }.issubset({row["name"] for row in conn.execute("PRAGMA table_info(material_role_matches)")})
        migrated_task = conn.execute(
            "SELECT status, state_version FROM collection_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        assert migrated_task["status"] == "awaiting_strategy"
        assert migrated_task["state_version"] == 1


def test_orchestration_event_and_review_tables_are_append_only(tmp_path: Path) -> None:
    database = tmp_path / "mcn.sqlite"
    store = Store(database)
    store.init_db()
    migrate_collection_task_orchestration_v1(database)
    task_id = store.create_collection_task(
        command="collect task keyword",
        target_scope="keyword",
        target_count_per_role=1,
        topic="亲子沟通",
    )
    event = store.append_collection_task_event(task_id=task_id, event_type="test_event")

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store.connect() as conn:
            conn.execute(
                "UPDATE collection_task_events SET event_type = 'changed' WHERE id = ?",
                (event["id"],),
            )
