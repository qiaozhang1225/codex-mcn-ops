from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mcn_ops.collection.douyin.contracts import build_provider_result
from mcn_ops.collection.runner import (
    CollectionConfig,
    TopicCollectionRunner,
    dedupe_candidates,
    filter_candidates_for_relevance,
)
from mcn_ops.collection.tools import ToolRegistry, ToolSpec
from mcn_ops.collection.workflows import CollectionPolicy, CollectionTaskOrchestrator
from mcn_ops.store import Store


def test_channels_collection_persists_candidates_material_and_understanding_idempotently(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(
        name="宋立心理",
        positioning="面向青春期孩子家长的家庭心理老师",
        search_keywords=["青春期", "亲子沟通"],
        target_directions=["孩子厌学", "手机沉迷"],
        confirmation_status="confirmed",
    )
    role = store.get_ip_role(role_id)
    assert role is not None
    tools = _channels_tools()
    runner = TopicCollectionRunner(tools, store)
    config = CollectionConfig(
        topic="青春期孩子",
        target_count=1,
        like_floor=2000,
        min_duration_seconds=20,
        max_duration_seconds=300,
        tool_provider="wechat_channels_remote",
        max_search_pages=1,
        page_size=50,
        role_id=role_id,
        role_profile=role,
        search_keywords=["青春期孩子"],
    )

    first = runner.run(config)
    second = runner.run(config)

    assert first.status == "completed"
    assert first.candidate_count == 2
    assert first.understanding_success_count == 1
    assert second.existing_reused_material_ids == first.saved_material_ids
    with sqlite3.connect(store.db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM source_works WHERE platform='wechat_channels'"
        ).fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM collection_candidates").fetchone()[0] == 4
        assert connection.execute("SELECT count(*) FROM collected_materials").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM material_transcriptions").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        serialized = " ".join(
            str(row[0])
            for row in connection.execute("SELECT payload_json FROM source_observations")
        )
        assert "signed-private" not in serialized
        assert "decodeKey" not in serialized
    material = store.get_collected_material(first.saved_material_ids[0])
    assert material is not None
    assert material["source_platform"] == "wechat_channels"
    assert material["platform_author_id"] == "finder-author-1"
    assert material["transcript_text"].startswith("为什么孩子进入青春期")
    assert material["understanding_status"] == "success"
    matches = store.list_material_role_matches(material_id=material["id"])
    assert matches[0]["role_id"] == role_id
    assert matches[0]["decision"] == "accepted"


def _channels_tools() -> ToolRegistry:
    registry = ToolRegistry()
    packages = [
        _package("work-1", "nonce-1", "青春期孩子为什么不愿沟通", 2500),
        _package("work-2", "nonce-2", "青春期亲子沟通的三个误区", 20),
    ]
    registry.register(
        ToolSpec(
            name="channels_search_videos",
            description="test",
            parameters={},
            handler=lambda args: build_provider_result(
                provider="wechat_channels_remote",
                method_key="wechat_channels_search",
                normalized={"keyword": args["keyword"], "source_packages": packages},
                paging={
                    "has_next": True,
                    "captured_pages": 1,
                    "captured_items": 2,
                    "stop_reason": "max_pages",
                    "request_satisfied": True,
                    "source_exhausted": False,
                    "raw": {},
                },
            ),
        )
    )
    registry.register(
        ToolSpec(
            name="channels_fetch_video_detail",
            description="test",
            parameters={},
            handler=lambda args: build_provider_result(
                provider="wechat_channels_remote",
                method_key="wechat_channels_detail",
                normalized={"source_package": packages[0]},
                raw={},
            ),
        )
    )
    transcript = (
        "为什么孩子进入青春期以后不愿沟通？因为他开始需要边界，所以父母不要和他较劲。"
        "第一，先稳定自己的情绪；第二，给孩子表达空间；第三，在孩子开口时认真回应。"
        "真正有效的亲子沟通，不是压服孩子，而是在关系安全的前提下共同解决问题。"
    )
    registry.register(
        ToolSpec(
            name="channels_extract_video_text",
            description="test",
            parameters={},
            handler=lambda args: build_provider_result(
                provider="aliyun-qwen-asr",
                method_key="channels_extract_video_text",
                normalized={
                    "text": transcript,
                    "model": "qwen3-asr-flash",
                    "language": "zh",
                    "source_package": {
                        **{
                            key: value
                            for key, value in args["source_package"].items()
                            if key != "detail_ref"
                        },
                        "transcript_text": transcript,
                        "audio_sha256": "audio-hash",
                    },
                },
                raw={},
                usage={
                    "audio_seconds": 90,
                    "estimated_cost_cny": 0.0198,
                    "model": "qwen3-asr-flash",
                },
            ),
        )
    )
    return registry


