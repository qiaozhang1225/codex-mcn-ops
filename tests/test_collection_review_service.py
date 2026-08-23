from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcn_ops.cli import main
from mcn_ops.collection.review import TaskReviewService
from mcn_ops.migrations import migrate_collection_task_orchestration_v1
from mcn_ops.store import Store


def _store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    migrate_collection_task_orchestration_v1(store.db_path)
    return store


def _role(store: Store) -> str:
    return store.upsert_ip_role(
        name="宋立心理",
        positioning="面向青春期孩子家长的家庭心理老师",
        target_directions=["亲子沟通", "孩子厌学"],
        search_keywords=["青春期孩子", "亲子沟通"],
        confirmation_status="confirmed",
    )


def _task(store: Store, *, role_id: str, target_count: int) -> str:
    task_id = store.create_collection_task(
        command=f"collect 20 formal rewrite bases for {role_id}",
        target_scope="keyword",
        target_count_per_role=target_count,
        topic="青春期家庭心理",
        parsed={
            "role_id": role_id,
            "policy": {"viral_like_floor": 2000},
        },
        status="awaiting_review",
    )
    store.upsert_collection_task_role(
        task_id=task_id,
        role_id=role_id,
        target_count=target_count,
        status="awaiting_review",
    )
    return task_id


def _material(
    store: Store,
    *,
    task_id: str,
    role_id: str,
    work_id: str,
    transcript: str | None = None,
) -> str:
    transcript = transcript or "孩子拒绝沟通时，父母先处理自己的焦虑，再理解孩子行为背后的心理需要。"
    run_id = store.create_collection_run(
        task_id=task_id,
        role_id=role_id,
        topic="亲子沟通",
        target_count=1,
        like_floor=2000,
        super_like_threshold=100000,
        tool_provider="wechat_channels_remote",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "task_id": task_id,
            "role_id": role_id,
            "source_platform": "wechat_channels",
            "work_id": work_id,
            "source_link": f"channels://{work_id}",
            "title": "青春期亲子沟通",
            "transcript_text": transcript,
            "public_metrics": {"likes": 5000},
            "material_eligibility": {"eligibility_status": "accepted"},
        },
        material_understanding={"topic_summary": transcript},
        raw={},
    )
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=task_id,
        fit_score=0.45,
        decision="rejected",
        reasons=["automatic exact-term matcher rejected"],
    )
    return material_id


def _review(
    service: TaskReviewService,
    *,
    task_id: str,
    material_id: str,
    role_id: str,
    outcome: str,
    key: str,
) -> dict[str, object]:
    return service.review(
        task_id=task_id,
        material_id=material_id,
        role_id=role_id,
        outcome=outcome,
        topic_direction="亲子沟通",
        content_mechanism="父母焦虑影响亲子沟通",
        evidence={"reasons": ["完整转写包含目标家长、家庭冲突与可解释的心理机制"]},
        reviewer="codex-semantic-review",
        idempotency_key=key,
        fit_score=0.9 if outcome == "formal_rewrite_base" else 0.3,
    )


