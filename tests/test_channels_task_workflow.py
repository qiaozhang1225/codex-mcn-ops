from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcn_ops.cli import build_parser
from mcn_ops.collection.douyin.contracts import build_provider_result
from mcn_ops.collection.review import TaskReviewService
from mcn_ops.collection.tools import ToolRegistry, ToolSpec
from mcn_ops.collection.workflows import CollectionPolicy, CollectionTaskOrchestrator
from mcn_ops.migrations import migrate_collection_task_orchestration_v1
from mcn_ops.store import Store


class _UnusedSessionGuard:
    worker_id = "workstation-channels-01"
    shared_secret = "x" * 32

    def __init__(self) -> None:
        self.closed_reasons: list[str] = []

    def ensure_active(self) -> dict[str, Any]:
        return {"status": "active"}

    def close(self, *, reason: str) -> dict[str, Any]:
        self.closed_reasons.append(reason)
        return {"status": "cleaned"}


class _FailingCleanupGuard(_UnusedSessionGuard):
    def close(self, *, reason: str) -> dict[str, Any]:
        raise RuntimeError(f"cleanup failed: {reason}")


def test_durable_channels_task_commands_are_exposed_by_the_cli() -> None:
    parser = build_parser()
    assert parser.parse_args(
        ["collect", "task", "plan", "--task-id", "ctask-123", "--keyword", "亲子沟通"]
    ).task_command == "plan"
    assert parser.parse_args(
        ["collect", "task", "step", "--task-id", "ctask-123"]
    ).task_command == "step"
    assert parser.parse_args(
        [
            "collect",
            "task",
            "tune",
            "--task-id",
            "ctask-123",
            "--max-duration-seconds",
            "900",
        ]
    ).task_command == "tune"
    assert parser.parse_args(
        [
            "collect",
            "task",
            "cancel",
            "--task-id",
            "ctask-123",
            "--reason",
            "scope_changed",
        ]
    ).task_command == "cancel"
    assert parser.parse_args(
        ["collect", "task", "session-status", "--task-id", "ctask-123"]
    ).task_command == "session-status"
    assert parser.parse_args(
        ["collect", "task", "session-recover", "--task-id", "ctask-123"]
    ).task_command == "session-recover"


