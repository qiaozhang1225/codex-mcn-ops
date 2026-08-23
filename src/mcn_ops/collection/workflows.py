from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from ..store import Store
from .channels.factory import build_channels_collection_registry
from .channels.session import ChannelsAcquisitionController
from .douyin.contracts import DouyinProvider
from .douyin.factory import build_collection_provider
from .douyin.registry import build_douyin_registry
from .eligibility import evaluate_material_eligibility, is_material_eligible
from .mock_tools import build_mock_source_registry
from .runner import (
    CollectionConfig,
    TopicCollectionRunner,
    engagement_score,
    metric_value,
    request_fingerprint,
)
from .task_contracts import CollectionActionStatus, CollectionTaskStatus
from .task_engine import CollectionTaskActionEngine
from .understanding import (
    DEFAULT_UNDERSTANDING_MODEL,
    DEFAULT_UNDERSTANDING_PROVIDER,
    RULES_UNDERSTANDING_MODEL,
    RULES_UNDERSTANDING_PROVIDER,
    build_material_understanding,
    validate_understanding,
)

LOCAL_UNDERSTANDING_PROVIDER = RULES_UNDERSTANDING_PROVIDER
LOCAL_UNDERSTANDING_MODEL = RULES_UNDERSTANDING_MODEL
TARGET_UNDERSTANDING_PROVIDER = DEFAULT_UNDERSTANDING_PROVIDER
TARGET_UNDERSTANDING_MODEL = DEFAULT_UNDERSTANDING_MODEL


@dataclass
class CollectionPolicy:
    viral_like_floor: int = 10000
    min_duration_seconds: int = 20
    max_duration_seconds: int = 300
    super_like_threshold: int = 100000
    max_search_pages: int = 3
    page_size: int = 10
    stop_after_nonviral_pages: int = 2
    max_materials_per_iteration: int = 5


