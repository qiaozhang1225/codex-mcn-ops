from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from mcn_ops.cli import build_parser, main
from mcn_ops.migrations import MATERIAL_INVENTORY_V1, migrate_material_inventory_v1
from mcn_ops.store import Store


def _confirmed_role(store: Store, name: str) -> str:
    return store.upsert_ip_role(
        name=name,
        positioning="知识型口播",
        confirmation_status="confirmed",
        search_keywords=["认知"],
    )


def _material(
    store: Store,
    *,
    role_id: str | None,
    source_link: str,
    transcript: str = "真正能帮助人的不是一句结论，而是把原因、边界和行动路径完整讲清楚。",
) -> str:
    run_id = store.create_collection_run(
        task_id=None,
        role_id=role_id,
        topic="认知",
        target_count=1,
        like_floor=1,
        super_like_threshold=100,
        tool_provider="mock",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "role_id": role_id,
            "source_link": source_link,
            "title": "认知素材",
            "transcript_text": transcript,
            "source_platform": "mock",
            "material_eligibility": {"eligibility_status": "accepted"},
        },
        material_understanding={"topic_summary": transcript or "线索素材"},
        raw={},
    )
    if role_id is not None:
        store.insert_material_role_match(
            material_id=material_id,
            role_id=role_id,
            task_id=None,
            fit_score=0.9,
            decision="accepted",
            reasons=["测试中已确认适配"],
        )
    return material_id


def _classification(material_id: str, topic: str = "关系边界") -> dict[str, object]:
    return {
        "material_id": material_id,
        "topic_direction": topic,
        "content_mechanism": "原因解释",
        "knowledge_subtype": "认知判断",
        "material_class": "formal_rewrite_base",
        "is_primary": True,
        "review_status": "reviewed",
        "reviewer": "human-review",
        "decision_source": "manual-review",
        "classification_reasons": ["原文有完整观点和解释链"],
    }


def test_explicit_migration_is_additive_idempotent_and_preserves_v3_data(tmp_path: Path) -> None:
    database = tmp_path / "existing-v3.sqlite"
    store = Store(database)
    store.init_db()
    role_id = _confirmed_role(store, "迁移测试角色")
    material_id = _material(store, role_id=role_id, source_link="mock://migration-work")
    with store.connect() as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("ip_roles", "source_works", "collected_materials", "material_transcriptions")
        }
        conn.execute("DROP TABLE material_inventory_classifications")
        conn.execute("DELETE FROM schema_migrations WHERE version = ?", (MATERIAL_INVENTORY_V1,))

    first = migrate_material_inventory_v1(database)
    second = migrate_material_inventory_v1(database)

    assert first["status"] == "applied"
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
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?", (MATERIAL_INVENTORY_V1,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM collected_materials WHERE id = ?", (material_id,)
        ).fetchone()[0] == 1


def test_existing_database_requires_explicit_inventory_migration(tmp_path: Path) -> None:
    database = tmp_path / "existing-v3.sqlite"
    store = Store(database)
    store.init_db()
    role_id = _confirmed_role(store, "显式迁移角色")
    material_id = _material(store, role_id=role_id, source_link="mock://explicit-gate")
    with store.connect() as conn:
        conn.execute("DROP TABLE material_inventory_classifications")
        conn.execute("DELETE FROM schema_migrations WHERE version = ?", (MATERIAL_INVENTORY_V1,))

    store.init_db()
    with pytest.raises(RuntimeError, match="migrate-material-inventory-v1"):
        store.classify_material_inventory(role_id=role_id, **_classification(material_id))


def test_inventory_supports_role_specific_classification_and_database_uniqueness(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_a = _confirmed_role(store, "角色甲")
    role_b = _confirmed_role(store, "角色乙")
    material_id = _material(store, role_id=None, source_link="mock://shared-role-material")
    for role_id in (role_a, role_b):
        store.insert_material_role_match(
            material_id=material_id,
            role_id=role_id,
            task_id=None,
            fit_score=0.9,
            decision="accepted",
            reasons=["测试中已确认适配"],
        )

    item_a = store.classify_material_inventory(role_id=role_a, **_classification(material_id))
    item_b = store.classify_material_inventory(
        role_id=role_b,
        **{
            **_classification(material_id),
            "material_class": "topic_clue",
            "review_status": "pending",
            "is_primary": False,
        },
    )

    assert item_a["role_id"] == role_a
    assert item_b["role_id"] == role_b
    with store.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO material_inventory_classifications(
                id, material_id, role_id, topic_direction, content_mechanism,
                material_class, review_status, decision_source,
                classification_reasons_json, created_at, updated_at
            ) SELECT ?, material_id, role_id, topic_direction, content_mechanism,
                     material_class, review_status, decision_source,
                     classification_reasons_json, created_at, updated_at
              FROM material_inventory_classifications WHERE id = ?
            """,
            ("duplicate", item_a["id"]),
        )
    with store.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO material_inventory_classifications(
                id, material_id, role_id, topic_direction, content_mechanism,
                material_class, review_status, decision_source,
                classification_reasons_json, created_at, updated_at
            ) VALUES (
                'invalid-fk', 'missing-material', ?, '关系边界', '原因解释',
                'topic_clue', 'reviewed', 'test', '["test"]',
                '2026-08-13T00:00:00+00:00', '2026-08-13T00:00:00+00:00'
            )
            """,
            (role_a,),
        )


