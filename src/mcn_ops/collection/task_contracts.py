from __future__ import annotations

from enum import StrEnum


class CollectionTaskStatus(StrEnum):
    READY_FOR_SEARCH = "ready_for_search"
    ACQUIRING = "acquiring"
    AWAITING_REVIEW = "awaiting_review"
    AWAITING_STRATEGY = "awaiting_strategy"
    BLOCKED = "blocked"
    COMPLETING = "completing"
    CANCELLING = "cancelling"
    CLEANUP_REQUIRED = "cleanup_required"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CollectionActionStatus(StrEnum):
    PLANNED = "planned"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class CollectionActionType(StrEnum):
    SEARCH_KEYWORD = "search_keyword"
    CONTINUE_KEYWORD = "continue_keyword"
    SEARCH_RELATED_KEYWORD = "search_related_keyword"
    INSPECT_AUTHOR = "inspect_author"
    COLLECT_AUTHOR_WORKS = "collect_author_works"
    REVIEW_MATERIAL = "review_material"
    COMPLETE_TASK = "complete_task"
    CANCEL_TASK = "cancel_task"


class CollectionFrontierType(StrEnum):
    KEYWORD = "keyword"
    AUTHOR = "author"


class CollectionFrontierStatus(StrEnum):
    OPEN = "open"
    EXHAUSTED = "exhausted"
    BLOCKED = "blocked"
    FAILED = "failed"


class ChannelsSessionStatus(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    DEGRADED = "degraded"
    CLEANUP_PENDING = "cleanup_pending"
    CLEANED = "cleaned"
    EXPIRED = "expired"
    CLEANUP_FAILED = "cleanup_failed"


class MaterialReviewOutcome(StrEnum):
    FORMAL_REWRITE_BASE = "formal_rewrite_base"
    TOPIC_CLUE = "topic_clue"
    REJECTED = "rejected"


TERMINAL_TASK_STATUSES = frozenset(
    {
        CollectionTaskStatus.COMPLETED,
        CollectionTaskStatus.CANCELLED,
        CollectionTaskStatus.FAILED,
    }
)

ACQUISITION_ACTION_TYPES = frozenset(
    {
        CollectionActionType.SEARCH_KEYWORD,
        CollectionActionType.CONTINUE_KEYWORD,
        CollectionActionType.SEARCH_RELATED_KEYWORD,
        CollectionActionType.INSPECT_AUTHOR,
        CollectionActionType.COLLECT_AUTHOR_WORKS,
    }
)

ALLOWED_TASK_TRANSITIONS: dict[CollectionTaskStatus, frozenset[CollectionTaskStatus]] = {
    CollectionTaskStatus.READY_FOR_SEARCH: frozenset(
        {
            CollectionTaskStatus.ACQUIRING,
            CollectionTaskStatus.BLOCKED,
            CollectionTaskStatus.CANCELLING,
        }
    ),
    CollectionTaskStatus.ACQUIRING: frozenset(
        {
            CollectionTaskStatus.AWAITING_REVIEW,
            CollectionTaskStatus.AWAITING_STRATEGY,
            CollectionTaskStatus.BLOCKED,
            CollectionTaskStatus.CANCELLING,
        }
    ),
    CollectionTaskStatus.AWAITING_REVIEW: frozenset(
        {
            CollectionTaskStatus.AWAITING_REVIEW,
            CollectionTaskStatus.AWAITING_STRATEGY,
            CollectionTaskStatus.COMPLETING,
            CollectionTaskStatus.BLOCKED,
            CollectionTaskStatus.CANCELLING,
        }
    ),
    CollectionTaskStatus.AWAITING_STRATEGY: frozenset(
        {
            CollectionTaskStatus.READY_FOR_SEARCH,
            CollectionTaskStatus.AWAITING_REVIEW,
            CollectionTaskStatus.COMPLETING,
            CollectionTaskStatus.BLOCKED,
            CollectionTaskStatus.CANCELLING,
        }
    ),
    CollectionTaskStatus.BLOCKED: frozenset(
        {
            CollectionTaskStatus.READY_FOR_SEARCH,
            CollectionTaskStatus.AWAITING_REVIEW,
            CollectionTaskStatus.AWAITING_STRATEGY,
            CollectionTaskStatus.CLEANUP_REQUIRED,
            CollectionTaskStatus.CANCELLING,
        }
    ),
    CollectionTaskStatus.COMPLETING: frozenset(
        {
            CollectionTaskStatus.COMPLETED,
            CollectionTaskStatus.CLEANUP_REQUIRED,
        }
    ),
    CollectionTaskStatus.CANCELLING: frozenset(
        {
            CollectionTaskStatus.CANCELLED,
            CollectionTaskStatus.CLEANUP_REQUIRED,
        }
    ),
    CollectionTaskStatus.CLEANUP_REQUIRED: frozenset(
        {
            CollectionTaskStatus.COMPLETING,
            CollectionTaskStatus.CANCELLING,
            CollectionTaskStatus.CLEANUP_REQUIRED,
        }
    ),
    CollectionTaskStatus.COMPLETED: frozenset(),
    CollectionTaskStatus.CANCELLED: frozenset(),
    CollectionTaskStatus.FAILED: frozenset(),
}


def is_terminal_task_status(status: str | CollectionTaskStatus) -> bool:
    return CollectionTaskStatus(status) in TERMINAL_TASK_STATUSES


def is_acquisition_action(action_type: str | CollectionActionType) -> bool:
    return CollectionActionType(action_type) in ACQUISITION_ACTION_TYPES


def require_task_transition(
    current: str | CollectionTaskStatus,
    target: str | CollectionTaskStatus,
) -> None:
    current_status = CollectionTaskStatus(current)
    target_status = CollectionTaskStatus(target)
    if target_status not in ALLOWED_TASK_TRANSITIONS[current_status]:
        raise ValueError(
            f"invalid collection task transition: {current_status.value} -> {target_status.value}"
        )