def _registry(search_calls: list[dict[str, Any]]) -> ToolRegistry:
    registry = ToolRegistry()
    package = {
        "source_type": "wechat_channels_remote",
        "source_platform": "wechat_channels",
        "provider": "wechat_channels_remote",
        "work_id": "durable-work-1",
        "title": "青春期孩子拒绝沟通，父母先处理焦虑",
        "platform_caption": "青春期孩子拒绝沟通，父母先处理焦虑",
        "author_name": "家庭心理老师",
        "platform_author_id": "finder-author-1",
        "duration_ms": 90_000,
        "public_metrics": {
            "digg_count": 5_000,
            "collect_count": 300,
            "comment_count": 50,
            "share_count": 200,
            "play_count": None,
        },
        "detail_ref": {"object_id": "durable-work-1", "object_nonce_id": "nonce-1"},
        "media_lease_available": True,
        "collection_notes": [],
    }

    def search(arguments: dict[str, Any]) -> dict[str, Any]:
        search_calls.append(arguments)
        return build_provider_result(
            provider="wechat_channels_remote",
            method_key="wechat_channels_search",
            normalized={"keyword": arguments["keyword"], "source_packages": [package]},
            paging={
                "has_next": True,
                "next_cursor": "page-2",
                "captured_pages": 1,
                "captured_items": 1,
                "stop_reason": "max_pages",
                "request_satisfied": True,
                "source_exhausted": False,
                "raw": {},
            },
        )

    registry.register(ToolSpec("channels_search_videos", "test", {}, search))
    registry.register(
        ToolSpec(
            "channels_fetch_video_detail",
            "test",
            {},
            lambda _arguments: build_provider_result(
                provider="wechat_channels_remote",
                method_key="wechat_channels_detail",
                normalized={"source_package": {**package, "detail_verified": True}},
                raw={},
            ),
        )
    )
    registry.register(
        ToolSpec(
            "channels_resolve_share_link",
            "test",
            {},
            lambda arguments: build_provider_result(
                provider="wechat_channels_remote",
                method_key="wechat_channels_share_url",
                normalized={
                    "work_id": arguments["work_id"],
                    "source_link": "https://weixin.qq.com/sph/DurableWork1",
                    "source_link_verified": True,
                },
                raw={},
            ),
        )
    )
    transcript = (
        "为什么青春期孩子越来越不愿意和父母沟通？因为父母一开口就急着纠正，孩子感受到的不是帮助，而是不被理解。"
        "孩子拒绝沟通时，父母最先要处理的不是孩子的态度，而是自己的焦虑。第一，暂停追问和说教，让关系先恢复安全；"
        "第二，描述你看到的事实，不给孩子贴懒惰或叛逆的标签；第三，理解行为背后的心理需要，再一起讨论双方都能执行的边界。"
        "真正有效的亲子沟通，不是压服孩子，而是在关系安全的前提下共同解决问题。"
    )
    registry.register(
        ToolSpec(
            "channels_extract_video_text",
            "test",
            {},
            lambda arguments: build_provider_result(
                provider="aliyun-qwen-asr",
                method_key="channels_extract_video_text",
                normalized={
                    "text": transcript,
                    "model": "qwen3-asr-flash",
                    "language": "zh",
                    "source_package": {
                        **arguments["source_package"],
                        "transcript_text": transcript,
                        "audio_sha256": "audio-hash",
                    },
                },
                raw={},
            ),
        )
    )
    return registry