def test_formal_base_requires_usable_transcript_but_topic_clue_does_not(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store, "底稿资格角色")
    material_id = _material(store, role_id=role_id, source_link="mock://no-transcript", transcript="")

    with pytest.raises(ValueError, match="not eligible as a reviewed formal rewrite base"):
        store.classify_material_inventory(role_id=role_id, **_classification(material_id))

    clue = store.classify_material_inventory(
        role_id=role_id,
        **{
            **_classification(material_id),
            "material_class": "topic_clue",
            "review_status": "reviewed",
            "is_primary": False,
        },
    )
    assert clue["material_class"] == "topic_clue"


def test_reviewed_formal_base_requires_accepted_role_match(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store, "适配约束角色")
    material_id = _material(store, role_id=None, source_link="mock://role-match-required")

    with pytest.raises(ValueError, match="reviewed formal rewrite base"):
        store.classify_material_inventory(role_id=role_id, **_classification(material_id))
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=None,
        fit_score=0.2,
        decision="rejected",
        reasons=["不适配"],
    )
    with pytest.raises(ValueError, match="reviewed formal rewrite base"):
        store.classify_material_inventory(role_id=role_id, **_classification(material_id))
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=None,
        fit_score=0.9,
        decision="accepted",
        reasons=["适配"],
    )
    assert store.classify_material_inventory(role_id=role_id, **_classification(material_id))["is_primary"]


def test_pending_inventory_is_distinct_and_honors_review_and_used_flags(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store, "待审核角色")
    unclassified_a = _material(store, role_id=role_id, source_link="mock://pending-shared")
    _material(store, role_id=role_id, source_link="mock://pending-shared")
    pending_material = _material(store, role_id=role_id, source_link="mock://pending-status")
    rejected_material = _material(store, role_id=role_id, source_link="mock://rejected-status")
    reviewed_material = _material(store, role_id=role_id, source_link="mock://reviewed-status")
    used_material = _material(store, role_id=role_id, source_link="mock://used-status")
    store.classify_material_inventory(
        role_id=role_id,
        **{**_classification(pending_material), "review_status": "pending"},
    )
    store.classify_material_inventory(
        role_id=role_id,
        **{
            **_classification(rejected_material),
            "material_class": "topic_clue",
            "review_status": "rejected",
            "is_primary": False,
        },
    )
    store.classify_material_inventory(
        role_id=role_id,
        **{
            **_classification(reviewed_material),
            "material_class": "topic_clue",
            "review_status": "reviewed",
            "is_primary": False,
        },
    )
    store.promote_material_to_content_package(used_material, platform="douyin", role_id=role_id)

    default = store.list_pending_material_inventory(role_id=role_id)
    expanded = store.list_pending_material_inventory(
        role_id=role_id,
        include_pending=True,
        include_rejected=True,
        include_used=True,
    )

    assert [item["material_id"] for item in default] == [unclassified_a]
    assert len({item["source_work_id"] for item in expanded}) == len(expanded) == 4
    assert {item["material_id"] for item in expanded} == {
        unclassified_a,
        pending_material,
        rejected_material,
        used_material,
    }
    assert all(item["transcript_text"] for item in expanded)


def test_primary_topic_is_unique_and_secondary_topic_does_not_fill_two_quotas(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store, "主方向角色")
    material_id = _material(store, role_id=role_id, source_link="mock://cross-topic")
    store.classify_material_inventory(role_id=role_id, **_classification(material_id, "方向甲"))
    with pytest.raises(sqlite3.IntegrityError):
        store.classify_material_inventory(role_id=role_id, **_classification(material_id, "方向乙"))
    secondary = store.classify_material_inventory(
        role_id=role_id,
        **{**_classification(material_id, "方向乙"), "is_primary": False},
    )

    inventory = store.list_material_inventory(role_id=role_id, include_used=True)
    summary = store.summarize_material_inventory(
        role_id=role_id,
        video_allocation={"方向甲": 1, "方向乙": 1},
        formal_base_targets={"方向甲": 1, "方向乙": 1},
    )

    assert secondary["is_primary"] is False
    assert {item["topic_direction"] for item in inventory} == {"方向甲", "方向乙"}
    by_topic = {item["topic_direction"]: item for item in summary["topics"]}
    assert by_topic["方向甲"]["available_formal_rewrite_bases"] == 1
    assert by_topic["方向乙"]["available_formal_rewrite_bases"] == 0
    assert by_topic["方向乙"]["shortage"] == 1
    assert summary["cross_topic_overlap_materials"] == [
        {"material_id": material_id, "topic_directions": ["方向乙", "方向甲"]}
    ]