class CollectionTaskOrchestrator:
    def __init__(
        self,
        store: Store,
        *,
        channels_registry_factory: Callable[..., Any] | None = None,
        channels_session_controller_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.store = store
        self._channels_registry_factory = (
            channels_registry_factory or build_channels_collection_registry
        )
        self._channels_session_controller_factory = (
            channels_session_controller_factory or ChannelsAcquisitionController
        )

    def run_keyword_task(
        self,
        *,
        topic: str,
        target_count: int,
        policy: CollectionPolicy | None = None,
        tool_provider: str = "mock",
        transcription_provider: str = "aliyun",
        allow_paid_fallback: bool = False,
        keywords: list[str] | None = None,
        related_keywords: list[str] | None = None,
        role_id: str | None = None,
        understanding_provider: str = TARGET_UNDERSTANDING_PROVIDER,
        understanding_model: str = TARGET_UNDERSTANDING_MODEL,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        policy = policy or CollectionPolicy()
        topic = topic.strip()
        if not topic:
            raise ValueError("--topic is required")
        if target_count < 1:
            raise ValueError("--target-count must be >= 1")
        role_profile = self.store.get_ip_role(role_id) if role_id else None
        if role_id and role_profile is None:
            raise KeyError(f"role not found: {role_id}")
        if role_profile and (
            role_profile.get("confirmation_status") != "confirmed" or bool(role_profile.get("needs_reconfirm"))
        ):
            raise ValueError(
                f"role {role_profile['id']} is {role_profile.get('confirmation_status')}; "
                "confirm the IP role before using it in a formal collection task"
            )
        command = f"collect task keyword --topic {topic} --target-count {target_count}"
        parsed = {
            "entrypoint": "keyword",
            "topic": topic,
            "target_count": target_count,
            "tool_provider": tool_provider,
            "transcription_provider": transcription_provider,
            "allow_paid_fallback": allow_paid_fallback,
            "role_id": role_id,
            "keywords": _unique_strings([topic, *(keywords or [])]),
            "related_keywords": _unique_strings(related_keywords or []),
            "policy": asdict(policy),
            "target_understanding": _target_understanding(provider=understanding_provider, model=understanding_model),
        }
        if tool_provider == "wechat_channels_remote" and _orchestration_schema_ready(
            self.store
        ):
            return self._run_durable_channels_keyword_task(
                parsed=parsed,
                policy=policy,
                role_profile=role_profile,
                task_id=task_id,
            )
        if task_id is None:
            task_id = self.store.create_collection_task(
                command=command,
                target_scope="keyword",
                target_count_per_role=target_count,
                topic=topic,
                parsed=parsed,
            )
        task_record = self.store.get_collection_task(task_id)
        if task_record is None:
            raise KeyError(f"collection task not found: {task_id}")
        previous_summary = (
            task_record.get("summary") if isinstance(task_record.get("summary"), dict) else {}
        )
        current_report = self.build_task_report(task_id)
        if _task_goal_count(current_report) >= target_count:
            completed_summary = {
                **previous_summary,
                "entrypoint": "keyword",
                "target_count": target_count,
                "goal_metric": current_report["goal_metric"],
                "qualified_formal_base_count": current_report["qualified_formal_base_count"],
                "remaining_count": 0,
                "goal_satisfied": True,
                "pause_reason": None,
            }
            self.store.finish_collection_task(task_id, "completed", completed_summary)
            return self.build_task_report(task_id)
        if (
            role_id
            and current_report["runs"]
            and current_report["inventory_handoff"]["pending_review_count"] > 0
        ):
            checkpoint = {
                **previous_summary,
                "entrypoint": "keyword",
                "target_count": target_count,
                "goal_metric": current_report["goal_metric"],
                "qualified_formal_base_count": current_report["qualified_formal_base_count"],
                "remaining_count": current_report["remaining_count"],
                "goal_satisfied": False,
                "pause_reason": "semantic_review_required",
            }
            self.store.update_collection_task_progress(task_id, "awaiting_review", checkpoint)
            return self.build_task_report(task_id)
        if tool_provider == "mock":
            tools = build_mock_source_registry()
        elif tool_provider == "wechat_channels_remote":
            tools = build_channels_collection_registry(
                transcription_provider_name=transcription_provider,
            )
        else:
            provider = build_collection_provider(
                tool_provider,
                transcription_provider_name=transcription_provider,
                allow_paid_fallback=allow_paid_fallback,
            )
            tools = build_douyin_registry(provider, include_user_post_tools=False)
        runner = TopicCollectionRunner(tools, self.store)
        exhausted_keywords = _unique_strings(previous_summary.get("exhausted_keywords") or [])
        pending_keywords = _unique_strings(previous_summary.get("pending_keywords") or [])
        queue = _unique_strings(
            [
                *pending_keywords,
                topic,
                *(keywords or []),
                *(related_keywords or []),
                *_role_collection_keywords(role_profile, topic),
            ]
        )
        queue = [keyword for keyword in queue if keyword not in exhausted_keywords]
        keyword_errors: list[dict[str, str]] = list(previous_summary.get("keyword_errors") or [])
        run_summaries: list[dict[str, Any]] = []
        error: str | None = None
        iteration_limit = 1 if tool_provider == "wechat_channels_remote" else max(len(queue), 1)
        iterations = 0
        try:
            while _task_goal_count(self.build_task_report(task_id)) < target_count and queue:
                if iterations >= iteration_limit:
                    break
                iterations += 1
                keyword = queue.pop(0)
                if keyword in exhausted_keywords:
                    continue
                remaining = max(1, target_count - _task_goal_count(self.build_task_report(task_id)))
                if tool_provider == "wechat_channels_remote":
                    remaining = min(remaining, max(1, policy.max_materials_per_iteration))
                try:
                    result = runner.run(
                        CollectionConfig(
                            topic=keyword,
                            target_count=remaining,
                            like_floor=policy.viral_like_floor,
                            super_like_threshold=policy.super_like_threshold,
                            min_duration_seconds=policy.min_duration_seconds,
                            max_duration_seconds=policy.max_duration_seconds,
                            tool_provider=tool_provider,
                            max_search_pages=policy.max_search_pages,
                            page_size=policy.page_size,
                            task_id=task_id,
                            role_id=role_id,
                            role_profile=role_profile,
                            search_keywords=[keyword],
                            understanding_provider=understanding_provider,
                            understanding_model=understanding_model,
                        )
                    )
                except Exception as exc:
                    exhausted_keywords.append(keyword)
                    keyword_errors.append({"keyword": keyword, "error": str(exc)})
                    continue
                exhausted_keywords.append(keyword)
                run_summaries.append(result.to_dict())
                report = self.build_task_report(task_id)
                queue.extend(
                    keyword
                    for keyword in _next_keywords_from_report(report)
                    if _keyword_in_topic_scope(keyword, topic, role_profile)
                    if keyword not in exhausted_keywords and keyword not in queue
                )
            report = self.build_task_report(task_id)
            saved_count = _task_saved_count(report)
            goal_count = _task_goal_count(report)
            goal_satisfied = goal_count >= target_count
            pending_review_count = int(report["inventory_handoff"]["pending_review_count"] or 0)
            if goal_satisfied:
                status = "completed"
            elif pending_review_count > 0:
                status = "awaiting_review"
            elif queue:
                status = "ready_for_search"
            elif not run_summaries and keyword_errors and saved_count == 0:
                status = "failed"
            else:
                status = "awaiting_strategy"
            summary = {
                "entrypoint": "keyword",
                "target_count": target_count,
                "goal_metric": report["goal_metric"],
                "qualified_formal_base_count": report["qualified_formal_base_count"],
                "saved_count": saved_count,
                "remaining_count": max(target_count - goal_count, 0),
                "exhausted_keywords": exhausted_keywords,
                "pending_keywords": queue,
                "keyword_errors": keyword_errors,
                "runs": run_summaries,
                "goal_satisfied": goal_satisfied,
                "pause_reason": (
                    "semantic_review_required"
                    if status == "awaiting_review"
                    else "strategy_decision_required"
                    if status == "awaiting_strategy"
                    else None
                ),
                "understanding": report["understanding_summary"],
            }
            if status in {"completed", "failed"}:
                self.store.finish_collection_task(task_id, status, summary)
            else:
                self.store.update_collection_task_progress(task_id, status, summary)
            return self.build_task_report(task_id)
        except Exception as exc:
            error = str(exc)
            self.store.finish_collection_task(
                task_id,
                "failed",
                {"entrypoint": "keyword", "runs": run_summaries, "keyword_errors": keyword_errors, "error": error},
                error=error,
            )
            raise

    def _run_durable_channels_keyword_task(
        self,
        *,
        parsed: dict[str, Any],
        policy: CollectionPolicy,
        role_profile: dict[str, Any] | None,
        task_id: str | None,
    ) -> dict[str, Any]:
        topic = str(parsed["topic"])
        target_count = int(parsed["target_count"])
        role_id = str(parsed.get("role_id") or "") or None
        if task_id is None:
            task_id = self.store.create_collection_task(
                command=f"collect task keyword --topic {topic} --target-count {target_count}",
                target_scope="keyword",
                target_count_per_role=target_count,
                topic=topic,
                parsed=parsed,
                status=CollectionTaskStatus.READY_FOR_SEARCH.value,
            )
            if role_id:
                self.store.upsert_collection_task_role(
                    task_id=task_id,
                    role_id=role_id,
                    target_count=target_count,
                    status=CollectionTaskStatus.READY_FOR_SEARCH.value,
                )
            planner = self._channels_action_engine(task_id=task_id, live=False)
            parsed_keywords = _unique_strings(parsed.get("keywords") or [])
            queue = _unique_strings(
                [
                    *[keyword for keyword in parsed_keywords if keyword != topic],
                    *_role_collection_keywords(role_profile, topic),
                    *(parsed.get("related_keywords") or []),
                    topic,
                ]
            )
            if not queue:
                queue = [topic]
            for index, keyword in enumerate(queue):
                if index == 0:
                    planner.plan_keyword(
                        task_id=task_id,
                        keyword=keyword,
                        max_pages=min(policy.max_search_pages, 5),
                        page_size=policy.page_size,
                        role_id=role_id,
                        reason="initial task keyword",
                    )
                else:
                    planner.plan_related_keyword(
                        task_id=task_id,
                        keyword=keyword,
                        origin_keyword=queue[0],
                        max_pages=min(policy.max_search_pages, 5),
                        page_size=policy.page_size,
                        role_id=role_id,
                        reason="initial related keyword",
                    )
        return self.step_channels_task(task_id)

    def plan_channels_keyword_action(
        self,
        *,
        task_id: str,
        keyword: str,
        continue_frontier: bool = False,
        origin_keyword: str | None = None,
        max_pages: int = 1,
        page_size: int = 20,
        strategy_iteration: int = 0,
        reason: str = "strategy decision",
    ) -> dict[str, Any]:
        task = self._require_durable_channels_task(task_id)
        role_id = str((task.get("parsed") or {}).get("role_id") or "") or None
        engine = self._channels_action_engine(task_id=task_id, live=False)
        if continue_frontier:
            action = engine.plan_continue_keyword(
                task_id=task_id,
                keyword=keyword,
                max_pages=max_pages,
                page_size=page_size,
                role_id=role_id,
                strategy_iteration=strategy_iteration,
                reason=reason,
            )
        elif origin_keyword:
            action = engine.plan_related_keyword(
                task_id=task_id,
                keyword=keyword,
                origin_keyword=origin_keyword,
                max_pages=max_pages,
                page_size=page_size,
                role_id=role_id,
                strategy_iteration=strategy_iteration,
                reason=reason,
            )
        else:
            action = engine.plan_keyword(
                task_id=task_id,
                keyword=keyword,
                max_pages=max_pages,
                page_size=page_size,
                role_id=role_id,
                strategy_iteration=strategy_iteration,
                reason=reason,
            )
        current = self.store.get_collection_task(task_id)
        assert current is not None
        if current["status"] in {
            CollectionTaskStatus.AWAITING_STRATEGY.value,
            CollectionTaskStatus.BLOCKED.value,
        }:
            self.store.compare_and_swap_collection_task(
                task_id,
                expected_state_version=int(current["state_version"]),
                status=CollectionTaskStatus.READY_FOR_SEARCH.value,
                event_type="strategy_action_planned",
                action_id=action["id"],
                event_payload={"action_type": action["action_type"]},
            )
        return action

    def step_channels_task(self, task_id: str) -> dict[str, Any]:
        task = self._require_durable_channels_task(task_id)
        if task["status"] in {
            CollectionTaskStatus.AWAITING_REVIEW.value,
            CollectionTaskStatus.COMPLETING.value,
            CollectionTaskStatus.CANCELLING.value,
            CollectionTaskStatus.CLEANUP_REQUIRED.value,
            CollectionTaskStatus.COMPLETED.value,
            CollectionTaskStatus.CANCELLED.value,
            CollectionTaskStatus.FAILED.value,
        }:
            return self.build_task_report(task_id)
        if task["status"] in {
            CollectionTaskStatus.AWAITING_STRATEGY.value,
            CollectionTaskStatus.BLOCKED.value,
        }:
            planned = [
                action
                for action in self.store.list_collection_task_actions(task_id=task_id)
                if action["status"]
                in {
                    CollectionActionStatus.PLANNED.value,
                    CollectionActionStatus.INTERRUPTED.value,
                }
            ]
            if not planned:
                return self.build_task_report(task_id)
            task = self.store.compare_and_swap_collection_task(
                task_id,
                expected_state_version=int(task["state_version"]),
                status=CollectionTaskStatus.READY_FOR_SEARCH.value,
                event_type="planned_action_queue_resumed",
            )
        engine = self._channels_action_engine(task_id=task_id, live=True)
        outcome = engine.execute_one(task_id=task_id)
        if outcome is None:
            return self.build_task_report(task_id)
        if outcome.status == CollectionActionStatus.SUCCEEDED.value:
            try:
                self._materialize_channels_action(task_id=task_id, action_id=outcome.action_id)
            except Exception as exc:
                current = self.store.get_collection_task(task_id)
                if current and current["status"] == CollectionTaskStatus.ACQUIRING.value:
                    self.store.compare_and_swap_collection_task(
                        task_id,
                        expected_state_version=int(current["state_version"]),
                        status=CollectionTaskStatus.BLOCKED.value,
                        error=str(exc),
                        event_type="action_materialization_failed",
                        action_id=outcome.action_id,
                        event_payload={"error_type": type(exc).__name__, "message": str(exc)},
                    )
                raise
        report = self.build_task_report(task_id)
        proposal = engine.propose_next_task_state(
            task_id=task_id,
            pending_review_count=int(
                report["inventory_handoff"]["pending_review_count"] or 0
            ),
        )
        current = self.store.get_collection_task(task_id)
        assert current is not None
        if current["status"] != proposal.status:
            self.store.compare_and_swap_collection_task(
                task_id,
                expected_state_version=int(current["state_version"]),
                status=proposal.status,
                event_type="bounded_action_reconciled",
                action_id=outcome.action_id,
                event_payload={**proposal.to_dict(), "outcome_code": outcome.code},
            )
        return self.build_task_report(task_id)

    def _materialize_channels_action(self, *, task_id: str, action_id: str) -> None:
        task = self._require_durable_channels_task(task_id)
        action = self.store.get_collection_task_action(action_id)
        if action is None:
            raise KeyError(f"collection task action not found: {action_id}")
        runs = [
            run
            for run in self.store.list_collection_runs(task_id=task_id)
            if run.get("action_id") == action_id
        ]
        if not runs:
            return
        run = runs[-1]
        candidates = [
            candidate
            for candidate in self.store.list_collection_candidates(task_id=task_id)
            if candidate.get("run_id") == run["id"]
        ]
        if not candidates:
            self.store.finish_collection_run(
                run["id"],
                "partial",
                {"action_id": action_id, "saved_count": 0, "candidate_count": 0},
            )
            return
        parsed = task.get("parsed") if isinstance(task.get("parsed"), dict) else {}
        policy = CollectionPolicy(
            **{**asdict(CollectionPolicy()), **(parsed.get("policy") or {})}
        )
        role_id = str(parsed.get("role_id") or "") or None
        role_profile = self.store.get_ip_role(role_id) if role_id else None
        before = self.build_task_report(task_id)
        remaining = max(1, int(before.get("remaining_count") or 1))
        target_count = min(remaining, max(1, policy.max_materials_per_iteration))
        registry = self._channels_registry(task_id)
        TopicCollectionRunner(registry, self.store).run(
            CollectionConfig(
                topic=str(action["input"].get("keyword") or task.get("topic") or "channels"),
                target_count=target_count,
                like_floor=policy.viral_like_floor,
                super_like_threshold=policy.super_like_threshold,
                min_duration_seconds=policy.min_duration_seconds,
                max_duration_seconds=policy.max_duration_seconds,
                tool_provider="wechat_channels_remote",
                max_search_pages=1,
                page_size=policy.page_size,
                task_id=task_id,
                role_id=role_id,
                role_profile=role_profile,
                search_keywords=[str(action["input"].get("keyword") or "")],
                understanding_provider=str(
                    (parsed.get("target_understanding") or {}).get("provider")
                    or TARGET_UNDERSTANDING_PROVIDER
                ),
                understanding_model=str(
                    (parsed.get("target_understanding") or {}).get("model")
                    or TARGET_UNDERSTANDING_MODEL
                ),
                run_id=str(run["id"]),
                preloaded_candidates=[
                    {"source_package": dict(candidate["source_package"])}
                    for candidate in candidates
                ],
                preloaded_traversal=dict(action.get("result", {}).get("paging") or {}),
            )
        )

    def _channels_action_engine(
        self,
        *,
        task_id: str,
        live: bool,
    ) -> CollectionTaskActionEngine:
        if live:
            return CollectionTaskActionEngine(
                self.store,
                lease_owner="mac-codex-channels",
                registry=self._channels_registry(task_id),
            )
        return CollectionTaskActionEngine(
            self.store,
            lease_owner="mac-codex-channels-plan",
            executor=lambda _action_type, _arguments: {},
        )

    def _channels_registry(self, task_id: str) -> Any:
        controller = self._channels_session_controller_factory(self.store, task_id)
        return self._channels_registry_factory(
            transcription_provider_name="aliyun",
            session_guard=controller,
        )

    def _require_durable_channels_task(self, task_id: str) -> dict[str, Any]:
        if not _orchestration_schema_ready(self.store):
            raise RuntimeError(
                "collection task orchestration schema is not installed; run "
                "mcn db migrate-collection-task-orchestration-v1"
            )
        task = self.store.get_collection_task(task_id)
        if task is None:
            raise KeyError(f"collection task not found: {task_id}")
        parsed = task.get("parsed") if isinstance(task.get("parsed"), dict) else {}
        if parsed.get("tool_provider") != "wechat_channels_remote":
            raise ValueError(f"collection task is not a Channels task: {task_id}")
        return task

    def complete_channels_task(self, task_id: str) -> dict[str, Any]:
        task = self._require_durable_channels_task(task_id)
        if task["status"] == CollectionTaskStatus.COMPLETED.value:
            return self.build_task_report(task_id)
        if task["status"] != CollectionTaskStatus.COMPLETING.value:
            raise ValueError(
                f"collection task is not ready for completion: {task_id} ({task['status']})"
            )
        return self._cleanup_and_finalize_channels_task(
            task_id=task_id,
            terminal_status=CollectionTaskStatus.COMPLETED,
            cleanup_reason="task_completed",
        )

    def cancel_channels_task(self, task_id: str, *, reason: str) -> dict[str, Any]:
        task = self._require_durable_channels_task(task_id)
        if task["status"] == CollectionTaskStatus.CANCELLED.value:
            return self.build_task_report(task_id)
        if task["status"] in {
            CollectionTaskStatus.COMPLETED.value,
            CollectionTaskStatus.FAILED.value,
        }:
            raise ValueError(
                f"terminal collection task cannot be cancelled: {task_id} ({task['status']})"
            )
        if task["status"] != CollectionTaskStatus.CANCELLING.value:
            summary = {
                **(task.get("summary") if isinstance(task.get("summary"), dict) else {}),
                "terminal_intent": "cancel",
                "cancel_reason": str(reason or "operator_request"),
            }
            task = self.store.compare_and_swap_collection_task(
                task_id,
                expected_state_version=int(task["state_version"]),
                status=CollectionTaskStatus.CANCELLING.value,
                summary=summary,
                event_type="task_cancellation_requested",
                event_payload={"reason": str(reason or "operator_request")},
            )
        for action in self.store.list_collection_task_actions(task_id=task_id):
            if action["status"] in {
                CollectionActionStatus.PLANNED.value,
                CollectionActionStatus.CLAIMED.value,
                CollectionActionStatus.RUNNING.value,
                CollectionActionStatus.INTERRUPTED.value,
            }:
                self.store.update_collection_task_action_status(
                    action["id"],
                    status=CollectionActionStatus.CANCELLED.value,
                    error={"reason": str(reason or "operator_request")},
                )
        return self._cleanup_and_finalize_channels_task(
            task_id=task_id,
            terminal_status=CollectionTaskStatus.CANCELLED,
            cleanup_reason="task_cancelled",
        )

    def recover_channels_task_cleanup(self, task_id: str) -> dict[str, Any]:
        task = self._require_durable_channels_task(task_id)
        if task["status"] != CollectionTaskStatus.CLEANUP_REQUIRED.value:
            raise ValueError(
                f"collection task does not require cleanup recovery: {task_id} ({task['status']})"
            )
        summary = task.get("summary") if isinstance(task.get("summary"), dict) else {}
        intent = str(summary.get("terminal_intent") or "complete")
        target = (
            CollectionTaskStatus.CANCELLING
            if intent == "cancel"
            else CollectionTaskStatus.COMPLETING
        )
        task = self.store.compare_and_swap_collection_task(
            task_id,
            expected_state_version=int(task["state_version"]),
            status=target.value,
            event_type="cleanup_recovery_started",
            event_payload={"terminal_intent": intent},
        )
        if target is CollectionTaskStatus.CANCELLING:
            return self.cancel_channels_task(task_id, reason="cleanup_recovery")
        return self.complete_channels_task(task_id)

    def _cleanup_and_finalize_channels_task(
        self,
        *,
        task_id: str,
        terminal_status: CollectionTaskStatus,
        cleanup_reason: str,
    ) -> dict[str, Any]:
        controller = self._channels_session_controller_factory(self.store, task_id)
        try:
            controller.close(reason=cleanup_reason)
        except Exception as exc:
            current = self.store.get_collection_task(task_id)
            assert current is not None
            if current["status"] in {
                CollectionTaskStatus.COMPLETING.value,
                CollectionTaskStatus.CANCELLING.value,
            }:
                summary = {
                    **(
                        current.get("summary")
                        if isinstance(current.get("summary"), dict)
                        else {}
                    ),
                    "terminal_intent": (
                        "cancel"
                        if terminal_status is CollectionTaskStatus.CANCELLED
                        else "complete"
                    ),
                    "cleanup_error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
                self.store.compare_and_swap_collection_task(
                    task_id,
                    expected_state_version=int(current["state_version"]),
                    status=CollectionTaskStatus.CLEANUP_REQUIRED.value,
                    summary=summary,
                    error=str(exc),
                    event_type="task_cleanup_failed",
                    event_payload={"error_type": type(exc).__name__, "message": str(exc)},
                )
            raise
        current = self.store.get_collection_task(task_id)
        assert current is not None
        self.store.compare_and_swap_collection_task(
            task_id,
            expected_state_version=int(current["state_version"]),
            status=terminal_status.value,
            error=None,
            completed_at=datetime.now(UTC).isoformat(),
            event_type="task_cleanup_verified",
            event_payload={"terminal_status": terminal_status.value},
        )
        return self.build_task_report(task_id)

    def run_author_task(
        self,
        *,
        name: str | None = None,
        sec_uid: str | None = None,
        policy: CollectionPolicy | None = None,
        like_floor: int | None = None,
        materialize_top: int = 0,
        max_pages: int = 0,
        sort_type: int = 1,
        skip_expand: bool = False,
        no_cache: bool = False,
        refresh_existing_understanding: bool = False,
        understanding_provider: str = TARGET_UNDERSTANDING_PROVIDER,
        understanding_model: str = TARGET_UNDERSTANDING_MODEL,
        task_id: str | None = None,
        finish_task: bool = True,
        data_provider: str = "direct",
        transcription_provider: str = "aliyun",
        allow_paid_fallback: bool = False,
    ) -> dict[str, Any]:
        policy = policy or CollectionPolicy()
        floor = like_floor if like_floor is not None else policy.viral_like_floor
        label = name or sec_uid or "douyin_author"
        parsed = {
            "entrypoint": "author",
            "name": name,
            "sec_uid": sec_uid,
            "like_floor": floor,
            "materialize_top": materialize_top,
            "max_pages": max_pages,
            "sort_type": sort_type,
            "skip_expand": skip_expand,
            "data_provider": data_provider,
            "transcription_provider": transcription_provider,
            "allow_paid_fallback": allow_paid_fallback,
            "policy": asdict(policy),
            "target_understanding": _target_understanding(provider=understanding_provider, model=understanding_model),
        }
        if task_id is None:
            task_id = self.store.create_collection_task(
                command=f"collect task author --name {label} --like-floor {floor}",
                target_scope="author",
                target_count_per_role=materialize_top,
                topic=f"{label} 爆款文案",
                parsed=parsed,
            )
        run_id = self.store.create_collection_run(
            task_id=task_id,
            role_id=None,
            topic=f"{label} 爆款文案",
            target_count=materialize_top,
            like_floor=floor,
            super_like_threshold=policy.super_like_threshold,
            tool_provider=f"{data_provider}_author_task",
        )
        materialized: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        expand_summary: dict[str, Any] = {"skipped": skip_expand}
        try:
            client: DouyinProvider | None = None
            author = self._resolve_author(sec_uid=sec_uid, name=name)
            if author is None and sec_uid:
                stored_sec_uid = self.store.upsert_douyin_author(
                    {
                        "sec_uid": sec_uid,
                        "nickname": name or sec_uid,
                        "profile_url": f"https://www.douyin.com/user/{sec_uid}",
                    }
                )
                author = self.store.get_douyin_author(stored_sec_uid)
            if author is None and skip_expand:
                raise KeyError(f"douyin author not found: {label}")
            if author is None:
                raise KeyError(
                    f"douyin author not found locally: {label}; resolve a verified sec_uid from video detail first"
                )
            if not skip_expand:
                client = client or self._build_collection_provider(
                    data_provider=data_provider,
                    transcription_provider=transcription_provider,
                    allow_paid_fallback=allow_paid_fallback,
                )
                expand_summary = self._expand_author_videos(
                    client,
                    run_id=run_id,
                    author=author,
                    like_floor=floor,
                    min_duration_seconds=policy.min_duration_seconds,
                    max_duration_seconds=policy.max_duration_seconds,
                    max_pages=max_pages,
                    sort_type=sort_type,
                    stop_after_nonviral_pages=policy.stop_after_nonviral_pages,
                    use_cache=not no_cache,
                )
            materialized, skipped = self._materialize_author_videos(
                run_id=run_id,
                task_id=task_id,
                author=author,
                like_floor=floor,
                min_duration_seconds=policy.min_duration_seconds,
                max_duration_seconds=policy.max_duration_seconds,
                materialize_top=materialize_top,
                client=client,
                use_cache=not no_cache,
                data_provider=data_provider,
                transcription_provider=transcription_provider,
                allow_paid_fallback=allow_paid_fallback,
                refresh_existing_understanding=refresh_existing_understanding,
                understanding_provider=understanding_provider,
                understanding_model=understanding_model,
            )
            run_status = _workflow_goal_status(len(materialized), materialize_top)
            self.store.finish_collection_run(
                run_id,
                run_status,
                {
                    "entrypoint": "author",
                    "author": _author_summary(author),
                    "expand": expand_summary,
                    "materialized": materialized,
                    "skipped": skipped,
                    "goal_satisfied": materialize_top <= 0 or len(materialized) >= materialize_top,
                },
            )
            if finish_task:
                report = self.build_task_report(task_id)
                self.store.finish_collection_task(
                    task_id,
                    run_status,
                    {
                        "entrypoint": "author",
                        "author": _author_summary(author),
                        "materialized_count": len(materialized),
                        "skipped_count": len(skipped),
                        "goal_satisfied": materialize_top <= 0 or len(materialized) >= materialize_top,
                        "understanding": report["understanding_summary"],
                    },
                )
            return self.build_task_report(task_id)
        except Exception as exc:
            self.store.finish_collection_run(
                run_id,
                "failed",
                {"entrypoint": "author", "materialized": materialized, "skipped": skipped, "expand": expand_summary},
                error=str(exc),
            )
            if finish_task:
                self.store.finish_collection_task(
                    task_id,
                    "failed",
                    {"entrypoint": "author", "materialized": materialized, "skipped": skipped, "error": str(exc)},
                    error=str(exc),
                )
            raise

    def run_discovered_authors_task(
        self,
        *,
        min_appearances: int = 2,
        top_authors: int = 10,
        like_floor: int | None = None,
        materialize_top: int = 0,
        max_pages: int = 0,
        sort_type: int = 1,
        skip_expand: bool = False,
        no_cache: bool = False,
        dry_run: bool = False,
        understanding_provider: str = TARGET_UNDERSTANDING_PROVIDER,
        understanding_model: str = TARGET_UNDERSTANDING_MODEL,
        policy: CollectionPolicy | None = None,
        task_id: str | None = None,
        data_provider: str = "direct",
        transcription_provider: str = "aliyun",
        allow_paid_fallback: bool = False,
    ) -> dict[str, Any]:
        policy = policy or CollectionPolicy()
        floor = like_floor if like_floor is not None else policy.viral_like_floor
        discovered = discover_source_authors(self.store, min_appearances=min_appearances)[:top_authors]
        parsed = {
            "entrypoint": "discovered_authors",
            "min_appearances": min_appearances,
            "top_authors": top_authors,
            "like_floor": floor,
            "materialize_top": materialize_top,
            "max_pages": max_pages,
            "sort_type": sort_type,
            "skip_expand": skip_expand,
            "dry_run": dry_run,
            "data_provider": data_provider,
            "transcription_provider": transcription_provider,
            "allow_paid_fallback": allow_paid_fallback,
            "authors": discovered,
            "policy": asdict(policy),
            "target_understanding": _target_understanding(provider=understanding_provider, model=understanding_model),
        }
        if task_id is None:
            task_id = self.store.create_collection_task(
                command=f"collect task discover-authors --min-appearances {min_appearances} --like-floor {floor}",
                target_scope="discovered_authors",
                target_count_per_role=materialize_top,
                topic="discovered source authors",
                parsed=parsed,
            )
        if dry_run:
            self.store.finish_collection_task(
                task_id,
                "completed",
                {"entrypoint": "discovered_authors", "authors": discovered, "dry_run": True},
            )
            return self.build_task_report(task_id)
        author_results: list[dict[str, Any]] = []
        try:
            for author in discovered:
                report = self.run_author_task(
                    sec_uid=author.get("author_sec_uid"),
                    name=author.get("author_name"),
                    policy=policy,
                    like_floor=floor,
                    materialize_top=materialize_top,
                    max_pages=max_pages,
                    sort_type=sort_type,
                    skip_expand=skip_expand,
                    no_cache=no_cache,
                    understanding_provider=understanding_provider,
                    understanding_model=understanding_model,
                    task_id=task_id,
                    finish_task=False,
                    data_provider=data_provider,
                    transcription_provider=transcription_provider,
                    allow_paid_fallback=allow_paid_fallback,
                )
                author_results.append(
                    {
                        "author_sec_uid": author.get("author_sec_uid"),
                        "author_name": author.get("author_name"),
                        "saved_count": _task_saved_count(report),
                    }
                )
            report = self.build_task_report(task_id)
            expected_count = materialize_top * len(discovered) if materialize_top > 0 else 0
            task_status = _workflow_goal_status(_task_saved_count(report), expected_count)
            if not discovered:
                task_status = "empty"
            self.store.finish_collection_task(
                task_id,
                task_status,
                {
                    "entrypoint": "discovered_authors",
                    "authors": discovered,
                    "author_results": author_results,
                    "goal_satisfied": bool(discovered) and (
                        expected_count <= 0 or _task_saved_count(report) >= expected_count
                    ),
                    "understanding": report["understanding_summary"],
                },
            )
            return self.build_task_report(task_id)
        except Exception as exc:
            self.store.finish_collection_task(
                task_id,
                "failed",
                {"entrypoint": "discovered_authors", "authors": discovered, "author_results": author_results, "error": str(exc)},
                error=str(exc),
            )
            raise

    def resume_task(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_collection_task(task_id)
        if not task:
            raise KeyError(f"collection task not found: {task_id}")
        parsed = task.get("parsed") or {}
        policy = CollectionPolicy(**{**asdict(CollectionPolicy()), **(parsed.get("policy") or {})})
        entrypoint = parsed.get("entrypoint") or task.get("target_scope")
        if entrypoint == "keyword":
            if (
                _resume_data_provider(parsed.get("tool_provider"), default="mock")
                == "wechat_channels_remote"
                and _orchestration_schema_ready(self.store)
            ):
                if task["status"] == CollectionTaskStatus.COMPLETING.value:
                    return self.complete_channels_task(task_id)
                if task["status"] == CollectionTaskStatus.CLEANUP_REQUIRED.value:
                    return self.recover_channels_task_cleanup(task_id)
                if task["status"] == CollectionTaskStatus.CANCELLING.value:
                    return self.cancel_channels_task(task_id, reason="resume_cancellation")
                return self.step_channels_task(task_id)
            return self.run_keyword_task(
                topic=str(parsed.get("topic") or task.get("topic") or ""),
                target_count=int(parsed.get("target_count") or task.get("target_count_per_role") or 1),
                policy=policy,
                tool_provider=_resume_data_provider(parsed.get("tool_provider"), default="mock"),
                keywords=list(parsed.get("keywords") or []),
                related_keywords=list(parsed.get("related_keywords") or []),
                role_id=parsed.get("role_id"),
                understanding_provider=str((parsed.get("target_understanding") or {}).get("provider") or TARGET_UNDERSTANDING_PROVIDER),
                understanding_model=str((parsed.get("target_understanding") or {}).get("model") or TARGET_UNDERSTANDING_MODEL),
                task_id=task_id,
                transcription_provider=_resume_transcription_provider(parsed.get("transcription_provider")),
                allow_paid_fallback=False,
            )
        if entrypoint == "author":
            return self.run_author_task(
                name=parsed.get("name"),
                sec_uid=parsed.get("sec_uid"),
                policy=policy,
                like_floor=parsed.get("like_floor"),
                materialize_top=int(parsed.get("materialize_top") or 0),
                max_pages=int(parsed.get("max_pages") or 0),
                sort_type=int(parsed.get("sort_type") or 1),
                skip_expand=bool(parsed.get("skip_expand")),
                understanding_provider=str((parsed.get("target_understanding") or {}).get("provider") or TARGET_UNDERSTANDING_PROVIDER),
                understanding_model=str((parsed.get("target_understanding") or {}).get("model") or TARGET_UNDERSTANDING_MODEL),
                task_id=task_id,
                data_provider=_resume_data_provider(parsed.get("data_provider"), default="direct"),
                transcription_provider=_resume_transcription_provider(parsed.get("transcription_provider")),
                allow_paid_fallback=False,
            )
        if entrypoint == "discovered_authors":
            return self.run_discovered_authors_task(
                min_appearances=int(parsed.get("min_appearances") or 2),
                top_authors=int(parsed.get("top_authors") or 10),
                like_floor=parsed.get("like_floor"),
                materialize_top=int(parsed.get("materialize_top") or 0),
                max_pages=int(parsed.get("max_pages") or 0),
                sort_type=int(parsed.get("sort_type") or 1),
                skip_expand=bool(parsed.get("skip_expand")),
                dry_run=bool(parsed.get("dry_run")),
                understanding_provider=str((parsed.get("target_understanding") or {}).get("provider") or TARGET_UNDERSTANDING_PROVIDER),
                understanding_model=str((parsed.get("target_understanding") or {}).get("model") or TARGET_UNDERSTANDING_MODEL),
                policy=policy,
                task_id=task_id,
                data_provider=_resume_data_provider(parsed.get("data_provider"), default="direct"),
                transcription_provider=_resume_transcription_provider(parsed.get("transcription_provider")),
                allow_paid_fallback=False,
            )
        raise ValueError(f"unsupported task entrypoint: {entrypoint}")

    def build_task_report(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_collection_task(task_id)
        if not task:
            raise KeyError(f"collection task not found: {task_id}")
        runs = self.store.list_collection_runs(task_id=task_id)
        candidates = self.store.list_collection_candidates(task_id=task_id)
        created_materials = self.store.list_collected_materials(task_id=task_id)
        material_by_id = {material["id"]: material for material in created_materials}
        existing_reused: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate.get("status") != "existing_reused" or not candidate.get("material_id"):
                continue
            material = self.store.get_collected_material(str(candidate["material_id"]))
            if material and material["id"] not in material_by_id:
                material_by_id[material["id"]] = material
                existing_reused.append(material)
        for run in runs:
            summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
            for item in summary.get("materialized") or []:
                if not isinstance(item, dict) or not str(item.get("status") or "").startswith("existing_"):
                    continue
                material_id = item.get("material_id")
                if not material_id or material_id in material_by_id:
                    continue
                material = self.store.get_collected_material(str(material_id))
                if material:
                    material_by_id[material["id"]] = material
                    existing_reused.append(material)
        saved_materials = list(material_by_id.values())
        skipped = [
            candidate
            for candidate in candidates
            if candidate.get("status") in {"rejected", "below_threshold", "skipped"}
        ]
        source_authors = discover_source_authors_from_records(saved_materials, candidates)
        if not source_authors and isinstance((task.get("parsed") or {}).get("authors"), list):
            source_authors = list((task.get("parsed") or {}).get("authors") or [])
        parsed = task.get("parsed") if isinstance(task.get("parsed"), dict) else {}
        role_ids = _unique_strings(
            [
                str(parsed.get("role_id") or ""),
                *[
                    str(item.get("role_id") or "")
                    for item in self.store.collection_task_summary(task_id).get("roles", [])
                ],
            ]
        )
        pending_by_role: list[dict[str, Any]] = []
        goal_by_role: list[dict[str, Any]] = []
        inventory_schema_ready = True
        task_source_work_ids = {
            str(material.get("source_work_id") or "")
            for material in saved_materials
            if material.get("source_work_id")
        }
        for role_id in role_ids:
            try:
                inventory = self.store.list_material_inventory(role_id=role_id, include_used=True)
            except RuntimeError as exc:
                if "migrate-material-inventory-v1" not in str(exc):
                    raise
                inventory_schema_ready = False
                inventory = []
            reviewed_source_work_ids = {
                str(item.get("source_work_id") or "")
                for item in inventory
                if item.get("review_status") in {"reviewed", "rejected"}
            }
            try:
                durable_reviews = self.store.list_collection_material_reviews(
                    task_id=task_id,
                    role_id=role_id,
                )
            except RuntimeError as exc:
                if "orchestration schema is not installed" not in str(exc):
                    raise
                durable_reviews = None
            if durable_reviews is not None:
                reviewed_source_work_ids = {
                    str(item.get("source_work_id") or "") for item in durable_reviews
                }
            formal_source_work_ids = {
                str(item.get("source_work_id") or "")
                for item in inventory
                if item.get("formal_usable")
                and item.get("is_primary")
                and not item.get("used")
                and item.get("source_work_id") in task_source_work_ids
            }
            semantic_review_queue: list[dict[str, Any]] = []
            seen_review_source_works: set[str] = set()
            for material in saved_materials:
                source_work_id = str(material.get("source_work_id") or "")
                if (
                    not source_work_id
                    or source_work_id in reviewed_source_work_ids
                    or source_work_id in seen_review_source_works
                    or not str(material.get("transcript_text") or "").strip()
                ):
                    continue
                seen_review_source_works.add(source_work_id)
                role_matches = self.store.list_material_role_matches(
                    material_id=str(material["id"]),
                    role_id=role_id,
                )
                semantic_review_queue.append(
                    {
                        "material_id": material["id"],
                        "source_work_id": source_work_id,
                        "title": material.get("title") or material.get("clean_title"),
                        "automatic_role_decision": (
                            role_matches[0].get("decision") if role_matches else "not_evaluated"
                        ),
                        "automatic_fit_score": (
                            role_matches[0].get("fit_score") if role_matches else None
                        ),
                    }
                )
            try:
                durable_goal = self.store.count_available_task_formal_bases(
                    task_id=task_id,
                    role_id=role_id,
                )
            except RuntimeError as exc:
                if "orchestration schema is not installed" not in str(exc):
                    raise
                durable_goal = None
            if durable_goal is not None:
                formal_source_work_ids = set(durable_goal["source_work_ids"])
            pending_by_role.append(
                {
                    "role_id": role_id,
                    "pending_count": len(semantic_review_queue),
                    "material_ids": [item["material_id"] for item in semantic_review_queue],
                    "materials": semantic_review_queue,
                    "review_scope": "all_task_materials_regardless_of_automatic_role_match",
                    "next_inventory_command": (
                        f"mcn material inventory pending --role-id {role_id} "
                        f"--task-id {task_id} --json"
                    ),
                }
            )
            goal_by_role.append(
                {
                    "role_id": role_id,
                    "target_count": _target_count(task),
                    "qualified_formal_base_count": len(formal_source_work_ids),
                    "remaining_count": max(_target_count(task) - len(formal_source_work_ids), 0),
                    "goal_satisfied": len(formal_source_work_ids) >= _target_count(task),
                    "source_work_ids": sorted(formal_source_work_ids),
                }
            )
        call_summary = self.store.task_call_summary(task_id)
        asr_calls = [
            item
            for item in call_summary["by_tool"]
            if item.get("provider") == "aliyun"
            or item.get("tool_name") in {"douyin_extract_video_text", "video_to_text_v2"}
        ]
        asr_results = [
            material.get("transcription_result")
            for material in created_materials
            if isinstance(material.get("transcription_result"), dict)
        ]
        estimated_costs = [
            float(result["estimated_cost"])
            for result in asr_results
            if result.get("estimated_cost") not in (None, "")
        ]
        accepted_role_match_ids = {
            match["material_id"]
            for role_id in role_ids
            for match in self.store.list_material_role_matches(role_id=role_id, task_id=task_id)
            if match["decision"] == "accepted"
        }
        traversal = []
        for run in runs:
            summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
            contract = summary.get("traversal")
            if not isinstance(contract, dict):
                contract = summary.get("expand") if isinstance(summary.get("expand"), dict) else {}
            traversal.append({"run_id": run["id"], **contract})
        role_targeted_goal = bool(goal_by_role)
        qualified_formal_base_count = (
            min(item["qualified_formal_base_count"] for item in goal_by_role)
            if role_targeted_goal
            else len(saved_materials)
        )
        goal_satisfied = (
            all(item["goal_satisfied"] for item in goal_by_role)
            if role_targeted_goal
            else len(saved_materials) >= _target_count(task)
        )
        orchestration: dict[str, Any]
        try:
            sessions = self.store.list_channels_acquisition_sessions(task_id=task_id)
            orchestration = {
                "schema_ready": True,
                "actions": self.store.list_collection_task_actions(task_id=task_id),
                "events": self.store.list_collection_task_events(task_id=task_id),
                "frontiers": self.store.list_collection_task_frontiers(task_id=task_id),
                "reviews": self.store.list_collection_material_reviews(task_id=task_id),
                "acquisition_sessions": sessions,
                "acquisition_session_events": [
                    event
                    for session in sessions
                    for event in self.store.list_channels_acquisition_events(
                        session_id=str(session["id"])
                    )
                ],
            }
        except RuntimeError as exc:
            if "orchestration schema is not installed" not in str(exc):
                raise
            orchestration = {
                "schema_ready": False,
                "migration_command": "mcn db migrate-collection-task-orchestration-v1",
            }
        return {
            "task": task,
            "runs": runs,
            "target_count": _target_count(task),
            "saved_count": len(saved_materials),
            "created_material_count": len(created_materials),
            "existing_reused_count": len(existing_reused),
            "qualified_formal_base_count": qualified_formal_base_count,
            "goal_metric": (
                "available_reviewed_primary_formal_rewrite_base"
                if role_targeted_goal
                else "saved_material"
            ),
            "goal_satisfied": goal_satisfied,
            "goal_by_role": goal_by_role,
            "remaining_count": max(_target_count(task) - qualified_formal_base_count, 0),
            "saved_materials": saved_materials,
            "skipped_candidates": skipped,
            "newly_discovered_source_works": len(
                {material.get("source_work_id") for material in created_materials if material.get("source_work_id")}
            ),
            "reused_source_works": len(
                {material.get("source_work_id") for material in existing_reused if material.get("source_work_id")}
            ),
            "successful_transcriptions": len(
                {material["id"] for material in created_materials if str(material.get("transcript_text") or "").strip()}
            ),
            "rejected_candidate_count": len(skipped),
            "accepted_formal_material_count": len(
                {
                    material["id"]
                    for material in created_materials
                    if material.get("status") == "collected" and material.get("eligibility_status") == "accepted"
                }
            ),
            "accepted_role_match_count": len(accepted_role_match_ids),
            "inventory_handoff": {
                "schema_ready": inventory_schema_ready,
                "pending_review_count": sum(item["pending_count"] for item in pending_by_role),
                "roles": pending_by_role,
                "automatic_formal_classification": False,
            },
            "traversal_completeness": traversal,
            "asr_summary": {
                "calls": sum(int(item["count"]) for item in asr_calls),
                "cache_hits": sum(int(item["cache_hits"]) for item in asr_calls),
                "non_cache_requests": sum(
                    max(int(item["count"]) - int(item["cache_hits"]), 0)
                    for item in asr_calls
                    if item.get("status") == "ok"
                ),
                "paid_requests": sum(
                    1
                    for result in asr_results
                    if result.get("status") == "success" and not bool(result.get("cache_hit"))
                ),
                "estimated_cost": round(sum(estimated_costs), 8) if estimated_costs else None,
                "currency": "CNY" if estimated_costs else None,
            },
            "source_authors_discovered": source_authors,
            "understanding_summary": _understanding_summary(saved_materials),
            "next_recommended_keywords": _next_keywords_from_materials(saved_materials),
            "next_recommended_authors": _next_authors_from_materials(saved_materials),
            "collection_call_summary": call_summary,
            "orchestration": orchestration,
        }

    def _build_collection_provider(
        self,
        *,
        data_provider: str,
        transcription_provider: str,
        allow_paid_fallback: bool,
    ) -> DouyinProvider:
        return build_collection_provider(
            data_provider,
            transcription_provider_name=transcription_provider,
            allow_paid_fallback=allow_paid_fallback,
        )

    def _call_provider(
        self,
        client: DouyinProvider,
        *,
        run_id: str,
        method_key: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        arguments = {"params": params or {}, "body": body or {}}
        provider_name = str(getattr(client, "provider_name", "legacy"))
        fingerprint = request_fingerprint(method_key, arguments, provider=provider_name)
        started = time.monotonic()
        outer_cache_enabled = use_cache and method_key != "video_to_text_v2"
        if outer_cache_enabled:
            cached = self.store.get_cached_collection_call(fingerprint)
            if cached is not None:
                self.store.log_collection_call(
                    run_id=run_id,
                    provider=provider_name,
                    tool_name=method_key,
                    request_fingerprint=fingerprint,
                    status="ok",
                    duration_ms=_elapsed_ms(started),
                    cache_hit=True,
                )
                cached = dict(cached)
                cached["cache_hit"] = True
                return cached
        try:
            result = client.call(method_key, params=params, body=body, use_cache=use_cache)
        except Exception as exc:
            self.store.log_collection_call(
                run_id=run_id,
                provider=provider_name,
                tool_name=method_key,
                request_fingerprint=fingerprint,
                status="error",
                duration_ms=_elapsed_ms(started),
                cache_hit=False,
                error=str(exc),
            )
            raise
        status = "ok" if result.get("ok", True) else "error"
        if outer_cache_enabled and status == "ok":
            self.store.put_cached_collection_call(method_key, fingerprint, result, provider=provider_name)
        self.store.log_collection_call(
            run_id=run_id,
            provider=str(result.get("provider") or provider_name),
            tool_name=method_key,
            request_fingerprint=fingerprint,
            status=status,
            duration_ms=_elapsed_ms(started),
            cache_hit=bool(result.get("cache_hit")),
            error=str(result.get("error")) if status == "error" and result.get("error") else None,
        )
        return result

    def _resolve_author(self, *, sec_uid: str | None, name: str | None) -> dict[str, Any] | None:
        if sec_uid:
            return self.store.get_douyin_author(sec_uid)
        if not name:
            return None
        matches = [author for author in self.store.list_douyin_authors() if author.get("nickname") == name]
        if not matches:
            matches = [author for author in self.store.list_douyin_authors() if name in str(author.get("nickname") or "")]
        if len(matches) > 1:
            names = ", ".join(str(author.get("nickname")) for author in matches[:5])
            raise ValueError(f"multiple douyin authors matched {name!r}: {names}; use --sec-uid")
        return matches[0] if matches else None

    def _expand_author_videos(
        self,
        client: DouyinProvider,
        *,
        run_id: str,
        author: dict[str, Any],
        like_floor: int,
        min_duration_seconds: int,
        max_duration_seconds: int,
        max_pages: int,
        sort_type: int,
        stop_after_nonviral_pages: int,
        use_cache: bool,
    ) -> dict[str, Any]:
        cursor = ""
        page_limit = max_pages if max_pages > 0 else 100
        pages: list[dict[str, Any]] = []
        saved_video_ids: list[str] = []
        seen_cursors: set[str] = set()
        nonviral_page_streak = 0
        stop_reason = "max_pages"
        captured_pages = 0
        has_next = False
        for page_number in range(1, page_limit + 1):
            result = self._call_provider(
                client,
                run_id=run_id,
                method_key="user_post",
                params={
                    "userId": author["sec_uid"],
                    "sortType": sort_type,
                    "cursor": cursor,
                    "max_pages": max_pages,
                },
                use_cache=use_cache,
            )
            normalized = result.get("normalized") if isinstance(result.get("normalized"), dict) else {}
            items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
            packages = normalized.get("source_packages") if isinstance(normalized.get("source_packages"), list) else []
            page_videos: list[dict[str, Any]] = []
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                source_package = packages[index] if index < len(packages) and isinstance(packages[index], dict) else {}
                video = _author_video_from_normalized_item(item, source_package)
                page_videos.append(video)
                saved_video_ids.append(
                    self.store.upsert_douyin_author_video(
                        author["sec_uid"],
                        video,
                        raw=item.get("raw") if isinstance(item.get("raw"), dict) else None,
                    )
                )
            paging = result.get("paging") if isinstance(result.get("paging"), dict) else {}
            paging_raw = paging.get("raw") if isinstance(paging.get("raw"), dict) else {}
            browser_aggregated = bool(paging_raw.get("browser_aggregated"))
            result_pages = int(paging_raw.get("pages_captured") or 1)
            captured_pages += result_pages
            next_cursor = str(paging.get("cursor") or "")
            has_next = bool(paging.get("has_next"))
            page_viral_count = len(
                _rank_author_videos(
                    page_videos,
                    like_floor=like_floor,
                    min_duration_seconds=min_duration_seconds,
                    max_duration_seconds=max_duration_seconds,
                )
            )
            nonviral_page_streak = nonviral_page_streak + 1 if page_viral_count == 0 else 0
            pages.append(
                {
                    "page": page_number,
                    "captured_pages": result_pages,
                    "fetched_count": len(items),
                    "saved_count": len(page_videos),
                    "viral_count": page_viral_count,
                    "cursor": cursor,
                    "next_cursor": next_cursor,
                    "has_next": has_next,
                }
            )
            if not has_next:
                stop_reason = "no_next_page"
                break
            if browser_aggregated:
                stop_reason = str(paging_raw.get("stop_reason") or ("source_exhausted" if not has_next else "provider_stopped"))
                break
            if not next_cursor or next_cursor in seen_cursors:
                stop_reason = "cursor_exhausted"
                break
            if stop_after_nonviral_pages > 0 and nonviral_page_streak >= stop_after_nonviral_pages:
                stop_reason = "nonviral_page_streak"
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        source_exhausted = not has_next
        traversal = _traversal_contract(
            captured_pages=captured_pages,
            captured_items=len(set(saved_video_ids)),
            has_next=has_next,
            requested_pages=max_pages,
            stop_reason=stop_reason,
            source_exhausted=source_exhausted,
        )
        return {
            "pages": pages,
            "saved_count": len(set(saved_video_ids)),
            "total_stored_count": len(self.store.list_douyin_author_videos(author["sec_uid"])),
            "stop_reason": stop_reason,
            **traversal,
        }

    def _materialize_author_videos(
        self,
        *,
        run_id: str,
        task_id: str,
        author: dict[str, Any],
        like_floor: int,
        min_duration_seconds: int,
        max_duration_seconds: int,
        materialize_top: int,
        client: DouyinProvider | None,
        use_cache: bool,
        data_provider: str,
        transcription_provider: str,
        allow_paid_fallback: bool,
        refresh_existing_understanding: bool,
        understanding_provider: str,
        understanding_model: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        ranked = _rank_author_videos(
            self.store.list_douyin_author_videos(author["sec_uid"]),
            like_floor=like_floor,
            min_duration_seconds=min_duration_seconds,
            max_duration_seconds=max_duration_seconds,
        )
        materialized: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for video in ranked:
            if materialize_top > 0 and len(materialized) >= materialize_top:
                break
            existing = _find_collected_material_by_work_id(self.store, str(video.get("work_id") or ""))
            if existing:
                if existing.get("status") != "collected":
                    skipped.append(
                        {
                            "work_id": video.get("work_id"),
                            "title": video.get("title"),
                            "reason": "existing_unusable_material",
                            "material_id": existing["id"],
                        }
                    )
                    continue
                status = "existing_preserved"
                if refresh_existing_understanding:
                    understanding = build_material_understanding(
                        existing,
                        provider=understanding_provider,
                        model=understanding_model,
                    )
                    validate_understanding(understanding)
                    self.store.update_material_understanding(
                        existing["id"],
                        understanding=understanding,
                        provider=understanding_provider,
                        model=understanding_model,
                    )
                    self.store.log_material_understanding(
                        run_id=existing.get("run_id") or run_id,
                        material_id=existing["id"],
                        provider=understanding_provider,
                        model=understanding_model,
                        status="ok",
                        output=understanding,
                    )
                    status = "existing_understanding_refreshed"
                materialized.append(
                    {
                        "material_id": existing["id"],
                        "work_id": video.get("work_id"),
                        "title": video.get("title"),
                        "status": status,
                    }
                )
                continue
            source_url = video.get("source_url")
            if not source_url:
                skipped.append({"work_id": video.get("work_id"), "title": video.get("title"), "reason": "missing_source_url"})
                continue
            client = client or self._build_collection_provider(
                data_provider=data_provider,
                transcription_provider=transcription_provider,
                allow_paid_fallback=allow_paid_fallback,
            )
            try:
                detail_result = self._call_provider(
                    client,
                    run_id=run_id,
                    method_key="detail_v4",
                    body={"url": source_url},
                    use_cache=use_cache,
                )
                detail_normalized = detail_result.get("normalized") if isinstance(detail_result.get("normalized"), dict) else {}
                detail_package = detail_normalized.get("source_package") if isinstance(detail_normalized.get("source_package"), dict) else {}
                detail_rejection = _author_detail_rejection(
                    detail_package,
                    like_floor=like_floor,
                    min_duration_seconds=min_duration_seconds,
                    max_duration_seconds=max_duration_seconds,
                )
                if detail_rejection:
                    raise ValueError(detail_rejection)
            except Exception as exc:
                skipped.append(
                    {
                        "work_id": video.get("work_id"),
                        "title": video.get("title"),
                        "reason": "detail_verification_failed",
                        "detail": str(exc),
                    }
                )
                continue
            verified_video = _author_video_from_normalized_item({}, detail_package)
            video = {**video, **{key: value for key, value in verified_video.items() if value not in (None, "", [], {})}}
            try:
                extract_result = self._call_provider(
                    client,
                    run_id=run_id,
                    method_key="video_to_text_v2",
                    body={"url": source_url},
                    use_cache=use_cache,
                )
            except Exception as exc:
                skipped.append(
                    {
                        "work_id": video.get("work_id"),
                        "title": video.get("title"),
                        "reason": "video_to_text_failed",
                        "detail": str(exc),
                    }
                )
                continue
            normalized = extract_result.get("normalized") if isinstance(extract_result.get("normalized"), dict) else {}
            transcript_text = str(normalized.get("text") or (normalized.get("source_package") or {}).get("transcript_text") or "").strip()
            if not transcript_text:
                skipped.append({"work_id": video.get("work_id"), "title": video.get("title"), "reason": "empty_transcript"})
                continue
            source_package = _source_package_from_author_video(author, video)
            source_package["task_id"] = task_id
            _merge_source_package(source_package, detail_package)
            extract_package = normalized.get("source_package") if isinstance(normalized.get("source_package"), dict) else {}
            _merge_source_package(source_package, extract_package)
            source_package["transcript_text"] = transcript_text
            eligibility = evaluate_material_eligibility(source_package)
            source_package["material_eligibility"] = eligibility
            if not is_material_eligible(eligibility):
                skipped.append(
                    {
                        "work_id": video.get("work_id"),
                        "title": video.get("title"),
                        "reason": eligibility.get("reject_reason") or "eligibility_rejected",
                        "detail": "; ".join(eligibility.get("reasons") or []),
                    }
                )
                continue
            understanding = build_material_understanding(
                source_package,
                provider=understanding_provider,
                model=understanding_model,
            )
            validate_understanding(understanding)
            source_package["material_understanding"] = understanding
            source_package["understanding_status"] = str(understanding.get("status") or "success")
            material_id = self.store.insert_collected_material(
                run_id=run_id,
                source_package=source_package,
                material_understanding=understanding,
                raw={"author": _author_summary(author), "author_video": video, "video_to_text_v2_result": extract_result},
            )
            self.store.log_material_understanding(
                run_id=run_id,
                material_id=material_id,
                provider=understanding_provider,
                model=understanding_model,
                status="ok",
                output=understanding,
            )
            materialized.append(
                {
                    "material_id": material_id,
                    "work_id": video.get("work_id"),
                    "title": video.get("title"),
                    "status": "created_draft_understanding",
                }
            )
        return materialized, skipped


def discover_source_authors(store: Store, *, min_appearances: int = 2) -> list[dict[str, Any]]:
    authors: dict[str, dict[str, Any]] = {}
    _add_material_authors(authors, store.list_collected_materials())
    _add_candidate_authors(authors, store.list_collection_candidates())
    for author in store.list_douyin_authors():
        videos = store.list_douyin_author_videos(author["sec_uid"])
        key = _author_key(author.get("sec_uid"), author.get("nickname"))
        record = authors.setdefault(key, _blank_author_record(author.get("sec_uid"), author.get("nickname")))
        record["author_profile_url"] = record.get("author_profile_url") or author.get("profile_url")
        record["follower_count"] = author.get("follower_count")
        record["has_profile"] = True
        for video in videos:
            score = _score_from_metrics(video.get("metrics") or {})
            record["appearances"] += 1
            record["scores"].append(score)
    for record in authors.values():
        scores = record.pop("scores", [])
        record["max_engagement_score"] = max(scores) if scores else 0
        record["avg_engagement_score"] = int(sum(scores) / len(scores)) if scores else 0
    return [
        record
        for record in sorted(
            authors.values(),
            key=lambda item: (
                int(item.get("appearances") or 0),
                int(item.get("max_engagement_score") or 0),
                int(item.get("avg_engagement_score") or 0),
                bool(item.get("has_profile")),
                int(item.get("follower_count") or 0),
            ),
            reverse=True,
        )
        if int(record.get("appearances") or 0) >= min_appearances
    ]


def discover_source_authors_from_records(materials: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    authors: dict[str, dict[str, Any]] = {}
    _add_material_authors(authors, materials)
    _add_candidate_authors(authors, candidates)
    for record in authors.values():
        scores = record.pop("scores", [])
        record["max_engagement_score"] = max(scores) if scores else 0
        record["avg_engagement_score"] = int(sum(scores) / len(scores)) if scores else 0
    return sorted(
        authors.values(),
        key=lambda item: (
            int(item.get("appearances") or 0),
            int(item.get("max_engagement_score") or 0),
            int(item.get("avg_engagement_score") or 0),
        ),
        reverse=True,
    )


def format_task_show(report: dict[str, Any]) -> str:
    task = report["task"]
    understanding = report["understanding_summary"]
    return "\n".join(
        [
            f"Task {task['id']} [{task['status']}]",
            f"scope={task['target_scope']} topic={task.get('topic') or ''}",
            f"goal={report['qualified_formal_base_count']}/{report['target_count']} metric={report['goal_metric']} remaining={report['remaining_count']}",
            f"material_results={report['saved_count']} created={report['created_material_count']} reused={report['existing_reused_count']}",
            f"runs={len(report['runs'])} skipped={len(report['skipped_candidates'])} api_calls={report['collection_call_summary']['total_calls']} cache_hits={report['collection_call_summary']['cache_hits']}",
            f"inventory_pending={report['inventory_handoff']['pending_review_count']} automatic_formal_classification=false",
            f"understanding metadata_ready={understanding['metadata_ready_count']} codex_default={understanding['final_codex_count']} rules_draft={understanding['draft_local_count']} pending_material={understanding['pending_material_understanding_count']}",
        ]
    )


def format_task_report_markdown(report: dict[str, Any]) -> str:
    task = report["task"]
    lines = [
        f"# Collection Task Report: {task['id']}",
        "",
        f"- scope: {task['target_scope']}",
        f"- status: {task['status']}",
        f"- topic: {task.get('topic') or ''}",
        f"- target_count: {report['target_count']}",
        f"- goal_metric: {report['goal_metric']}",
        f"- qualified_formal_base_count: {report['qualified_formal_base_count']}",
        f"- goal_satisfied: {str(report['goal_satisfied']).lower()}",
        f"- saved_count: {report['saved_count']}",
        f"- created_material_count: {report['created_material_count']}",
        f"- existing_reused_count: {report['existing_reused_count']}",
        f"- remaining_count: {report['remaining_count']}",
        f"- newly_discovered_source_works: {report['newly_discovered_source_works']}",
        f"- reused_source_works: {report['reused_source_works']}",
        f"- successful_transcriptions: {report['successful_transcriptions']}",
        f"- accepted_formal_material_count: {report['accepted_formal_material_count']}",
        f"- accepted_role_match_count: {report['accepted_role_match_count']}",
        "",
        "## Understanding",
        "",
    ]
    understanding = report["understanding_summary"]
    lines.extend(
        [
            f"- metadata_ready_count: {understanding['metadata_ready_count']}",
            f"- final_codex_count: {understanding['final_codex_count']}",
            f"- draft_local_count: {understanding['draft_local_count']}",
            f"- pending_material_understanding_count: {understanding['pending_material_understanding_count']}",
        ]
    )
    if understanding["pending_codex_understanding_count"]:
        lines.append("- note: 有素材缺少正式 material understanding，需要补齐后再作为二创检索 metadata 使用。")
    lines.extend(["", "## Saved Materials", ""])
    for material in report["saved_materials"]:
        lines.append(
            f"- {material['id']} | {material.get('understanding_provider')}/{material.get('understanding_model')}/{material.get('understanding_status')} | "
            f"{material.get('title') or material.get('clean_title') or ''}"
        )
    lines.extend(["", "## Skipped Candidates", ""])
    for candidate in report["skipped_candidates"][:50]:
        lines.append(
            f"- {candidate.get('status')} | {candidate.get('skip_reason') or ''} | {candidate.get('title') or ''}"
        )
    lines.extend(["", "## Inventory Handoff", ""])
    handoff = report["inventory_handoff"]
    lines.append(f"- schema_ready: {str(handoff['schema_ready']).lower()}")
    lines.append(f"- pending_review_count: {handoff['pending_review_count']}")
    lines.append("- automatic_formal_classification: false")
    for role in handoff["roles"]:
        lines.append(
            f"- role={role['role_id']} pending_semantic_review={role['pending_count']} "
            f"scope={role['review_scope']}"
        )
    lines.extend(["", "## Source Authors Discovered", ""])
    for author in report["source_authors_discovered"][:30]:
        lines.append(
            f"- {author.get('author_name') or ''} | sec_uid={author.get('author_sec_uid') or ''} | appearances={author.get('appearances')}"
        )
    lines.extend(["", "## Next Recommendations", ""])
    lines.append("- keywords: " + ", ".join(report["next_recommended_keywords"][:20]))
    lines.append(
        "- authors: "
        + ", ".join(
            str(author.get("author_name") or author.get("author_sec_uid") or "")
            for author in report["next_recommended_authors"][:20]
        )
    )
    lines.extend(["", "## API Calls", ""])
    call_summary = report["collection_call_summary"]
    lines.append(f"- total_calls: {call_summary['total_calls']}")
    lines.append(f"- cache_hits: {call_summary['cache_hits']}")
    for item in call_summary["by_tool"]:
        lines.append(f"- {item['tool_name']} {item['status']}: {item['count']} calls, {item['cache_hits']} cache hits")
    return "\n".join(lines).rstrip() + "\n"


def _author_summary(author: dict[str, Any]) -> dict[str, Any]:
    return {
        "sec_uid": author.get("sec_uid"),
        "uid": author.get("uid"),
        "douyin_id": author.get("douyin_id"),
        "nickname": author.get("nickname"),
        "profile_url": author.get("profile_url"),
        "follower_count": author.get("follower_count"),
        "aweme_count": author.get("aweme_count"),
        "total_favorited": author.get("total_favorited"),
    }


def _author_video_from_normalized_item(item: dict[str, Any], source_package: dict[str, Any]) -> dict[str, Any]:
    metrics = source_package.get("public_metrics") if isinstance(source_package.get("public_metrics"), dict) else item.get("metrics")
    return {
        "work_id": item.get("id") or source_package.get("work_id"),
        "source_url": source_package.get("source_link") or item.get("share_url") or item.get("short_url"),
        "title": source_package.get("title") or item.get("title"),
        "platform_caption": source_package.get("platform_caption") or item.get("caption") or item.get("title"),
        "caption": source_package.get("platform_caption") or item.get("caption") or item.get("title"),
        "post_time": source_package.get("post_time") or item.get("post_time"),
        "duration_ms": source_package.get("duration_ms") or item.get("duration"),
        "cover_url": source_package.get("cover_url") or item.get("cover_url"),
        "metrics": metrics or {},
        "source_package": source_package,
    }


def _source_package_from_author_video(author: dict[str, Any], video: dict[str, Any]) -> dict[str, Any]:
    source_package = dict(video.get("source_package") or {})
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    defaults = {
        "source_type": "douyin_author",
        "source_platform": "douyin",
        "source_link": video.get("source_url"),
        "title": video.get("title"),
        "clean_title": video.get("title"),
        "platform_caption": video.get("title"),
        "caption_text": video.get("caption_text") or video.get("title"),
        "hashtags": video.get("hashtags") or [],
        "author_name": author.get("nickname"),
        "author_sec_uid": author.get("sec_uid"),
        "author_profile_url": author.get("profile_url"),
        "author_douyin_id": author.get("douyin_id"),
        "work_id": video.get("work_id"),
        "post_time": video.get("post_time"),
        "duration_ms": video.get("duration_ms"),
        "cover_url": video.get("cover_url"),
        "public_metrics": {
            "digg_count": metrics.get("digg_count") or video.get("likes"),
            "collect_count": metrics.get("collect_count") or video.get("collects"),
            "comment_count": metrics.get("comment_count") or video.get("comments"),
            "share_count": metrics.get("share_count") or video.get("shares"),
            "play_count": metrics.get("play_count"),
        },
        "collection_notes": ["author_hot_work"],
    }
    for key, value in defaults.items():
        if source_package.get(key) in (None, "", []):
            source_package[key] = value
    return source_package


def _merge_source_package(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if value in (None, "", []):
            continue
        if key in {"title", "clean_title", "platform_caption", "caption_text"} and base.get(key):
            continue
        if base.get(key) in (None, "", []):
            base[key] = value


def _find_collected_material_by_work_id(store: Store, work_id: str) -> dict[str, Any] | None:
    if not work_id:
        return None
    for material in store.list_collected_materials():
        if str(material.get("work_id") or "") == work_id:
            return material
    return None


def _rank_author_videos(
    videos: list[dict[str, Any]],
    *,
    like_floor: int,
    min_duration_seconds: int,
    max_duration_seconds: int,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for video in videos:
        metrics = _author_video_metrics(video)
        candidate = {"source_package": {"public_metrics": metrics}}
        likes = metric_value(metrics, "digg_count", "likes")
        score = engagement_score(candidate)
        duration_ms = _optional_int(video.get("duration_ms"))
        if duration_ms is not None:
            duration_seconds = duration_ms / 1000
            if duration_seconds < min_duration_seconds or duration_seconds > max_duration_seconds:
                continue
        if likes < like_floor and score < max(like_floor * 2, 1):
            continue
        ranked.append(
            {
                "id": video.get("id"),
                "work_id": video.get("work_id"),
                "title": video.get("title"),
                "source_url": video.get("source_url"),
                "post_time": video.get("post_time"),
                "duration_ms": duration_ms,
                "likes": likes,
                "collects": metric_value(metrics, "collect_count", "favorites", "favorite_count"),
                "comments": metric_value(metrics, "comment_count", "comments"),
                "shares": metric_value(metrics, "share_count", "shares"),
                "score": score,
                "metrics": metrics,
                "source_package": video.get("source_package") if isinstance(video.get("source_package"), dict) else {},
                "hashtags": video.get("hashtags") or [],
                "caption_text": video.get("caption_text"),
                "cover_url": video.get("cover_url"),
            }
        )
    return sorted(
        ranked,
        key=lambda item: (
            int(item["score"]),
            int(item["shares"]),
            int(item["collects"]),
            int(item["comments"]),
            int(item["likes"]),
        ),
        reverse=True,
    )


def _author_video_metrics(video: dict[str, Any]) -> dict[str, Any]:
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    if metrics:
        return dict(metrics)
    source_package = video.get("source_package") if isinstance(video.get("source_package"), dict) else {}
    package_metrics = source_package.get("public_metrics") if isinstance(source_package.get("public_metrics"), dict) else {}
    return dict(package_metrics)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _author_detail_rejection(
    source_package: dict[str, Any],
    *,
    like_floor: int,
    min_duration_seconds: int,
    max_duration_seconds: int,
) -> str | None:
    if not source_package:
        return "Detail provider returned no authoritative source package."
    duration_ms = _optional_int(source_package.get("duration_ms"))
    if duration_ms is not None:
        duration_seconds = duration_ms / 1000
        if duration_seconds < min_duration_seconds:
            return f"Authoritative duration {duration_seconds:.1f}s is below {min_duration_seconds}s."
        if duration_seconds > max_duration_seconds:
            return f"Authoritative duration {duration_seconds:.1f}s exceeds {max_duration_seconds}s."
    metrics = source_package.get("public_metrics") if isinstance(source_package.get("public_metrics"), dict) else {}
    likes = metric_value(metrics, "digg_count", "likes")
    score = engagement_score({"source_package": {"public_metrics": metrics}})
    if likes < like_floor and score < max(like_floor * 2, 1):
        return f"Authoritative metrics are below the viral threshold {like_floor}."
    return None


def _traversal_contract(
    *,
    captured_pages: int,
    captured_items: int,
    has_next: bool,
    requested_pages: int,
    stop_reason: str,
    source_exhausted: bool,
) -> dict[str, Any]:
    request_satisfied = source_exhausted or (requested_pages > 0 and captured_pages >= requested_pages)
    return {
        "captured_pages": captured_pages,
        "captured_items": captured_items,
        "has_next": has_next,
        "request_satisfied": request_satisfied,
        "source_exhausted": source_exhausted,
        "stop_reason": stop_reason,
    }


def _workflow_goal_status(saved_count: int, target_count: int) -> str:
    if target_count <= 0 or saved_count >= target_count:
        return "completed"
    if saved_count > 0:
        return "partial"
    return "empty"


def _resume_data_provider(value: Any, *, default: str) -> str:
    provider = str(value or default).strip().lower()
    if provider in {"mxnzp", "auto"}:
        return "direct"
    return provider


def _resume_transcription_provider(value: Any) -> str:
    provider = str(value or "aliyun").strip().lower()
    return "aliyun" if provider in {"", "provider"} else provider


def _orchestration_schema_ready(store: Store) -> bool:
    with store.connect() as conn:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("collection_task_actions",),
        ).fetchone() is not None


def _target_understanding(
    *,
    provider: str = TARGET_UNDERSTANDING_PROVIDER,
    model: str = TARGET_UNDERSTANDING_MODEL,
) -> dict[str, str]:
    return {"provider": provider, "model": model, "status": "success"}


def _target_count(task: dict[str, Any]) -> int:
    value = task.get("target_count_per_role")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _task_saved_count(report: dict[str, Any]) -> int:
    return int(report.get("saved_count") or 0)


def _task_goal_count(report: dict[str, Any]) -> int:
    if report.get("goal_by_role"):
        return int(report.get("qualified_formal_base_count") or 0)
    return _task_saved_count(report)


def _understanding_summary(materials: list[dict[str, Any]]) -> dict[str, Any]:
    final_codex_count = 0
    draft_local_count = 0
    metadata_ready_count = 0
    for material in materials:
        provider = str(material.get("understanding_provider") or "")
        model = str(material.get("understanding_model") or "")
        status = str(material.get("understanding_status") or "")
        if provider == TARGET_UNDERSTANDING_PROVIDER and model == TARGET_UNDERSTANDING_MODEL and status == "success":
            final_codex_count += 1
        if provider != LOCAL_UNDERSTANDING_PROVIDER and status == "success":
            metadata_ready_count += 1
        if provider == LOCAL_UNDERSTANDING_PROVIDER or status == "draft_local_understanding":
            draft_local_count += 1
    return {
        "total": len(materials),
        "metadata_ready_count": metadata_ready_count,
        "final_codex_count": final_codex_count,
        "draft_local_count": draft_local_count,
        "pending_material_understanding_count": max(len(materials) - metadata_ready_count, 0),
        "pending_codex_understanding_count": max(len(materials) - metadata_ready_count, 0),
    }


def _next_keywords_from_report(report: dict[str, Any]) -> list[str]:
    return _unique_strings(report.get("next_recommended_keywords") or [])


def _next_keywords_from_materials(materials: list[dict[str, Any]]) -> list[str]:
    keywords: list[str] = []
    for material in materials:
        keywords.extend(material.get("next_collection_keywords") or [])
        understanding = material.get("material_understanding") or {}
        keywords.extend(understanding.get("next_collection_keywords") or [])
    return _unique_strings(keywords)


def _next_authors_from_materials(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    authors = discover_source_authors_from_records(materials, [])
    return [author for author in authors if author.get("author_sec_uid") or author.get("author_name")]


def _role_collection_keywords(role_profile: dict[str, Any] | None, topic: str) -> list[str]:
    if not role_profile:
        return []
    topic_text = str(topic or "")
    theme_map = role_profile.get("theme_map") or {}
    collection_targets = theme_map.get("collection_targets") if isinstance(theme_map, dict) else None
    if isinstance(collection_targets, dict):
        matched_keywords: list[str] = []
        for key, target in collection_targets.items():
            target_text = " ".join([str(key), str(target.get("selection_note") if isinstance(target, dict) else "")])
            if topic_text and topic_text not in target_text and target_text not in topic_text:
                continue
            if isinstance(target, dict):
                matched_keywords.extend(target.get("preferred_keywords") or [])
        if matched_keywords:
            return _unique_strings(matched_keywords)
    return _role_keywords(role_profile)


def _keyword_in_topic_scope(keyword: str, topic: str, role_profile: dict[str, Any] | None) -> bool:
    normalized = str(keyword or "").strip()
    if not normalized:
        return False
    topic_terms = _topic_scope_terms(topic)
    if any(term and term in normalized for term in topic_terms):
        return True
    scoped_role_keywords = _role_collection_keywords(role_profile, topic)
    return normalized in scoped_role_keywords


def _topic_scope_terms(topic: str) -> list[str]:
    normalized = str(topic or "").strip()
    if not normalized:
        return []
    terms = [normalized]
    terms.extend([part for part in normalized.replace("，", " ").replace("、", " ").replace("/", " ").split() if len(part) >= 2])
    known_terms = ["道家", "修行", "修心", "道德经", "庄子", "财运", "守财", "贵人运"]
    terms.extend([term for term in known_terms if term in normalized])
    return _unique_strings(terms)


def _role_keywords(role_profile: dict[str, Any] | None) -> list[str]:
    if not role_profile:
        return []
    return _unique_strings(
        [
            *(role_profile.get("search_keywords") or []),
            *(role_profile.get("target_directions") or []),
            *(role_profile.get("preferred_content") or []),
        ]
    )


def _add_material_authors(authors: dict[str, dict[str, Any]], materials: list[dict[str, Any]]) -> None:
    for material in materials:
        sec_uid = material.get("author_sec_uid")
        name = material.get("author_name")
        if not sec_uid and not name:
            continue
        key = _author_key(sec_uid, name)
        record = authors.setdefault(key, _blank_author_record(sec_uid, name))
        record["author_profile_url"] = record.get("author_profile_url") or material.get("author_profile_url")
        record["appearances"] += 1
        record["scores"].append(_score_from_metrics(material.get("metrics") or {}))


def _add_candidate_authors(authors: dict[str, dict[str, Any]], candidates: list[dict[str, Any]]) -> None:
    for candidate in candidates:
        source_package = candidate.get("source_package") if isinstance(candidate.get("source_package"), dict) else {}
        sec_uid = source_package.get("author_sec_uid")
        name = source_package.get("author_name") or candidate.get("author_name")
        if not sec_uid and not name:
            continue
        key = _author_key(sec_uid, name)
        record = authors.setdefault(key, _blank_author_record(sec_uid, name))
        record["author_profile_url"] = record.get("author_profile_url") or source_package.get("author_profile_url")
        record["appearances"] += 1
        record["scores"].append(_score_from_metrics(candidate.get("metrics") or source_package.get("public_metrics") or {}))


def _blank_author_record(sec_uid: Any, name: Any) -> dict[str, Any]:
    return {
        "author_sec_uid": sec_uid,
        "author_name": name,
        "author_profile_url": None,
        "appearances": 0,
        "scores": [],
        "max_engagement_score": 0,
        "avg_engagement_score": 0,
        "has_profile": False,
        "follower_count": None,
    }


def _author_key(sec_uid: Any, name: Any) -> str:
    return str(sec_uid or name or "").strip()


def _score_from_metrics(metrics: dict[str, Any]) -> int:
    return engagement_score({"source_package": {"public_metrics": metrics}})


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def report_to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
