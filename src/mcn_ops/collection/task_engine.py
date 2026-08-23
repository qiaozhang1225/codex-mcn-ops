from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .task_contracts import (
    ACQUISITION_ACTION_TYPES,
    CollectionActionStatus,
    CollectionActionType,
    CollectionFrontierStatus,
    CollectionFrontierType,
    CollectionTaskStatus,
)

MAX_PAGES_PER_ACTION = 5
_SEARCH_ACTIONS = {
    CollectionActionType.SEARCH_KEYWORD,
    CollectionActionType.CONTINUE_KEYWORD,
    CollectionActionType.SEARCH_RELATED_KEYWORD,
}
_ACTION_TOOL_NAMES = {
    CollectionActionType.SEARCH_KEYWORD: "channels_search_videos",
    CollectionActionType.CONTINUE_KEYWORD: "channels_search_videos",
    CollectionActionType.SEARCH_RELATED_KEYWORD: "channels_search_videos",
    CollectionActionType.INSPECT_AUTHOR: "channels_inspect_author",
    CollectionActionType.COLLECT_AUTHOR_WORKS: "channels_list_author_works",
}
_ACTIVE_ACTION_STATUSES = {
    CollectionActionStatus.CLAIMED.value,
    CollectionActionStatus.RUNNING.value,
}
_RETRYABLE_ACTION_STATUSES = {
    CollectionActionStatus.PLANNED.value,
    CollectionActionStatus.INTERRUPTED.value,
}
_BLOCKING_STOP_REASONS = {
    "cursor_missing",
    "cursor_cycle",
    "pagination_unverified",
    "source_exhausted_unverified",
}