def test_automatic_rejection_can_be_semantically_accepted_and_goal_moves_to_completing(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    task_id = _task(store, role_id=role_id, target_count=1)
    material_id = _material(store, task_id=task_id, role_id=role_id, work_id="accepted-1")
    service = TaskReviewService(store)

    result = _review(
        service,
        task_id=task_id,
        material_id=material_id,
        role_id=role_id,
        outcome="formal_rewrite_base",
        key="review:accepted-1:v1",
    )

    assert result["review"]["automatic_match_snapshot"]["decision"] == "rejected"
    assert result["review"]["outcome"] == "formal_rewrite_base"
    assert result["action"]["status"] == "succeeded"
    assert result["progress"]["qualified_formal_base_count"] == 1
    assert result["progress"]["remaining_count"] == 0
    assert result["task"]["status"] == "completing"
    match = store.list_material_role_matches(
        material_id=material_id,
        role_id=role_id,
        task_id=task_id,
    )[0]
    assert match["decision"] == "accepted"
    assert match["decision_source"] == "full-transcript-semantic-review"


def test_review_cli_records_evidence_and_returns_durable_progress(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    task_id = _task(store, role_id=role_id, target_count=1)
    material_id = _material(store, task_id=task_id, role_id=role_id, work_id="cli-review")

    assert main(
        [
            "--db-path",
            str(store.db_path),
            "collect",
            "task",
            "review",
            "--task-id",
            task_id,
            "--material-id",
            material_id,
            "--role-id",
            role_id,
            "--outcome",
            "formal_rewrite_base",
            "--topic-direction",
            "亲子沟通",
            "--content-mechanism",
            "父母焦虑影响沟通顺序",
            "--reason",
            "完整转写包含目标家长、冲突和心理机制",
            "--json",
        ]
    ) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["review"]["outcome"] == "formal_rewrite_base"
    assert result["action"]["status"] == "succeeded"
    assert result["task"]["status"] == "completing"


def test_successful_review_retry_is_idempotent_and_repairs_post_commit_state_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    task_id = _task(store, role_id=role_id, target_count=1)
    material_id = _material(store, task_id=task_id, role_id=role_id, work_id="retry-1")
    service = TaskReviewService(store)
    original_reconcile = service._reconcile_task_state

    def fail_after_review_commit(**_kwargs):
        raise RuntimeError("simulated crash after review commit")

    monkeypatch.setattr(service, "_reconcile_task_state", fail_after_review_commit)
    with pytest.raises(RuntimeError, match="simulated crash"):
        _review(
            service,
            task_id=task_id,
            material_id=material_id,
            role_id=role_id,
            outcome="formal_rewrite_base",
            key="review:retry-1:v1",
        )
    assert len(store.list_collection_material_reviews(task_id=task_id)) == 1
    assert store.get_collection_task(task_id)["status"] == "awaiting_review"

    monkeypatch.setattr(service, "_reconcile_task_state", original_reconcile)
    repaired = _review(
        service,
        task_id=task_id,
        material_id=material_id,
        role_id=role_id,
        outcome="formal_rewrite_base",
        key="review:retry-1:v1",
    )
    version_after_repair = repaired["task"]["state_version"]
    repeated = _review(
        service,
        task_id=task_id,
        material_id=material_id,
        role_id=role_id,
        outcome="formal_rewrite_base",
        key="review:retry-1:v1",
    )

    assert repaired["task"]["status"] == "completing"
    assert repeated["review"]["id"] == repaired["review"]["id"]
    assert repeated["action"]["id"] == repaired["action"]["id"]
    assert repeated["task"]["state_version"] == version_after_repair
    assert len(store.list_collection_material_reviews(task_id=task_id)) == 1


def test_rejected_reviews_leave_no_pending_material_and_move_to_strategy(tmp_path: Path) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    task_id = _task(store, role_id=role_id, target_count=20)
    first = _material(store, task_id=task_id, role_id=role_id, work_id="rejected-1")
    second = _material(store, task_id=task_id, role_id=role_id, work_id="rejected-2")
    service = TaskReviewService(store)

    first_result = _review(
        service,
        task_id=task_id,
        material_id=first,
        role_id=role_id,
        outcome="rejected",
        key="review:rejected-1:v1",
    )
    assert first_result["progress"]["pending_review_count"] == 1
    assert first_result["task"]["status"] == "awaiting_review"

    second_result = _review(
        service,
        task_id=task_id,
        material_id=second,
        role_id=role_id,
        outcome="rejected",
        key="review:rejected-2:v1",
    )
    assert second_result["progress"]["pending_review_count"] == 0
    assert second_result["progress"]["qualified_formal_base_count"] == 0
    assert second_result["task"]["status"] == "awaiting_strategy"
    assert {review["outcome"] for review in store.list_collection_material_reviews(task_id=task_id)} == {
        "rejected"
    }


def test_open_review_action_keeps_task_awaiting_review_until_action_is_cancelled(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    task_id = _task(store, role_id=role_id, target_count=20)
    material_id = _material(store, task_id=task_id, role_id=role_id, work_id="pending-action")
    waiting_action = store.create_collection_task_action(
        task_id=task_id,
        action_type="review_material",
        idempotency_key="planned-follow-up",
        input_payload={"material_id": material_id, "purpose": "follow-up"},
    )
    service = TaskReviewService(store)

    result = _review(
        service,
        task_id=task_id,
        material_id=material_id,
        role_id=role_id,
        outcome="rejected",
        key="review:pending-action:v1",
    )
    assert result["progress"]["pending_review_count"] == 0
    assert result["progress"]["pending_review_action_count"] == 1
    assert result["task"]["status"] == "awaiting_review"

    store.update_collection_task_action_status(waiting_action["id"], status="cancelled")
    reconciled = _review(
        service,
        task_id=task_id,
        material_id=material_id,
        role_id=role_id,
        outcome="rejected",
        key="review:pending-action:v1",
    )
    assert reconciled["progress"]["pending_review_action_count"] == 0
    assert reconciled["task"]["status"] == "awaiting_strategy"


@pytest.mark.parametrize("race", ["role_version", "transcript"])
def test_review_detects_role_or_transcript_race_and_fails_action_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    race: str,
) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    task_id = _task(store, role_id=role_id, target_count=1)
    material_id = _material(store, task_id=task_id, role_id=role_id, work_id=f"race-{race}")
    service = TaskReviewService(store)
    original_record = store.record_collection_material_review

    def mutate_then_record(**kwargs):
        with store.connect() as conn:
            if race == "role_version":
                conn.execute(
                    "UPDATE ip_roles SET profile_version = profile_version + 1 WHERE id = ?",
                    (role_id,),
                )
            else:
                transcription_id = store.get_collected_material(material_id)["transcription_id"]
                conn.execute(
                    "UPDATE material_transcriptions SET transcript_text = transcript_text || ' 已变化' WHERE id = ?",
                    (transcription_id,),
                )
        return original_record(**kwargs)

    monkeypatch.setattr(store, "record_collection_material_review", mutate_then_record)
    expected = "role profile version conflict" if race == "role_version" else "transcript changed"
    with pytest.raises(RuntimeError, match=expected):
        _review(
            service,
            task_id=task_id,
            material_id=material_id,
            role_id=role_id,
            outcome="formal_rewrite_base",
            key=f"review:race-{race}:v1",
        )

    assert store.list_collection_material_reviews(task_id=task_id) == []
    action = next(
        item
        for item in store.list_collection_task_actions(task_id=task_id)
        if item["idempotency_key"] == f"review:race-{race}:v1"
    )
    assert action["status"] == "failed"
    assert expected in action["error"]["message"]
    assert store.get_collection_task(task_id)["status"] == "awaiting_review"


def test_review_validates_evidence_before_creating_action(tmp_path: Path) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    task_id = _task(store, role_id=role_id, target_count=1)
    material_id = _material(store, task_id=task_id, role_id=role_id, work_id="bad-evidence")
    service = TaskReviewService(store)

    with pytest.raises(ValueError, match="evidence.reasons"):
        service.review(
            task_id=task_id,
            material_id=material_id,
            role_id=role_id,
            outcome="formal_rewrite_base",
            topic_direction="亲子沟通",
            content_mechanism="心理机制",
            evidence={"reasons": []},
            reviewer="codex",
            idempotency_key="bad-evidence",
        )
    assert store.list_collection_task_actions(task_id=task_id) == []


def test_one_role_goal_does_not_complete_a_multi_role_task(tmp_path: Path) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    second_role_id = store.upsert_ip_role(
        name="第二心理角色",
        positioning="家庭关系咨询",
        confirmation_status="confirmed",
        search_keywords=["家庭关系"],
    )
    task_id = _task(store, role_id=role_id, target_count=1)
    store.upsert_collection_task_role(
        task_id=task_id,
        role_id=second_role_id,
        target_count=1,
        status="awaiting_review",
    )
    material_id = _material(store, task_id=task_id, role_id=role_id, work_id="multi-role")

    result = _review(
        TaskReviewService(store),
        task_id=task_id,
        material_id=material_id,
        role_id=role_id,
        outcome="formal_rewrite_base",
        key="review:multi-role:v1",
    )

    by_role = {item["role_id"]: item for item in result["progress"]["goal_by_role"]}
    assert by_role[role_id]["remaining_count"] == 0
    assert by_role[second_role_id]["remaining_count"] == 1
    assert result["task"]["status"] == "awaiting_review"
