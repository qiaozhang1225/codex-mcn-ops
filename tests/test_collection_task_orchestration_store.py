from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mcn_ops.migrations import migrate_collection_task_orchestration_v1
from mcn_ops.store import Store


def _store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    migrate_collection_task_orchestration_v1(store.db_path)
    return store


def _task(store: Store, *, target_count: int = 20, like_floor: int = 2000) -> str:
    task_id = store.create_collection_task(
        command="collect task keyword",
        target_scope="keyword",
        target_count_per_role=target_count,
        topic="青春期孩子",
        parsed={"policy": {"viral_like_floor": like_floor}},
        status="ready_for_search",
    )
    return task_id


def _role(store: Store) -> str:
    return store.upsert_ip_role(
        name="宋立心理",
        positioning="青春期家庭心理",
        confirmation_status="confirmed",
        search_keywords=["青春期孩子", "亲子沟通"],
    )


def _material(
    store: Store,
    *,
    task_id: str,
    role_id: str,
    source_link: str,
    likes: int = 5000,
    transcript: str = "孩子拒绝沟通的时候，父母先处理自己的焦虑，再理解孩子的心理需要。",
) -> str:
    run_id = store.create_collection_run(
        task_id=task_id,
        role_id=role_id,
        topic="青春期孩子",
        target_count=1,
        like_floor=2000,
        super_like_threshold=100000,
        tool_provider="wechat_channels_remote",
    )
    return store.insert_collected_material(
        run_id=run_id,
        source_package={
            "task_id": task_id,
            "role_id": role_id,
            "source_link": source_link,
            "source_platform": "wechat_channels",
            "title": "亲子沟通",
            "transcript_text": transcript,
            "public_metrics": {"likes": likes},
            "material_eligibility": {"eligibility_status": "accepted"},
        },
        material_understanding={"topic_summary": transcript},
        raw={},
    )


def _active_review_action(store: Store, *, task_id: str, material_id: str) -> dict[str, object]:
    action = store.create_collection_task_action(
        task_id=task_id,
        action_type="review_material",
        idempotency_key=f"review:{material_id}",
        input_payload={"material_id": material_id},
        reason="full transcript review",
    )
    action = store.claim_collection_task_action(
        action["id"],
        lease_owner="codex-reviewer",
        lease_expires_at="2026-08-23T12:00:00+00:00",
    )
    return store.update_collection_task_action_status(action["id"], status="running")


def test_action_idempotency_single_active_acquisition_and_task_cas(tmp_path: Path) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    first = store.create_collection_task_action(
        task_id=task_id,
        action_type="search_keyword",
        idempotency_key="search:青春期孩子:first",
        input_payload={"keyword": "青春期孩子", "secret": "must-not-persist"},
    )
    repeated = store.create_collection_task_action(
        task_id=task_id,
        action_type="search_keyword",
        idempotency_key="search:青春期孩子:first",
        input_payload={"keyword": "青春期孩子", "secret": "different-secret"},
    )
    assert repeated["id"] == first["id"]
    assert repeated["input"]["secret"] == "<redacted>"

    with pytest.raises(ValueError, match="idempotency key conflict"):
        store.create_collection_task_action(
            task_id=task_id,
            action_type="search_keyword",
            idempotency_key="search:青春期孩子:first",
            input_payload={"keyword": "亲子沟通"},
        )

    claimed = store.claim_collection_task_action(
        first["id"],
        lease_owner="worker-a",
        lease_expires_at="2026-08-23T12:00:00+00:00",
        expected_task_state_version=0,
    )
    assert claimed["status"] == "claimed"
    assert store.get_collection_task(task_id)["status"] == "acquiring"
    assert store.get_collection_task(task_id)["state_version"] == 1

    second = store.create_collection_task_action(
        task_id=task_id,
        action_type="continue_keyword",
        idempotency_key="search:青春期孩子:second",
        input_payload={"keyword": "青春期孩子", "cursor": "next"},
    )
    with pytest.raises(RuntimeError, match="active acquisition action"):
        store.claim_collection_task_action(
            second["id"],
            lease_owner="worker-b",
            lease_expires_at="2026-08-23T12:00:00+00:00",
        )

    transitioned = store.compare_and_swap_collection_task(
        task_id,
        expected_state_version=1,
        status="awaiting_strategy",
    )
    assert transitioned["state_version"] == 2
    with pytest.raises(RuntimeError, match="state version conflict"):
        store.compare_and_swap_collection_task(
            task_id,
            expected_state_version=1,
            status="blocked",
        )