def _package(work_id: str, nonce: str, title: str, likes: int) -> dict[str, object]:
    return {
        "source_type": "wechat_channels_remote",
        "source_platform": "wechat_channels",
        "provider": "wechat_channels_remote",
        "work_id": work_id,
        "title": title,
        "platform_caption": title,
        "author_name": "心理老师",
        "platform_author_id": "finder-author-1",
        "duration_ms": 90000,
        "public_metrics": {
            "digg_count": likes,
            "collect_count": 300,
            "comment_count": 20,
            "share_count": 500,
            "play_count": None,
        },
        "detail_ref": {
            "object_id": work_id,
            "object_nonce_id": nonce,
            "encrypted_object_id": "",
        },
        "media_lease_available": True,
        "collection_notes": [],
    }


def test_channels_duplicate_candidates_retain_all_search_keywords() -> None:
    first = {
        "source_package": {
            **_package("work-1", "nonce-1", "青春期沟通", 100),
            "search_keyword": "青春期孩子",
            "collection_notes": [{"type": "search_keyword", "value": "青春期孩子"}],
        }
    }
    second = {
        "source_package": {
            **_package("work-1", "nonce-1", "青春期沟通", 100),
            "search_keyword": "亲子沟通",
            "collection_notes": [{"type": "search_keyword", "value": "亲子沟通"}],
        }
    }

    result = dedupe_candidates([first, second])

    assert len(result) == 1
    assert result[0]["source_package"]["matched_search_keywords"] == [
        "青春期孩子",
        "亲子沟通",
    ]


def test_channels_relevance_uses_explicit_task_search_keywords() -> None:
    candidate = {
        "source_package": _package(
            "work-search-keyword",
            "nonce-search-keyword",
            "孩子厌学后，家长先调整沟通顺序",
            500,
        )
    }

    accepted, skipped = filter_candidates_for_relevance(
        [candidate],
        role_profile=None,
        topic="宋立心理青春期家庭心理",
        search_keywords=["孩子厌学", "亲子沟通"],
    )

    assert accepted == [candidate]
    assert skipped == []


