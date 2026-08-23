from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mcn_ops.collection.task_engine import CollectionTaskActionEngine
from mcn_ops.migrations import migrate_collection_task_orchestration_v1
from mcn_ops.store import Store

NOW = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)


class FakeExecutor:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.results = list(results or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(
        self, action_type: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self.calls.append((action_type, dict(arguments)))
        if not self.results:
            raise RuntimeError("no fake result")
        result = self.results.pop(0)
        if "raise" in result:
            raise RuntimeError(str(result["raise"]))
        return result


def _store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    migrate_collection_task_orchestration_v1(store.db_path)
    return store


def _task(store: Store) -> str:
    return store.create_collection_task(
        command="collect 20 channels scripts",
        target_scope="keyword",
        target_count_per_role=20,
        topic="青春期孩子",
        parsed={"policy": {"viral_like_floor": 2000}},
        status="ready_for_search",
    )


def _engine(store: Store, executor: FakeExecutor) -> CollectionTaskActionEngine:
    return CollectionTaskActionEngine(
        store,
        lease_owner="mac-codex",
        executor=executor,
        clock=lambda: NOW,
    )


def _page(
    *,
    next_cursor: str | None = "page-2",
    stop_reason: str = "max_pages",
    source_exhausted: bool = False,
    work_id: str = "channels-work-1",
    capability_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "source_packages": [
            {
                "source_platform": "wechat_channels",
                "work_id": work_id,
                "title": "亲子沟通",
                "public_metrics": {"likes": 5000},
            }
        ]
    }
    if capability_gate is not None:
        normalized["capability_gate"] = capability_gate
    return {
        "ok": True,
        "provider": "wechat_channels_remote",
        "method_key": "wechat_channels_search",
        "normalized": normalized,
        "paging": {
            "has_next": not source_exhausted,
            "next_cursor": next_cursor,
            "captured_pages": 1,
            "captured_items": 1,
            "stop_reason": stop_reason,
            "request_satisfied": stop_reason in {"max_pages", "source_exhausted"},
            "source_exhausted": source_exhausted,
        },
    }


def test_plans_all_acquisition_actions_with_deterministic_idempotency(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    engine = _engine(store, FakeExecutor())

    first = engine.plan_keyword(task_id=task_id, keyword="青春期孩子")
    repeated = engine.plan_keyword(task_id=task_id, keyword="青春期孩子")
    related = engine.plan_related_keyword(
        task_id=task_id,
        keyword="厌学",
        origin_keyword="青春期孩子",
    )
    inspect = engine.plan_inspect_author(task_id=task_id, platform_author_id="finder-1")
    collect = engine.plan_collect_author(task_id=task_id, platform_author_id="finder-1")

    assert first["id"] == repeated["id"]
    assert first["idempotency_key"].startswith("task-action:v1:search_keyword:")
    assert related["action_type"] == "search_related_keyword"
    assert inspect["action_type"] == "inspect_author"
    assert collect["action_type"] == "collect_author_works"
    assert collect["input"]["author_feed_live_poc_verified"] is False
    assert len(store.list_collection_task_actions(task_id=task_id)) == 4


def test_max_pages_persists_candidate_and_cursor_atomically_and_remains_open(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    executor = FakeExecutor([_page(next_cursor="page-2")])
    engine = _engine(store, executor)
    action = engine.plan_keyword(task_id=task_id, keyword="青春期孩子")

    outcome = engine.execute_one(task_id=task_id)

    assert outcome is not None
    assert outcome.status == "succeeded"
    assert outcome.frontier_status == "open"
    assert outcome.source_exhausted is False
    assert executor.calls == [
        (
            "search_keyword",
            {"keyword": "青春期孩子", "cursor": "", "max_pages": 1, "page_size": 20},
        )
    ]
    frontier = store.get_collection_task_frontier(action["input"]["frontier_id"])
    assert frontier["cursor"] == {"next_cursor": "page-2"}
    assert frontier["page_count"] == 1
    assert frontier["result_count"] == 1
    assert frontier["traversal_complete"] is False
    candidates = store.list_collection_candidates(task_id=task_id)
    assert len(candidates) == 1
    assert candidates[0]["source_package"]["work_id"] == "channels-work-1"


def test_continue_reads_persisted_cursor_and_only_authoritative_exhaustion_closes(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    executor = FakeExecutor(
        [
            _page(next_cursor="page-2", work_id="work-1"),
            _page(
                next_cursor=None,
                stop_reason="source_exhausted",
                source_exhausted=True,
                work_id="work-2",
            ),
        ]
    )
    engine = _engine(store, executor)
    first = engine.plan_keyword(task_id=task_id, keyword="青春期孩子")
    assert engine.execute_one(task_id=task_id).frontier_status == "open"

    continued = engine.plan_continue_keyword(task_id=task_id, keyword="青春期孩子")
    outcome = engine.execute_one(task_id=task_id)

    assert continued["input"]["cursor"] == {"next_cursor": "page-2"}
    assert executor.calls[1][1]["cursor"] == "page-2"
    assert outcome.source_exhausted is True
    frontier = store.get_collection_task_frontier(first["input"]["frontier_id"])
    assert frontier["status"] == "exhausted"
    assert frontier["traversal_complete"] is True
    assert frontier["cursor"] == {}
    assert frontier["page_count"] == 2


@pytest.mark.parametrize(
    ("next_cursor", "expected_code"),
    [(None, "cursor_missing"), ("page-1", "cursor_cycle")],
)
def test_cursor_missing_or_cycle_fails_closed_without_advancing_frontier(
    tmp_path: Path,
    next_cursor: str | None,
    expected_code: str,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    executor = FakeExecutor([_page(next_cursor="page-1", work_id="first")])
    engine = _engine(store, executor)
    initial = engine.plan_keyword(task_id=task_id, keyword="青春期孩子")
    assert engine.execute_one(task_id=task_id).status == "succeeded"
    before = store.get_collection_task_frontier(initial["input"]["frontier_id"])
    engine.plan_continue_keyword(task_id=task_id, keyword="青春期孩子")
    executor.results.append(_page(next_cursor=next_cursor, work_id="unsafe"))

    outcome = engine.execute_one(task_id=task_id)

    assert outcome.blocked is True
    assert outcome.code == expected_code
    after = store.get_collection_task_frontier(before["id"])
    assert after["version"] == before["version"]
    assert after["cursor"] == before["cursor"]
    assert after["result_count"] == before["result_count"]
    assert len(store.list_collection_candidates(task_id=task_id)) == 1
    assert engine.propose_next_task_state(task_id=task_id).status == "blocked"


def test_executor_failure_marks_action_failed_without_advancing_frontier(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    executor = FakeExecutor([{"raise": "worker disconnected"}])
    engine = _engine(store, executor)
    action = engine.plan_keyword(task_id=task_id, keyword="青春期孩子")

    outcome = engine.execute_one(task_id=task_id)

    assert outcome.code == "executor_failed"
    assert outcome.blocked is False
    assert store.get_collection_task_action(action["id"])["status"] == "failed"
    frontier = store.get_collection_task_frontier(action["input"]["frontier_id"])
    assert frontier["version"] == 0
    assert frontier["page_count"] == 0
    assert store.list_collection_candidates(task_id=task_id) == []


def test_expired_claim_is_interrupted_and_reclaimed_but_live_claim_is_not_stolen(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    engine = _engine(store, FakeExecutor())
    action = engine.plan_keyword(task_id=task_id, keyword="青春期孩子")
    store.claim_collection_task_action(
        action["id"],
        lease_owner="dead-worker",
        lease_expires_at="2026-08-23T07:59:00+00:00",
        expected_task_state_version=0,
    )

    reclaimed = engine.claim_one(task_id=task_id)

    assert reclaimed["status"] == "claimed"
    assert reclaimed["lease_owner"] == "mac-codex"
    assert reclaimed["attempt_count"] == 2

    other_store = _store(tmp_path / "other")
    other_task = _task(other_store)
    other_engine = _engine(other_store, FakeExecutor())
    other_action = other_engine.plan_keyword(task_id=other_task, keyword="青春期孩子")
    other_store.claim_collection_task_action(
        other_action["id"],
        lease_owner="live-worker",
        lease_expires_at="2026-08-23T08:01:00+00:00",
        expected_task_state_version=0,
    )
    assert other_engine.claim_one(task_id=other_task) is None
    assert (
        other_store.get_collection_task_action(other_action["id"])["lease_owner"]
        == "live-worker"
    )


def test_author_feed_requires_both_plan_and_provider_live_poc_gates(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    executor = FakeExecutor([])
    engine = _engine(store, executor)
    action = engine.plan_collect_author(task_id=task_id, platform_author_id="finder-1")

    outcome = engine.execute_one(task_id=task_id)

    assert outcome.code == "author_feed_live_poc_required"
    assert outcome.blocked is True
    assert executor.calls == []
    frontier = store.get_collection_task_frontier(action["input"]["frontier_id"])
    assert frontier["status"] == "open"
    assert frontier["traversal_complete"] is False

    second_store = _store(tmp_path / "provider-gate")
    second_task = _task(second_store)
    provider_result = _page(
        next_cursor="author-page-2",
        capability_gate={"live_poc_verified": False, "production_ready": False},
    )
    second_executor = FakeExecutor([provider_result])
    second_engine = _engine(second_store, second_executor)
    second_action = second_engine.plan_collect_author(
        task_id=second_task,
        platform_author_id="finder-1",
        author_feed_live_poc_verified=True,
    )
    second_outcome = second_engine.execute_one(task_id=second_task)
    assert second_outcome.code == "author_feed_live_poc_required"
    assert (
        second_store.get_collection_task_frontier(
            second_action["input"]["frontier_id"]
        )["status"]
        == "open"
    )


def test_author_inspection_is_blocked_until_a_real_profile_contract_is_verified(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    executor = FakeExecutor([])
    engine = _engine(store, executor)
    action = engine.plan_inspect_author(
        task_id=task_id,
        platform_author_id="finder-1",
    )

    outcome = engine.execute_one(task_id=task_id)

    assert outcome.code == "author_inspection_live_poc_required"
    assert outcome.blocked is True
    assert executor.calls == []
    frontier = store.get_collection_task_frontier(action["input"]["frontier_id"])
    assert frontier["status"] == "open"
    assert frontier["version"] == 0


def test_state_proposal_never_completes_or_requests_cleanup(tmp_path: Path) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    engine = _engine(store, FakeExecutor())
    engine.plan_keyword(task_id=task_id, keyword="青春期孩子")

    planned = engine.propose_next_task_state(task_id=task_id)
    review = engine.propose_next_task_state(task_id=task_id, pending_review_count=2)

    assert planned.status == "ready_for_search"
    assert review.status == "awaiting_review"
    assert review.terminal is False
    assert review.cleanup_required is False


def test_unverified_author_terminal_signal_is_blocked_not_exhausted(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    task_id = _task(store)
    executor = FakeExecutor(
        [
            _page(
                next_cursor=None,
                stop_reason="source_exhausted_unverified",
                source_exhausted=False,
                capability_gate={"live_poc_verified": True, "production_ready": True},
            )
        ]
    )
    engine = _engine(store, executor)
    action = engine.plan_collect_author(
        task_id=task_id,
        platform_author_id="finder-1",
        author_feed_live_poc_verified=True,
    )

    outcome = engine.execute_one(task_id=task_id)

    assert outcome.code == "source_exhausted_unverified"
    assert outcome.blocked is True
    frontier = store.get_collection_task_frontier(action["input"]["frontier_id"])
    assert frontier["status"] == "open"
    assert frontier["traversal_complete"] is False
    assert frontier["version"] == 0