def test_open_task_configuration_update_is_cas_and_audited(tmp_path: Path) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    task = store.get_collection_task(task_id)
    assert task is not None
    parsed = dict(task["parsed"])
    parsed["policy"] = {"viral_like_floor": 2000, "max_duration_seconds": 900}

    updated = store.update_collection_task_configuration(
        task_id,
        expected_state_version=0,
        parsed=parsed,
        event_type="channels_task_policy_tuned",
        event_payload={"changes": {"max_duration_seconds": 900}},
    )

    assert updated["status"] == "ready_for_search"
    assert updated["state_version"] == 1
    assert updated["parsed"]["policy"]["max_duration_seconds"] == 900
    assert store.list_collection_task_events(task_id=task_id)[-1]["event_type"] == (
        "channels_task_policy_tuned"
    )
    with pytest.raises(RuntimeError, match="state version conflict"):
        store.update_collection_task_configuration(
            task_id,
            expected_state_version=0,
            parsed=parsed,
        )


def test_frontier_advance_is_cas_idempotent_and_only_authoritative_exhaustion_closes_it(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    action = store.create_collection_task_action(
        task_id=task_id,
        action_type="search_keyword",
        idempotency_key="page-1",
        input_payload={"keyword": "青春期孩子"},
    )
    action = store.claim_collection_task_action(
        action["id"],
        lease_owner="worker-a",
        lease_expires_at="2026-08-23T12:00:00+00:00",
        expected_task_state_version=0,
    )
    store.update_collection_task_action_status(action["id"], status="running")
    run_id = store.create_collection_run(
        task_id=task_id,
        role_id=None,
        topic="青春期孩子",
        target_count=1,
        like_floor=2000,
        super_like_threshold=100000,
        tool_provider="wechat_channels_remote",
        action_id=action["id"],
    )
    source_work_id = store.upsert_source_work(
        platform="wechat_channels",
        platform_work_id="frontier-work-1",
        title="候选素材",
    )
    frontier = store.upsert_collection_task_frontier(
        task_id=task_id,
        frontier_type="keyword",
        frontier_key="青春期孩子",
    )

    with pytest.raises(KeyError, match="source work not found"):
        store.advance_collection_task_frontier(
            frontier["id"],
            action_id=action["id"],
            expected_version=0,
            cursor={"offset": 50},
            source_exhausted=False,
            candidates=[{"run_id": run_id, "source_work_id": "missing-work"}],
        )
    assert store.get_collection_task_frontier(frontier["id"])["version"] == 0
    assert store.list_collection_candidates(task_id=task_id) == []

    first = store.advance_collection_task_frontier(
        frontier["id"],
        action_id=action["id"],
        expected_version=0,
        cursor={"offset": 50},
        source_exhausted=False,
        page_count_delta=1,
        result_count_delta=50,
        candidates=[
            {
                "run_id": run_id,
                "source_work_id": source_work_id,
                "status": "discovered",
                "selection_reason": "viral floor passed",
            }
        ],
    )
    assert first["status"] == "open"
    assert first["traversal_complete"] is False
    assert first["page_count"] == 1
    assert len(first["candidate_ids"]) == 1
    assert len(store.list_collection_candidates(task_id=task_id)) == 1
    repeated = store.advance_collection_task_frontier(
        frontier["id"],
        action_id=action["id"],
        expected_version=0,
        cursor={"offset": 50},
        source_exhausted=False,
        page_count_delta=1,
        result_count_delta=50,
    )
    assert repeated["version"] == 1
    assert repeated["page_count"] == 1

    store.update_collection_task_action_status(action["id"], status="succeeded")
    next_action = store.create_collection_task_action(
        task_id=task_id,
        action_type="continue_keyword",
        idempotency_key="page-2",
        input_payload={"keyword": "青春期孩子", "cursor": {"offset": 50}},
    )
    next_action = store.claim_collection_task_action(
        next_action["id"],
        lease_owner="worker-a",
        lease_expires_at="2026-08-23T12:00:00+00:00",
    )
    store.update_collection_task_action_status(next_action["id"], status="running")
    with pytest.raises(RuntimeError, match="frontier version conflict"):
        store.advance_collection_task_frontier(
            frontier["id"],
            action_id=next_action["id"],
            expected_version=0,
            cursor={},
            source_exhausted=True,
        )
    exhausted = store.advance_collection_task_frontier(
        frontier["id"],
        action_id=next_action["id"],
        expected_version=1,
        cursor={},
        source_exhausted=True,
        result_count_delta=2,
    )
    assert exhausted["status"] == "exhausted"
    assert exhausted["traversal_complete"] is True


def test_review_is_atomic_and_formal_count_is_distinct_by_source_and_excludes_any_use(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    task_id = _task(store, target_count=20, like_floor=2000)
    first_material = _material(
        store,
        task_id=task_id,
        role_id=role_id,
        source_link="channels://same-source",
    )
    duplicate_material = _material(
        store,
        task_id=task_id,
        role_id=role_id,
        source_link="channels://same-source",
    )
    assert duplicate_material != first_material
    for material_id in (first_material, duplicate_material):
        store.insert_material_role_match(
            material_id=material_id,
            role_id=role_id,
            task_id=task_id,
            fit_score=0.45,
            decision="rejected",
            reasons=["automatic exact-term matcher rejected"],
        )
        action = _active_review_action(store, task_id=task_id, material_id=material_id)
        transcript = store.get_collected_material(material_id)["transcript_text"].strip()
        review = store.record_collection_material_review(
            task_id=task_id,
            action_id=action["id"],
            material_id=material_id,
            role_id=role_id,
            outcome="formal_rewrite_base",
            topic_direction="亲子沟通",
            content_mechanism="父母焦虑影响沟通",
            evidence={"reasons": ["完整转写与目标家长及亲子沟通机制一致"]},
            reviewer="codex-semantic-review",
            role_profile_version=1,
            transcript_sha256=hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
            fit_score=0.9,
        )
        assert review["automatic_match_snapshot"]["decision"] == "rejected"

    store.insert_material_role_match(
        material_id=first_material,
        role_id=role_id,
        task_id=task_id,
        fit_score=0.1,
        decision="rejected",
        reasons=["late automatic matcher retry"],
    )
    preserved = store.list_material_role_matches(
        material_id=first_material,
        role_id=role_id,
        task_id=task_id,
    )[0]
    assert preserved["decision"] == "accepted"
    assert preserved["decision_source"] == "full-transcript-semantic-review"
    assert preserved["review_id"] is not None

    counted = store.count_available_task_formal_bases(task_id=task_id, role_id=role_id)
    assert counted["qualified_formal_base_count"] == 1
    assert len(counted["source_work_ids"]) == 1

    content_id = store.create_content_package(title="已使用", body="body", media_paths=[])
    store.insert_material_creation(
        material_id=duplicate_material,
        role_id=role_id,
        content_package_id=content_id,
        task_id=task_id,
        platform="wechat_channels",
    )
    after_use = store.count_available_task_formal_bases(task_id=task_id, role_id=role_id)
    assert after_use["qualified_formal_base_count"] == 0


def test_failed_review_validation_rolls_back_all_review_facts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    role_id = _role(store)
    task_id = _task(store)
    material_id = _material(store, task_id=task_id, role_id=role_id, source_link="channels://rollback")
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=task_id,
        fit_score=0.4,
        decision="rejected",
    )
    action = _active_review_action(store, task_id=task_id, material_id=material_id)

    with pytest.raises(RuntimeError, match="transcript changed"):
        store.record_collection_material_review(
            task_id=task_id,
            action_id=action["id"],
            material_id=material_id,
            role_id=role_id,
            outcome="formal_rewrite_base",
            topic_direction="亲子沟通",
            content_mechanism="心理需要",
            evidence={"reasons": ["test"]},
            reviewer="codex",
            role_profile_version=1,
            transcript_sha256="0" * 64,
            fit_score=0.9,
        )

    assert store.list_collection_material_reviews(task_id=task_id) == []
    matches = store.list_material_role_matches(material_id=material_id, role_id=role_id, task_id=task_id)
    assert matches[0]["decision"] == "rejected"
    assert store.get_collection_task_action(action["id"])["status"] == "running"


def test_channels_session_is_single_per_worker_cas_and_cleanup_verified(tmp_path: Path) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    session = store.create_channels_acquisition_session(
        task_id=task_id,
        worker_key="workstation:qiaoz",
        windows_host="192.168.3.112",
        certificate_thumbprint="D70CD039",
        worker_executable="D:\\wx-channel-poc\\wx_channel_cloud.exe",
        lease_expires_at="2026-08-23T12:00:00+00:00",
        metadata={"session_secret": "must-not-persist"},
    )
    assert session["metadata"]["session_secret"] == "<redacted>"
    active = store.update_channels_acquisition_session(
        session["id"],
        expected_state_version=0,
        status="active",
        heartbeat=True,
        lease_expires_at="2026-08-23T13:00:00+00:00",
    )
    assert active["state_version"] == 1
    assert active["last_heartbeat_at"] is not None
    with pytest.raises(RuntimeError, match="state version conflict"):
        store.update_channels_acquisition_session(
            session["id"],
            expected_state_version=0,
            status="degraded",
        )
    cleanup = store.update_channels_acquisition_session(
        session["id"],
        expected_state_version=1,
        status="cleanup_pending",
    )
    with pytest.raises(ValueError, match="cleanup verification"):
        store.update_channels_acquisition_session(
            session["id"],
            expected_state_version=cleanup["state_version"],
            status="cleaned",
        )
    cleaned = store.update_channels_acquisition_session(
        session["id"],
        expected_state_version=cleanup["state_version"],
        status="cleaned",
        cleanup_verified=True,
    )
    assert cleaned["cleanup_verified_at"] is not None
    assert [event["event_seq"] for event in store.list_channels_acquisition_events(session_id=session["id"])] == [1, 2, 3, 4]