def test_channels_detail_recheck_retains_task_search_keyword_match(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    result = TopicCollectionRunner(_channels_tools(), store).run(
        CollectionConfig(
            topic="宋立心理",
            target_count=1,
            like_floor=2000,
            min_duration_seconds=20,
            max_duration_seconds=300,
            tool_provider="wechat_channels_remote",
            max_search_pages=1,
            page_size=50,
            search_keywords=["青春期孩子"],
        )
    )

    assert result.status == "completed"
    assert len(result.saved_material_ids) == 1


def test_channels_formal_collection_rejects_subviral_floor(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()

    with pytest.raises(ValueError, match="like_floor >= 2000"):
        TopicCollectionRunner(_channels_tools(), store).run(
            CollectionConfig(
                topic="青春期孩子",
                target_count=1,
                like_floor=1999,
                tool_provider="wechat_channels_remote",
                search_keywords=["青春期孩子"],
            )
        )
    with sqlite3.connect(store.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0] == 0


def test_channels_role_task_pauses_for_semantic_review_and_completes_only_after_formal_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(
        name="宋立心理",
        positioning="面向青春期孩子家长的家庭心理老师",
        search_keywords=["青春期孩子", "亲子沟通"],
        target_directions=["孩子厌学", "手机沉迷"],
        confirmation_status="confirmed",
    )
    registry = _channels_tools()
    monkeypatch.setattr(
        "mcn_ops.collection.workflows.build_channels_collection_registry",
        lambda **_kwargs: registry,
    )
    orchestrator = CollectionTaskOrchestrator(store)

    first = orchestrator.run_keyword_task(
        topic="青春期孩子",
        target_count=1,
        policy=CollectionPolicy(
            viral_like_floor=2000,
            max_search_pages=1,
            page_size=50,
            max_materials_per_iteration=5,
        ),
        tool_provider="wechat_channels_remote",
        transcription_provider="aliyun",
        keywords=["青春期孩子", "亲子沟通"],
        role_id=role_id,
    )

    task_id = first["task"]["id"]
    assert first["task"]["status"] == "awaiting_review"
    assert first["task"]["completed_at"] is None
    assert first["saved_count"] == 1
    assert first["qualified_formal_base_count"] == 0
    assert first["remaining_count"] == 1
    assert first["inventory_handoff"]["pending_review_count"] == 1
    assert len(first["runs"]) == 1

    paused = orchestrator.resume_task(task_id)
    assert paused["task"]["status"] == "awaiting_review"
    assert len(paused["runs"]) == 1

    material_id = first["saved_materials"][0]["id"]
    store.classify_material_inventory(
        material_id=material_id,
        role_id=role_id,
        topic_direction="亲子沟通",
        content_mechanism="心理需要解释",
        material_class="formal_rewrite_base",
        is_primary=True,
        review_status="reviewed",
        reviewer="codex-semantic-review",
        decision_source="full-transcript-review",
        classification_reasons=["完整转写与宋立心理目标家长和亲子沟通方向一致"],
    )

    completed = orchestrator.resume_task(task_id)
    assert completed["task"]["status"] == "completed"
    assert completed["task"]["completed_at"] is not None
    assert completed["goal_satisfied"] is True
    assert completed["qualified_formal_base_count"] == 1
    assert completed["remaining_count"] == 0
    assert len(completed["runs"]) == 1


def test_channels_task_semantic_review_queue_includes_automatic_role_rejections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(
        name="宋立心理",
        positioning="面向青春期孩子家长的家庭心理老师",
        search_keywords=["青春期孩子"],
        target_directions=["亲子沟通"],
        confirmation_status="confirmed",
    )
    registry = _channels_tools()
    monkeypatch.setattr(
        "mcn_ops.collection.workflows.build_channels_collection_registry",
        lambda **_kwargs: registry,
    )
    monkeypatch.setattr(
        "mcn_ops.collection.runner.evaluate_role_match",
        lambda _material, _role: {
            "fit_score": 0.45,
            "decision": "rejected",
            "reasons": ["rules-based matcher did not find enough exact terms"],
            "matched_keywords": [],
            "avoidance_notes": [],
        },
    )

    report = CollectionTaskOrchestrator(store).run_keyword_task(
        topic="青春期孩子",
        target_count=20,
        policy=CollectionPolicy(viral_like_floor=2000, max_search_pages=1),
        tool_provider="wechat_channels_remote",
        transcription_provider="aliyun",
        role_id=role_id,
    )

    review_role = report["inventory_handoff"]["roles"][0]
    assert report["task"]["status"] == "awaiting_review"
    assert report["qualified_formal_base_count"] == 0
    assert report["remaining_count"] == 20
    assert review_role["pending_count"] == 1
    assert review_role["materials"][0]["automatic_role_decision"] == "rejected"

    material_id = report["saved_materials"][0]["id"]
    store.classify_material_inventory(
        material_id=material_id,
        role_id=role_id,
        topic_direction="不适配",
        content_mechanism="完整转写审核后排除",
        material_class="topic_clue",
        is_primary=False,
        review_status="rejected",
        reviewer="codex-semantic-review",
        decision_source="full-transcript-review",
        classification_reasons=["与目标账号方向不一致"],
    )

    reviewed_report = CollectionTaskOrchestrator(store).build_task_report(report["task"]["id"])
    assert reviewed_report["inventory_handoff"]["pending_review_count"] == 0
