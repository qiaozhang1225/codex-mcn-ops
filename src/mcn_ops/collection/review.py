from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from ..store import Store
from .task_contracts import (
    TERMINAL_TASK_STATUSES,
    CollectionActionStatus,
    CollectionActionType,
    CollectionTaskStatus,
    MaterialReviewOutcome,
)

OPEN_REVIEW_ACTION_STATUSES = frozenset(
    {
        CollectionActionStatus.PLANNED.value,
        CollectionActionStatus.CLAIMED.value,
        CollectionActionStatus.RUNNING.value,
        CollectionActionStatus.INTERRUPTED.value,
    }
)

FORMAL_TRANSCRIPT_DUPLICATE_THRESHOLD = 0.80
FORMAL_TRANSCRIPT_DUPLICATE_MIN_CHARS = 120


class TaskReviewService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def review(
        self,
        *,
        task_id: str,
        material_id: str,
        role_id: str,
        outcome: str,
        topic_direction: str,
        content_mechanism: str,
        evidence: dict[str, Any],
        reviewer: str,
        idempotency_key: str,
        fit_score: float | None = None,
        knowledge_subtype: str | None = None,
    ) -> dict[str, Any]:
        normalized = self._validate_request(
            outcome=outcome,
            topic_direction=topic_direction,
            content_mechanism=content_mechanism,
            evidence=evidence,
            reviewer=reviewer,
            idempotency_key=idempotency_key,
            fit_score=fit_score,
            knowledge_subtype=knowledge_subtype,
        )
        task = self.store.get_collection_task(task_id)
        if task is None:
            raise KeyError(f"collection task not found: {task_id}")
        role = self.store.get_ip_role(role_id)
        if role is None:
            raise KeyError(f"role not found: {role_id}")
        self._require_task_role(task_id=task_id, task=task, role_id=role_id)
        if role.get("confirmation_status") != "confirmed" or bool(role.get("needs_reconfirm")):
            raise ValueError(f"role must be confirmed before semantic review: {role_id}")
        material = self.store.get_collected_material(material_id)
        if material is None:
            raise KeyError(f"material not found: {material_id}")
        transcript = str(material.get("transcript_text") or "").strip()
        if not transcript:
            raise ValueError(f"material has no complete transcript: {material_id}")
        transcript_sha256 = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
        role_profile_version = int(role.get("profile_version") or 0)
        input_payload = {
            "material_id": material_id,
            "role_id": role_id,
            "outcome": normalized["outcome"],
            "topic_direction": normalized["topic_direction"],
            "content_mechanism": normalized["content_mechanism"],
            "knowledge_subtype": normalized["knowledge_subtype"],
            "evidence": normalized["evidence"],
            "reviewer": normalized["reviewer"],
            "fit_score": normalized["fit_score"],
            "role_profile_version": role_profile_version,
            "transcript_sha256": transcript_sha256,
        }
        existing = next(
            (
                action
                for action in self.store.list_collection_task_actions(task_id=task_id)
                if action["idempotency_key"] == normalized["idempotency_key"]
            ),
            None,
        )
        task_status = CollectionTaskStatus(task["status"])
        if existing is None and (
            task_status in TERMINAL_TASK_STATUSES
            or task_status in {
                CollectionTaskStatus.COMPLETING,
                CollectionTaskStatus.CANCELLING,
                CollectionTaskStatus.CLEANUP_REQUIRED,
            }
        ):
            raise ValueError(f"collection task does not accept new reviews in status {task_status.value}")
        if existing is None and task_status is not CollectionTaskStatus.AWAITING_REVIEW:
            raise ValueError(f"collection task is not awaiting semantic review: {task_id} ({task_status.value})")

        action = self.store.create_collection_task_action(
            task_id=task_id,
            action_type=CollectionActionType.REVIEW_MATERIAL.value,
            idempotency_key=normalized["idempotency_key"],
            input_payload=input_payload,
            reason="full-transcript-semantic-review",
        )
        if action["status"] == CollectionActionStatus.SUCCEEDED.value:
            review = self._review_for_action(task_id=task_id, action_id=action["id"])
            return self._finish_response(
                task_id=task_id,
                role_id=role_id,
                action=action,
                review=review,
            )
        if action["status"] in {
            CollectionActionStatus.FAILED.value,
            CollectionActionStatus.CANCELLED.value,
        }:
            raise RuntimeError(
                f"review action is already {action['status']}: {action['id']} ({action.get('error') or {}})"
            )
        if action["status"] in {
            CollectionActionStatus.PLANNED.value,
            CollectionActionStatus.INTERRUPTED.value,
        }:
            action = self.store.claim_collection_task_action(
                action["id"],
                lease_owner=normalized["reviewer"],
                lease_expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            )
        if action["status"] == CollectionActionStatus.CLAIMED.value:
            action = self.store.update_collection_task_action_status(
                action["id"],
                status=CollectionActionStatus.RUNNING.value,
            )
        if action["status"] != CollectionActionStatus.RUNNING.value:
            raise RuntimeError(f"review action is not executable: {action['id']} ({action['status']})")

        try:
            if normalized["outcome"] == MaterialReviewOutcome.FORMAL_REWRITE_BASE.value:
                duplicate = self._find_formal_transcript_duplicate(
                    material_id=material_id,
                    role_id=role_id,
                    transcript=transcript,
                )
                if duplicate is not None:
                    raise ValueError(
                        "near-duplicate formal transcript: "
                        f"material_id={duplicate['material_id']} "
                        f"similarity={duplicate['similarity']:.3f}"
                    )
            review = self.store.record_collection_material_review(
                task_id=task_id,
                action_id=action["id"],
                material_id=material_id,
                role_id=role_id,
                outcome=normalized["outcome"],
                topic_direction=normalized["topic_direction"],
                content_mechanism=normalized["content_mechanism"],
                evidence=normalized["evidence"],
                reviewer=normalized["reviewer"],
                role_profile_version=role_profile_version,
                transcript_sha256=transcript_sha256,
                fit_score=normalized["fit_score"],
                knowledge_subtype=normalized["knowledge_subtype"],
            )
        except Exception as exc:
            current_action = self.store.get_collection_task_action(action["id"])
            if current_action and current_action["status"] == CollectionActionStatus.RUNNING.value:
                self.store.update_collection_task_action_status(
                    action["id"],
                    status=CollectionActionStatus.FAILED.value,
                    error={"error_type": type(exc).__name__, "message": str(exc)},
                )
            raise
        action = self.store.get_collection_task_action(action["id"]) or action
        return self._finish_response(
            task_id=task_id,
            role_id=role_id,
            action=action,
            review=review,
        )

    def _finish_response(
        self,
        *,
        task_id: str,
        role_id: str,
        action: dict[str, Any],
        review: dict[str, Any],
    ) -> dict[str, Any]:
        progress = self._reconcile_task_state(
            task_id=task_id,
            role_id=role_id,
            review_action_id=str(action["id"]),
        )
        return {
            "task": progress["task"],
            "action": self.store.get_collection_task_action(str(action["id"])) or action,
            "review": review,
            "progress": progress,
        }

    def _find_formal_transcript_duplicate(
        self,
        *,
        material_id: str,
        role_id: str,
        transcript: str,
    ) -> dict[str, Any] | None:
        normalized = self._normalize_transcript_for_dedup(transcript)
        if len(normalized) < FORMAL_TRANSCRIPT_DUPLICATE_MIN_CHARS:
            return None
        best: dict[str, Any] | None = None
        seen_material_ids: set[str] = set()
        for review in self.store.list_collection_material_reviews(role_id=role_id):
            reviewed_material_id = str(review.get("material_id") or "")
            if (
                review.get("outcome") != MaterialReviewOutcome.FORMAL_REWRITE_BASE.value
                or not reviewed_material_id
                or reviewed_material_id == material_id
                or reviewed_material_id in seen_material_ids
            ):
                continue
            seen_material_ids.add(reviewed_material_id)
            reviewed_material = self.store.get_collected_material(reviewed_material_id)
            if reviewed_material is None:
                continue
            reviewed_transcript = self._normalize_transcript_for_dedup(
                str(reviewed_material.get("transcript_text") or "")
            )
            if len(reviewed_transcript) < FORMAL_TRANSCRIPT_DUPLICATE_MIN_CHARS:
                continue
            length_ratio = min(len(normalized), len(reviewed_transcript)) / max(
                len(normalized), len(reviewed_transcript)
            )
            if length_ratio < 0.60:
                continue
            similarity = SequenceMatcher(
                None,
                normalized,
                reviewed_transcript,
                autojunk=False,
            ).ratio()
            if similarity < FORMAL_TRANSCRIPT_DUPLICATE_THRESHOLD:
                continue
            if best is None or similarity > float(best["similarity"]):
                best = {
                    "material_id": reviewed_material_id,
                    "similarity": similarity,
                }
        return best

    @staticmethod
    def _normalize_transcript_for_dedup(transcript: str) -> str:
        return re.sub(r"[^\w]+", "", transcript.casefold(), flags=re.UNICODE)

    def _reconcile_task_state(
        self,
        *,
        task_id: str,
        role_id: str,
        review_action_id: str,
    ) -> dict[str, Any]:
        for _attempt in range(3):
            task = self.store.get_collection_task(task_id)
            if task is None:
                raise KeyError(f"collection task not found: {task_id}")
            role_targets = self._role_targets(task_id=task_id, task=task, fallback_role_id=role_id)
            target_count = role_targets[role_id]
            formal_by_role = {
                target_role_id: self.store.count_available_task_formal_bases(
                    task_id=task_id,
                    role_id=target_role_id,
                )
                for target_role_id in role_targets
            }
            formal = formal_by_role[role_id]
            pending_by_role = {
                target_role_id: self._pending_review_count(
                    task_id=task_id,
                    role_id=target_role_id,
                )
                for target_role_id in role_targets
            }
            pending_review_count = sum(pending_by_role.values())
            pending_action_count = sum(
                1
                for action in self.store.list_collection_task_actions(task_id=task_id)
                if action["action_type"] == CollectionActionType.REVIEW_MATERIAL.value
                and action["status"] in OPEN_REVIEW_ACTION_STATUSES
            )
            qualified_count = int(formal["qualified_formal_base_count"])
            goal_by_role = [
                {
                    "role_id": target_role_id,
                    "target_count": role_targets[target_role_id],
                    "qualified_formal_base_count": int(
                        formal_by_role[target_role_id]["qualified_formal_base_count"]
                    ),
                    "remaining_count": max(
                        role_targets[target_role_id]
                        - int(formal_by_role[target_role_id]["qualified_formal_base_count"]),
                        0,
                    ),
                    "pending_review_count": pending_by_role[target_role_id],
                }
                for target_role_id in role_targets
            ]
            if all(item["remaining_count"] == 0 for item in goal_by_role):
                target_status = CollectionTaskStatus.COMPLETING
            elif pending_review_count > 0 or pending_action_count > 0:
                target_status = CollectionTaskStatus.AWAITING_REVIEW
            else:
                target_status = CollectionTaskStatus.AWAITING_STRATEGY
            progress = {
                "task_id": task_id,
                "role_id": role_id,
                "target_count": target_count,
                "qualified_formal_base_count": qualified_count,
                "remaining_count": max(target_count - qualified_count, 0),
                "pending_review_count": pending_review_count,
                "pending_review_action_count": pending_action_count,
                "source_work_ids": formal["source_work_ids"],
                "goal_by_role": goal_by_role,
                "last_review_action_id": review_action_id,
                "next_status": target_status.value,
            }
            current_status = CollectionTaskStatus(task["status"])
            if current_status in TERMINAL_TASK_STATUSES or current_status in {
                CollectionTaskStatus.COMPLETING,
                CollectionTaskStatus.CANCELLING,
                CollectionTaskStatus.CLEANUP_REQUIRED,
            }:
                return {**progress, "task": task}
            previous_progress = (
                task.get("summary", {}).get("review_progress")
                if isinstance(task.get("summary"), dict)
                else None
            )
            if current_status is target_status and previous_progress == progress:
                return {**progress, "task": task}
            if current_status is target_status and target_status is not CollectionTaskStatus.AWAITING_REVIEW:
                return {**progress, "task": task}
            summary = {
                **(task.get("summary") if isinstance(task.get("summary"), dict) else {}),
                "review_progress": progress,
            }
            try:
                updated_task = self.store.compare_and_swap_collection_task(
                    task_id,
                    expected_state_version=int(task.get("state_version") or 0),
                    status=target_status.value,
                    summary=summary,
                    event_type="semantic_review_progress_recalculated",
                    action_id=review_action_id,
                    event_payload=progress,
                )
                return {**progress, "task": updated_task}
            except RuntimeError as exc:
                if "state version conflict" not in str(exc):
                    raise
        raise RuntimeError(f"collection task state remained contended after semantic review: {task_id}")

    def _pending_review_count(self, *, task_id: str, role_id: str) -> int:
        reviewed_source_work_ids = {
            str(review["source_work_id"])
            for review in self.store.list_collection_material_reviews(task_id=task_id, role_id=role_id)
        }
        materials_by_id = {
            str(material["id"]): material
            for material in self.store.list_collected_materials(task_id=task_id)
        }
        for candidate in self.store.list_collection_candidates(task_id=task_id):
            material_id = str(candidate.get("material_id") or "")
            if not material_id or material_id in materials_by_id:
                continue
            material = self.store.get_collected_material(material_id)
            if material is not None:
                materials_by_id[material_id] = material
        pending_source_work_ids = {
            str(material["source_work_id"])
            for material in materials_by_id.values()
            if str(material.get("transcript_text") or "").strip()
            and str(material.get("source_work_id") or "") not in reviewed_source_work_ids
        }
        return len(pending_source_work_ids)

    def _role_targets(
        self,
        *,
        task_id: str,
        task: dict[str, Any],
        fallback_role_id: str,
    ) -> dict[str, int]:
        role_targets = {
            str(item["role_id"]): int(item["target_count"])
            for item in self.store.collection_task_summary(task_id).get("roles", [])
        }
        if not role_targets:
            role_targets[fallback_role_id] = int(task.get("target_count_per_role") or 0)
        invalid = sorted(role_id for role_id, target in role_targets.items() if target < 1)
        if invalid:
            raise ValueError(
                f"collection task has no positive target for roles {', '.join(invalid)}: {task_id}"
            )
        if fallback_role_id not in role_targets:
            raise ValueError(f"role {fallback_role_id} has no target in collection task {task_id}")
        return role_targets

    def _require_task_role(self, *, task_id: str, task: dict[str, Any], role_id: str) -> None:
        linked_roles = {
            str(item["role_id"])
            for item in self.store.collection_task_summary(task_id).get("roles", [])
        }
        parsed = task.get("parsed") if isinstance(task.get("parsed"), dict) else {}
        parsed_role_id = str(parsed.get("role_id") or "").strip()
        if parsed_role_id:
            linked_roles.add(parsed_role_id)
        if linked_roles and role_id not in linked_roles:
            raise ValueError(f"role {role_id} is not linked to collection task {task_id}")

    def _review_for_action(self, *, task_id: str, action_id: str) -> dict[str, Any]:
        review = next(
            (
                item
                for item in self.store.list_collection_material_reviews(task_id=task_id)
                if item["action_id"] == action_id
            ),
            None,
        )
        if review is None:
            raise RuntimeError(f"succeeded review action has no immutable review record: {action_id}")
        return review

    @staticmethod
    def _validate_request(
        *,
        outcome: str,
        topic_direction: str,
        content_mechanism: str,
        evidence: dict[str, Any],
        reviewer: str,
        idempotency_key: str,
        fit_score: float | None,
        knowledge_subtype: str | None,
    ) -> dict[str, Any]:
        normalized_outcome = MaterialReviewOutcome(outcome).value
        normalized_topic = str(topic_direction or "").strip()
        normalized_mechanism = str(content_mechanism or "").strip()
        normalized_reviewer = str(reviewer or "").strip()
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_topic:
            raise ValueError("topic_direction is required")
        if not normalized_mechanism:
            raise ValueError("content_mechanism is required")
        if not normalized_reviewer:
            raise ValueError("reviewer is required")
        if not normalized_key:
            raise ValueError("idempotency_key is required")
        if not isinstance(evidence, dict) or not evidence:
            raise ValueError("evidence must be a non-empty object")
        reasons = evidence.get("reasons")
        if not isinstance(reasons, list) or not any(str(reason or "").strip() for reason in reasons):
            raise ValueError("evidence.reasons must contain at least one reason")
        if fit_score is not None and not 0 <= float(fit_score) <= 1:
            raise ValueError("fit_score must be between 0 and 1")
        return {
            "outcome": normalized_outcome,
            "topic_direction": normalized_topic,
            "content_mechanism": normalized_mechanism,
            "evidence": evidence,
            "reviewer": normalized_reviewer,
            "idempotency_key": normalized_key,
            "fit_score": float(fit_score) if fit_score is not None else None,
            "knowledge_subtype": str(knowledge_subtype or "").strip() or None,
        }