class ActionExecutor(Protocol):
    def execute(
        self,
        action_type: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class ToolRegistry(Protocol):
    def run(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ActionExecutionOutcome:
    action_id: str
    status: str
    blocked: bool
    code: str
    frontier_id: str
    frontier_status: str
    source_exhausted: bool = False
    candidate_count: int = 0


@dataclass(frozen=True)
class TaskStateProposal:
    status: str
    reason: str
    pending_review_count: int
    planned_acquisition_count: int
    open_frontier_count: int
    exhausted_frontier_count: int
    blocked_action_count: int
    terminal: bool = False
    cleanup_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CollectionTaskActionEngine:
    """Execute one persisted, bounded acquisition action at a time.

    The engine intentionally stops before task completion and certificate/session
    cleanup. Those transitions belong to the outer workflow after review and
    strategy decisions have been persisted.
    """

    def __init__(
        self,
        store: Any,
        *,
        lease_owner: str,
        executor: ActionExecutor
        | Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
        | None = None,
        registry: ToolRegistry | None = None,
        lease_seconds: int = 300,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (executor is None) == (registry is None):
            raise ValueError("exactly one of executor or registry is required")
        normalized_owner = str(lease_owner or "").strip()
        if not normalized_owner:
            raise ValueError("lease_owner is required")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.store = store
        self.lease_owner = normalized_owner
        self.executor = executor
        self.registry = registry
        self.lease_seconds = lease_seconds
        self.clock = clock or (lambda: datetime.now(UTC))

    def plan_keyword(
        self,
        *,
        task_id: str,
        keyword: str,
        max_pages: int = 1,
        page_size: int = 20,
        role_id: str | None = None,
        strategy_iteration: int = 0,
        reason: str = "",
    ) -> dict[str, Any]:
        frontier = self._keyword_frontier(task_id, keyword)
        if int(frontier["version"]) != 0 or int(frontier["page_count"]) != 0:
            raise ValueError("keyword frontier already started; plan a continue action")
        return self._plan(
            task_id=task_id,
            action_type=CollectionActionType.SEARCH_KEYWORD,
            frontier=frontier,
            operation={"keyword": keyword.strip()},
            max_pages=max_pages,
            page_size=page_size,
            role_id=role_id,
            strategy_iteration=strategy_iteration,
            reason=reason,
        )

    def plan_continue_keyword(
        self,
        *,
        task_id: str,
        keyword: str,
        max_pages: int = 1,
        page_size: int = 20,
        role_id: str | None = None,
        strategy_iteration: int = 0,
        reason: str = "",
    ) -> dict[str, Any]:
        frontier = self._find_frontier(task_id, CollectionFrontierType.KEYWORD, keyword)
        self._require_open(frontier)
        if not _cursor_token(frontier.get("cursor")):
            raise ValueError(
                "cursor_missing: keyword continuation requires a persisted cursor"
            )
        return self._plan(
            task_id=task_id,
            action_type=CollectionActionType.CONTINUE_KEYWORD,
            frontier=frontier,
            operation={"keyword": keyword.strip()},
            max_pages=max_pages,
            page_size=page_size,
            role_id=role_id,
            strategy_iteration=strategy_iteration,
            reason=reason,
        )

    def plan_related_keyword(
        self,
        *,
        task_id: str,
        keyword: str,
        origin_keyword: str,
        max_pages: int = 1,
        page_size: int = 20,
        role_id: str | None = None,
        strategy_iteration: int = 0,
        reason: str = "",
    ) -> dict[str, Any]:
        frontier = self._keyword_frontier(task_id, keyword)
        if int(frontier["version"]) != 0 or int(frontier["page_count"]) != 0:
            raise ValueError(
                "related keyword frontier already started; plan a continue action"
            )
        return self._plan(
            task_id=task_id,
            action_type=CollectionActionType.SEARCH_RELATED_KEYWORD,
            frontier=frontier,
            operation={
                "keyword": keyword.strip(),
                "origin_keyword": str(origin_keyword or "").strip(),
            },
            max_pages=max_pages,
            page_size=page_size,
            role_id=role_id,
            strategy_iteration=strategy_iteration,
            reason=reason,
        )

    def plan_inspect_author(
        self,
        *,
        task_id: str,
        platform_author_id: str,
        role_id: str | None = None,
        strategy_iteration: int = 0,
        reason: str = "",
    ) -> dict[str, Any]:
        frontier = self._author_frontier(task_id, platform_author_id)
        self._require_open(frontier)
        return self._plan(
            task_id=task_id,
            action_type=CollectionActionType.INSPECT_AUTHOR,
            frontier=frontier,
            operation={"platform_author_id": platform_author_id.strip()},
            max_pages=1,
            page_size=1,
            role_id=role_id,
            strategy_iteration=strategy_iteration,
            reason=reason,
        )

    def plan_collect_author(
        self,
        *,
        task_id: str,
        platform_author_id: str,
        max_pages: int = 1,
        page_size: int = 20,
        role_id: str | None = None,
        author_feed_live_poc_verified: bool = False,
        strategy_iteration: int = 0,
        reason: str = "",
    ) -> dict[str, Any]:
        frontier = self._author_frontier(task_id, platform_author_id)
        self._require_open(frontier)
        return self._plan(
            task_id=task_id,
            action_type=CollectionActionType.COLLECT_AUTHOR_WORKS,
            frontier=frontier,
            operation={
                "platform_author_id": platform_author_id.strip(),
                "author_feed_live_poc_verified": bool(author_feed_live_poc_verified),
            },
            max_pages=max_pages,
            page_size=page_size,
            role_id=role_id,
            strategy_iteration=strategy_iteration,
            reason=reason,
        )

    def recover_expired_claims(self, *, task_id: str) -> list[dict[str, Any]]:
        now = _aware_utc(self.clock())
        recovered: list[dict[str, Any]] = []
        for action in self.store.list_collection_task_actions(task_id=task_id):
            if action["status"] not in _ACTIVE_ACTION_STATUSES:
                continue
            expires_at = _parse_timestamp(action.get("lease_expires_at"))
            # Missing or malformed leases are not safe to steal automatically.
            if expires_at is None or expires_at > now:
                continue
            recovered.append(
                self.store.update_collection_task_action_status(
                    action["id"],
                    status=CollectionActionStatus.INTERRUPTED.value,
                    error={
                        "code": "claim_expired",
                        "message": "the prior acquisition claim expired and was recovered",
                        "blocked": False,
                    },
                )
            )
        return recovered

    def claim_one(self, *, task_id: str) -> dict[str, Any] | None:
        self.recover_expired_claims(task_id=task_id)
        actions = self.store.list_collection_task_actions(task_id=task_id)
        if any(action["status"] in _ACTIVE_ACTION_STATUSES for action in actions):
            return None
        task = self.store.get_collection_task(task_id)
        if task is None:
            raise KeyError(f"collection task not found: {task_id}")
        if task["status"] not in {
            CollectionTaskStatus.READY_FOR_SEARCH.value,
            CollectionTaskStatus.ACQUIRING.value,
        }:
            return None
        action = next(
            (
                row
                for row in actions
                if row["status"] in _RETRYABLE_ACTION_STATUSES
                and CollectionActionType(row["action_type"]) in ACQUISITION_ACTION_TYPES
            ),
            None,
        )
        if action is None:
            return None
        lease_expires_at = _aware_utc(self.clock()) + timedelta(
            seconds=self.lease_seconds
        )
        expected_version = (
            int(task["state_version"])
            if task["status"] == CollectionTaskStatus.READY_FOR_SEARCH.value
            else None
        )
        return self.store.claim_collection_task_action(
            action["id"],
            lease_owner=self.lease_owner,
            lease_expires_at=lease_expires_at.isoformat(),
            expected_task_state_version=expected_version,
        )

    def execute_one(self, *, task_id: str) -> ActionExecutionOutcome | None:
        action = self.claim_one(task_id=task_id)
        if action is None:
            return None
        action = self.store.update_collection_task_action_status(
            action["id"], status=CollectionActionStatus.RUNNING.value
        )
        frontier_id = str(action["input"].get("frontier_id") or "")
        frontier = self.store.get_collection_task_frontier(frontier_id)
        if frontier is None or frontier["task_id"] != task_id:
            return self._fail(action, frontier_id, "frontier_missing", True)
        if frontier["status"] != CollectionFrontierStatus.OPEN.value:
            return self._fail(
                action, frontier_id, "frontier_not_open", True, frontier=frontier
            )
        if int(frontier["version"]) != int(action["input"].get("frontier_version", -1)):
            return self._fail(
                action,
                frontier_id,
                "frontier_version_conflict",
                True,
                frontier=frontier,
            )
        if _canonical(frontier.get("cursor") or {}) != _canonical(
            action["input"].get("cursor") or {}
        ):
            return self._fail(
                action, frontier_id, "frontier_cursor_changed", True, frontier=frontier
            )

        action_type = CollectionActionType(action["action_type"])
        if action_type is CollectionActionType.CONTINUE_KEYWORD and not _cursor_token(
            frontier["cursor"]
        ):
            return self._fail(
                action, frontier_id, "cursor_missing", True, frontier=frontier
            )
        if action_type is CollectionActionType.COLLECT_AUTHOR_WORKS and not bool(
            action["input"].get("author_feed_live_poc_verified")
        ):
            return self._fail(
                action,
                frontier_id,
                "author_feed_live_poc_required",
                True,
                frontier=frontier,
            )

        try:
            provider_result = dict(
                self._execute(action_type, self._tool_arguments(action))
            )
        except Exception as exc:  # noqa: BLE001 - persist arbitrary executor failures
            return self._fail(
                action,
                frontier_id,
                "executor_failed",
                False,
                message=str(exc),
                frontier=frontier,
            )
        if provider_result.get("ok") is False:
            return self._fail(
                action,
                frontier_id,
                "provider_failed",
                False,
                message=str(
                    provider_result.get("error") or "provider returned ok=false"
                ),
                frontier=frontier,
            )
        if action_type is CollectionActionType.COLLECT_AUTHOR_WORKS:
            gate = (provider_result.get("normalized") or {}).get("capability_gate")
            if not isinstance(gate, dict) or not (
                gate.get("live_poc_verified") is True
                and gate.get("production_ready") is True
            ):
                return self._fail(
                    action,
                    frontier_id,
                    "author_feed_live_poc_required",
                    True,
                    frontier=frontier,
                )

        if action_type is CollectionActionType.INSPECT_AUTHOR:
            paging = {
                "captured_pages": 0,
                "captured_items": 0,
                "stop_reason": "profile_inspected",
                "source_exhausted": False,
            }
            next_cursor = dict(frontier["cursor"])
            source_exhausted = False
        else:
            paging = provider_result.get("paging")
            if not isinstance(paging, dict):
                return self._fail(
                    action, frontier_id, "paging_missing", True, frontier=frontier
                )
            safety_error = _paging_safety_error(
                paging, previous_cursor=_cursor_token(frontier["cursor"])
            )
            if safety_error:
                return self._fail(
                    action, frontier_id, safety_error, True, frontier=frontier
                )
            source_exhausted = paging.get("source_exhausted") is True
            next_cursor = (
                {}
                if source_exhausted
                else {
                    "next_cursor": str(
                        paging.get("next_cursor") or paging.get("cursor") or ""
                    )
                }
            )

        try:
            candidates = self._prepare_candidates(action, provider_result)
            advanced = self.store.advance_collection_task_frontier(
                frontier_id,
                action_id=action["id"],
                expected_version=int(frontier["version"]),
                cursor=next_cursor,
                source_exhausted=source_exhausted,
                page_count_delta=max(0, int(paging.get("captured_pages") or 0)),
                result_count_delta=max(
                    0,
                    int(paging.get("captured_items") or len(candidates)),
                ),
                candidates=candidates,
            )
        except Exception as exc:  # noqa: BLE001 - frontier must remain fail-closed
            return self._fail(
                action,
                frontier_id,
                "frontier_advance_failed",
                False,
                message=str(exc),
                frontier=frontier,
            )

        self.store.update_collection_task_action_status(
            action["id"],
            status=CollectionActionStatus.SUCCEEDED.value,
            result={
                "provider": provider_result.get("provider"),
                "method_key": provider_result.get("method_key"),
                "paging": paging,
                "frontier_id": frontier_id,
                "frontier_version": advanced["version"],
                "candidate_count": len(candidates),
            },
        )
        return ActionExecutionOutcome(
            action_id=action["id"],
            status=CollectionActionStatus.SUCCEEDED.value,
            blocked=False,
            code="ok",
            frontier_id=frontier_id,
            frontier_status=str(advanced["status"]),
            source_exhausted=source_exhausted,
            candidate_count=len(candidates),
        )

    def propose_next_task_state(
        self,
        *,
        task_id: str,
        pending_review_count: int | None = None,
    ) -> TaskStateProposal:
        actions = self.store.list_collection_task_actions(task_id=task_id)
        frontiers = self.store.list_collection_task_frontiers(task_id=task_id)
        inferred_reviews = sum(
            1
            for action in actions
            if action["action_type"] == CollectionActionType.REVIEW_MATERIAL.value
            and action["status"]
            in {
                CollectionActionStatus.PLANNED.value,
                CollectionActionStatus.CLAIMED.value,
                CollectionActionStatus.RUNNING.value,
                CollectionActionStatus.INTERRUPTED.value,
            }
        )
        reviews = (
            inferred_reviews
            if pending_review_count is None
            else max(0, pending_review_count)
        )
        active = sum(
            1 for action in actions if action["status"] in _ACTIVE_ACTION_STATUSES
        )
        planned = sum(
            1
            for action in actions
            if action["status"] in _RETRYABLE_ACTION_STATUSES
            and CollectionActionType(action["action_type"]) in ACQUISITION_ACTION_TYPES
        )
        blocked = sum(
            1
            for action in actions
            if action["status"] == CollectionActionStatus.FAILED.value
            and bool((action.get("error") or {}).get("blocked"))
        )
        open_count = sum(1 for frontier in frontiers if frontier["status"] == "open")
        exhausted_count = sum(
            1 for frontier in frontiers if frontier["status"] == "exhausted"
        )

        if blocked:
            status, reason = (
                CollectionTaskStatus.BLOCKED.value,
                "a fail-closed action needs strategy",
            )
        elif active:
            status, reason = (
                CollectionTaskStatus.ACQUIRING.value,
                "an acquisition action is active",
            )
        elif reviews:
            status, reason = (
                CollectionTaskStatus.AWAITING_REVIEW.value,
                "materials are pending review",
            )
        elif planned:
            status, reason = (
                CollectionTaskStatus.READY_FOR_SEARCH.value,
                "acquisition actions are planned",
            )
        else:
            status, reason = (
                CollectionTaskStatus.AWAITING_STRATEGY.value,
                "no bounded action is pending; review frontier evidence before planning more work",
            )
        return TaskStateProposal(
            status=status,
            reason=reason,
            pending_review_count=reviews,
            planned_acquisition_count=planned,
            open_frontier_count=open_count,
            exhausted_frontier_count=exhausted_count,
            blocked_action_count=blocked,
        )

    def _plan(
        self,
        *,
        task_id: str,
        action_type: CollectionActionType,
        frontier: dict[str, Any],
        operation: dict[str, Any],
        max_pages: int,
        page_size: int,
        role_id: str | None,
        strategy_iteration: int,
        reason: str,
    ) -> dict[str, Any]:
        self._require_open(frontier)
        _validate_bounds(max_pages=max_pages, page_size=page_size)
        if strategy_iteration < 0:
            raise ValueError("strategy_iteration cannot be negative")
        payload = {
            **operation,
            "frontier_id": frontier["id"],
            "frontier_type": frontier["frontier_type"],
            "frontier_key": frontier["frontier_key"],
            "frontier_version": int(frontier["version"]),
            "cursor": dict(frontier.get("cursor") or {}),
            "max_pages": int(max_pages),
            "page_size": int(page_size),
            "role_id": role_id,
            "strategy_iteration": int(strategy_iteration),
        }
        key_payload = {"action_type": action_type.value, **payload}
        idempotency_key = f"task-action:v1:{action_type.value}:{_sha256(key_payload)}"
        return self.store.create_collection_task_action(
            task_id=task_id,
            action_type=action_type.value,
            idempotency_key=idempotency_key,
            input_payload=payload,
            reason=reason,
        )

    def _keyword_frontier(self, task_id: str, keyword: str) -> dict[str, Any]:
        normalized = str(keyword or "").strip()
        if not normalized:
            raise ValueError("keyword is required")
        return self.store.upsert_collection_task_frontier(
            task_id=task_id,
            frontier_type=CollectionFrontierType.KEYWORD.value,
            frontier_key=normalized,
            cursor={},
        )

    def _author_frontier(self, task_id: str, platform_author_id: str) -> dict[str, Any]:
        normalized = str(platform_author_id or "").strip()
        if not normalized:
            raise ValueError("platform_author_id is required")
        return self.store.upsert_collection_task_frontier(
            task_id=task_id,
            frontier_type=CollectionFrontierType.AUTHOR.value,
            frontier_key=normalized,
            cursor={},
        )

    def _find_frontier(
        self,
        task_id: str,
        frontier_type: CollectionFrontierType,
        frontier_key: str,
    ) -> dict[str, Any]:
        normalized = str(frontier_key or "").strip()
        for frontier in self.store.list_collection_task_frontiers(task_id=task_id):
            if (
                frontier["frontier_type"] == frontier_type.value
                and frontier["frontier_key"] == normalized
            ):
                return frontier
        raise KeyError(
            f"collection task frontier not found: {frontier_type.value}:{normalized}"
        )

    @staticmethod
    def _require_open(frontier: Mapping[str, Any]) -> None:
        if frontier.get("status") != CollectionFrontierStatus.OPEN.value:
            raise ValueError(f"frontier is not open: {frontier.get('status')}")

    def _execute(
        self,
        action_type: CollectionActionType,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if self.registry is not None:
            return self.registry.run(_ACTION_TOOL_NAMES[action_type], arguments)
        if callable(self.executor) and not hasattr(self.executor, "execute"):
            return self.executor(action_type.value, arguments)
        assert self.executor is not None
        return self.executor.execute(action_type.value, arguments)

    @staticmethod
    def _tool_arguments(action: Mapping[str, Any]) -> dict[str, Any]:
        action_type = CollectionActionType(str(action["action_type"]))
        payload = action["input"]
        cursor = _cursor_token(payload.get("cursor"))
        if action_type in _SEARCH_ACTIONS:
            return {
                "keyword": payload["keyword"],
                "cursor": cursor,
                "max_pages": int(payload["max_pages"]),
                "page_size": int(payload["page_size"]),
            }
        if action_type is CollectionActionType.INSPECT_AUTHOR:
            return {"platform_author_id": payload["platform_author_id"]}
        return {
            "platform_author_id": payload["platform_author_id"],
            "cursor": cursor,
            "max_pages": int(payload["max_pages"]),
            "page_size": int(payload["page_size"]),
        }

    def _prepare_candidates(
        self,
        action: Mapping[str, Any],
        provider_result: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        explicit = provider_result.get("candidates")
        if explicit is not None:
            if not isinstance(explicit, list):
                raise ValueError("provider candidates must be a list")
            return [dict(candidate) for candidate in explicit]
        normalized = provider_result.get("normalized")
        packages = (
            normalized.get("source_packages") if isinstance(normalized, dict) else []
        )
        if not packages:
            return []
        if not isinstance(packages, list) or any(
            not isinstance(item, dict) for item in packages
        ):
            raise ValueError("normalized.source_packages must be a list of objects")

        task = self.store.get_collection_task(action["task_id"])
        if task is None:
            raise KeyError(f"collection task not found: {action['task_id']}")
        runs = self.store.list_collection_runs(task_id=action["task_id"])
        run = next(
            (item for item in runs if item.get("action_id") == action["id"]), None
        )
        policy = task.get("parsed", {}).get("policy", {})
        if run is None:
            run_id = self.store.create_collection_run(
                task_id=action["task_id"],
                role_id=action["input"].get("role_id"),
                topic=str(
                    action["input"].get("keyword") or task.get("topic") or "channels"
                ),
                target_count=int(task.get("target_count_per_role") or len(packages)),
                like_floor=int(
                    policy.get("viral_like_floor") or policy.get("like_floor") or 0
                ),
                super_like_threshold=int(policy.get("super_like_threshold") or 100_000),
                tool_provider=str(
                    provider_result.get("provider") or "wechat_channels_remote"
                ),
                action_id=action["id"],
            )
        else:
            run_id = str(run["id"])

        result: list[dict[str, Any]] = []
        for package in packages:
            prepared = dict(package)
            prepared.setdefault("task_id", action["task_id"])
            prepared.setdefault("role_id", action["input"].get("role_id"))
            source_work_id, _, _ = self.store._persist_source_package(
                prepared,
                raw={},
                run_id=run_id,
                observation_kind="search",
                provider=str(
                    provider_result.get("provider") or "wechat_channels_remote"
                ),
            )
            result.append(
                {
                    "run_id": run_id,
                    "role_id": action["input"].get("role_id"),
                    "source_work_id": source_work_id,
                    "status": "discovered",
                    "selection_reason": f"discovered by {action['action_type']}",
                }
            )
        return result

    def _fail(
        self,
        action: Mapping[str, Any],
        frontier_id: str,
        code: str,
        blocked: bool,
        *,
        message: str | None = None,
        frontier: Mapping[str, Any] | None = None,
    ) -> ActionExecutionOutcome:
        self.store.update_collection_task_action_status(
            action["id"],
            status=CollectionActionStatus.FAILED.value,
            error={
                "code": code,
                "message": message or code.replace("_", " "),
                "blocked": blocked,
                "frontier_id": frontier_id,
            },
        )
        return ActionExecutionOutcome(
            action_id=str(action["id"]),
            status=CollectionActionStatus.FAILED.value,
            blocked=blocked,
            code=code,
            frontier_id=frontier_id,
            frontier_status=str((frontier or {}).get("status") or "missing"),
        )


def _validate_bounds(*, max_pages: int, page_size: int) -> None:
    if not 1 <= int(max_pages) <= MAX_PAGES_PER_ACTION:
        raise ValueError(f"max_pages must be between 1 and {MAX_PAGES_PER_ACTION}")
    if int(page_size) <= 0:
        raise ValueError("page_size must be positive")


def _paging_safety_error(
    paging: Mapping[str, Any], *, previous_cursor: str
) -> str | None:
    stop_reason = str(paging.get("stop_reason") or "").strip()
    if stop_reason in _BLOCKING_STOP_REASONS:
        return stop_reason
    source_exhausted = paging.get("source_exhausted") is True
    if source_exhausted:
        return (
            None
            if stop_reason == "source_exhausted"
            else "source_exhaustion_inconsistent"
        )
    if stop_reason != "max_pages":
        return "pagination_unverified"
    next_cursor = str(paging.get("next_cursor") or paging.get("cursor") or "").strip()
    if not next_cursor:
        return "cursor_missing"
    if next_cursor == previous_cursor:
        return "cursor_cycle"
    return None


def _cursor_token(cursor: Any) -> str:
    if isinstance(cursor, Mapping):
        return str(
            cursor.get("next_cursor")
            or cursor.get("cursor")
            or cursor.get("offset")
            or ""
        ).strip()
    return str(cursor or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return _aware_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