def test_durable_channels_task_executes_one_search_then_materializes_without_research(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    migrate_collection_task_orchestration_v1(store.db_path)
    role_id = store.upsert_ip_role(
        name="宋立心理",
        positioning="面向青春期孩子家长的家庭心理老师",
        search_keywords=["青春期孩子", "亲子沟通"],
        confirmation_status="confirmed",
    )
    search_calls: list[dict[str, Any]] = []
    registry = _registry(search_calls)
    session = _UnusedSessionGuard()
    orchestrator = CollectionTaskOrchestrator(
        store,
        channels_registry_factory=lambda **_kwargs: registry,
        channels_session_controller_factory=lambda _store, _task_id: session,
    )

    report = orchestrator.run_keyword_task(
        topic="宋立心理青春期家庭心理",
        target_count=1,
        policy=CollectionPolicy(
            viral_like_floor=2_000,
            max_search_pages=1,
            page_size=20,
            max_materials_per_iteration=1,
        ),
        tool_provider="wechat_channels_remote",
        transcription_provider="aliyun",
        keywords=["青春期孩子"],
        role_id=role_id,
    )

    task_id = report["task"]["id"]
    assert report["task"]["status"] == "awaiting_review", report
    assert len(search_calls) == 1
    assert report["successful_transcriptions"] == 1
    assert report["inventory_handoff"]["pending_review_count"] == 1
    actions = store.list_collection_task_actions(task_id=task_id)
    assert actions[0]["status"] == "succeeded"
    frontier = store.list_collection_task_frontiers(task_id=task_id)[0]
    assert frontier["status"] == "open"
    assert frontier["cursor"] == {"next_cursor": "page-2"}
    linked_runs = [run for run in report["runs"] if run.get("action_id") == actions[0]["id"]]
    assert len(linked_runs) == 1

    material = report["saved_materials"][0]
    reviewed = TaskReviewService(store).review(
        task_id=task_id,
        material_id=material["id"],
        role_id=role_id,
        outcome="formal_rewrite_base",
        topic_direction="亲子沟通",
        content_mechanism="父母焦虑影响沟通顺序",
        evidence={"reasons": ["完整转写覆盖目标家长、冲突和心理机制"]},
        reviewer="codex-semantic-review",
        idempotency_key="review:durable-work-1:v1",
        fit_score=0.9,
    )
    assert reviewed["task"]["status"] == "completing"
    assert reviewed["progress"]["qualified_formal_base_count"] == 1

    completed = orchestrator.resume_task(task_id)
    assert completed["task"]["status"] == "completed"
    assert session.closed_reasons == ["task_completed"]


def test_cancelling_a_durable_task_cancels_planned_actions_before_cleanup(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    migrate_collection_task_orchestration_v1(store.db_path)
    task_id = store.create_collection_task(
        command="collect Channels scripts",
        target_scope="keyword",
        target_count_per_role=20,
        topic="青春期孩子",
        parsed={
            "entrypoint": "keyword",
            "topic": "青春期孩子",
            "target_count": 20,
            "tool_provider": "wechat_channels_remote",
            "policy": {"viral_like_floor": 2_000},
        },
        status="ready_for_search",
    )
    session = _UnusedSessionGuard()
    orchestrator = CollectionTaskOrchestrator(
        store,
        channels_registry_factory=lambda **_kwargs: _registry([]),
        channels_session_controller_factory=lambda _store, _task_id: session,
    )
    action = orchestrator.plan_channels_keyword_action(
        task_id=task_id,
        keyword="青春期孩子",
    )

    report = orchestrator.cancel_channels_task(task_id, reason="operator changed scope")

    assert report["task"]["status"] == "cancelled"
    assert store.get_collection_task_action(action["id"])["status"] == "cancelled"
    assert session.closed_reasons == ["task_cancelled"]


def test_open_channels_task_policy_can_be_tuned_without_changing_state(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    migrate_collection_task_orchestration_v1(store.db_path)
    task_id = store.create_collection_task(
        command="collect Channels scripts",
        target_scope="keyword",
        target_count_per_role=14,
        topic="厌学休学",
        parsed={
            "entrypoint": "keyword",
            "tool_provider": "wechat_channels_remote",
            "policy": {
                "viral_like_floor": 2_000,
                "min_duration_seconds": 30,
                "max_duration_seconds": 360,
                "max_materials_per_iteration": 8,
            },
        },
        status="ready_for_search",
    )
    orchestrator = CollectionTaskOrchestrator(store)

    result = orchestrator.tune_channels_task_policy(
        task_id=task_id,
        max_duration_seconds=900,
    )

    assert result["status"] == "ready_for_search"
    assert result["changes"] == {"max_duration_seconds": 900}
    updated = store.get_collection_task(task_id)
    assert updated is not None
    assert updated["parsed"]["policy"]["max_duration_seconds"] == 900
    assert updated["state_version"] == 1


def test_completion_stays_non_terminal_until_failed_cleanup_is_recovered(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    migrate_collection_task_orchestration_v1(store.db_path)
    task_id = store.create_collection_task(
        command="complete Channels task",
        target_scope="keyword",
        target_count_per_role=1,
        topic="亲子沟通",
        parsed={
            "entrypoint": "keyword",
            "tool_provider": "wechat_channels_remote",
            "target_count": 1,
        },
        status="completing",
    )
    orchestrator = CollectionTaskOrchestrator(
        store,
        channels_session_controller_factory=lambda _store, _task_id: _FailingCleanupGuard(),
    )

    with pytest.raises(RuntimeError, match="cleanup failed"):
        orchestrator.complete_channels_task(task_id)
    blocked = store.get_collection_task(task_id)
    assert blocked["status"] == "cleanup_required"
    assert blocked["completed_at"] is None

    recovered_session = _UnusedSessionGuard()
    orchestrator._channels_session_controller_factory = (
        lambda _store, _task_id: recovered_session
    )
    report = orchestrator.recover_channels_task_cleanup(task_id)
    assert report["task"]["status"] == "completed"
    assert recovered_session.closed_reasons == ["task_completed"]