def test_summary_counts_distinct_works_excludes_used_and_reports_shortage(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store, "库存统计角色")
    material_a = _material(store, role_id=role_id, source_link="mock://same-source-work")
    material_b = _material(store, role_id=role_id, source_link="mock://same-source-work")
    material_c = _material(store, role_id=role_id, source_link="mock://another-source-work")
    for material_id in (material_a, material_b):
        store.classify_material_inventory(role_id=role_id, **_classification(material_id))
    store.classify_material_inventory(
        role_id=role_id,
        **{
            **_classification(material_c),
            "material_class": "topic_clue",
            "review_status": "reviewed",
            "is_primary": False,
        },
    )
    store.promote_material_to_content_package(material_a, platform="douyin", role_id=role_id)

    visible = store.list_material_inventory(role_id=role_id)
    all_items = store.list_material_inventory(role_id=role_id, include_used=True)
    summary = store.summarize_material_inventory(
        role_id=role_id,
        video_allocation={"关系边界": 1},
        formal_base_targets={"关系边界": 3},
    )
    summary_with_used = store.summarize_material_inventory(
        role_id=role_id,
        video_allocation={"关系边界": 1},
        formal_base_targets={"关系边界": 3},
        include_used=True,
    )

    assert {item["material_id"] for item in visible} == {material_b, material_c}
    assert {item["material_id"] for item in all_items} == {material_a, material_b, material_c}
    topic = summary["topics"][0]
    assert topic["total_classified_materials"] == 3
    assert topic["distinct_source_works"] == 2
    assert topic["formal_rewrite_bases"] == 2
    assert topic["topic_clues"] == 1
    assert topic["used_materials"] == 1
    assert topic["available_formal_rewrite_bases"] == 0
    assert topic["shortage"] == 3
    assert summary_with_used["topics"][0]["available_formal_rewrite_bases"] == 1


def test_batch_import_rolls_back_all_rows_on_invalid_entry(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store, "批量回滚角色")
    material_id = _material(store, role_id=role_id, source_link="mock://batch-valid")

    with pytest.raises(KeyError, match="material not found"):
        store.import_material_inventory(
            role_id=role_id,
            classifications=[_classification(material_id), _classification("missing-material", "另一个方向")],
        )

    assert store.list_material_inventory(role_id=role_id, include_used=True) == []


def test_inventory_cli_help_and_transactional_import(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    material_help = parser.parse_args(["material", "inventory", "list", "--role-id", "role-1"])
    migration_help = parser.parse_args(["db", "migrate-material-inventory-v1"])
    assert material_help.inventory_command == "list"
    assert parser.parse_args(["material", "inventory", "pending", "--role-id", "role-1"]).inventory_command == "pending"
    assert migration_help.db_command == "migrate-material-inventory-v1"

    database = tmp_path / "mcn.sqlite"
    store = Store(database)
    store.init_db()
    role_id = _confirmed_role(store, "CLI 库存角色")
    material_id = _material(store, role_id=role_id, source_link="mock://cli-import")
    payload = tmp_path / "inventory.json"
    payload.write_text(
        json.dumps({"role_id": role_id, "classifications": [_classification(material_id)]}, ensure_ascii=False),
        encoding="utf-8",
    )

    assert main(
        [
            "--db-path",
            str(database),
            "material",
            "inventory",
            "import",
            "--role-id",
            role_id,
            "--file",
            str(payload),
            "--json",
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["imported_count"] == 1


def test_allocation_file_separates_video_plan_from_formal_base_targets(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = tmp_path / "mcn.sqlite"
    store = Store(database)
    store.init_db()
    role_id = _confirmed_role(store, "配额角色")
    allocation = tmp_path / "allocation.json"
    allocation.write_text(
        json.dumps(
            {
                "role_id": role_id,
                "batch_key": "batch-test",
                "expected_video_total": 3,
                "video_allocation": {"方向甲": 1, "方向乙": 2},
                "formal_base_targets": {"方向甲": 4, "方向乙": 5},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "--db-path",
            str(database),
            "material",
            "inventory",
            "summary",
            "--role-id",
            role_id,
            "--allocation-file",
            str(allocation),
            "--json",
        ]
    ) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["planned_video_total"] == 3
    assert summary["target_formal_base_total"] == 9
    assert sum(item["shortage"] for item in summary["topics"]) == 9

    malformed = tmp_path / "malformed.json"
    malformed.write_text(
        json.dumps(
            {
                "role_id": role_id,
                "batch_key": "batch-test",
                "expected_video_total": 4,
                "video_allocation": {"方向甲": 1, "方向乙": 2},
                "formal_base_targets": {"方向甲": 4, "方向乙": 5},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "--db-path",
            str(database),
            "material",
            "inventory",
            "summary",
            "--role-id",
            role_id,
            "--allocation-file",
            str(malformed),
        ]
    ) == 1
    assert "expected_video_total" in capsys.readouterr().err


def test_active_material_workflow_has_no_stale_provider_instructions() -> None:
    root = Path(__file__).resolve().parents[1]
    active_docs = [root / "workflows" / "collect_materials.md", root / "REQUIREMENTS.md"]
    stale_terms = ["mxnzp", "api.mxnzp.com", "douyin-cookie", "video_to_text_v2"]
    for document in active_docs:
        text = document.read_text(encoding="utf-8").lower()
        assert not any(term in text for term in stale_terms), document
