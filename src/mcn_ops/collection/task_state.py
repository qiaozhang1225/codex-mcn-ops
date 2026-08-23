from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .task_contracts import CollectionTaskStatus


@dataclass(frozen=True)
class RoleGoalProgress:
    role_id: str
    target_count: int
    qualified_count: int

    def __post_init__(self) -> None:
        if not self.role_id.strip():
            raise ValueError("role_id is required")
        if self.target_count < 1:
            raise ValueError("target_count must be >= 1")
        if self.qualified_count < 0:
            raise ValueError("qualified_count must be >= 0")

    @property
    def remaining_count(self) -> int:
        return max(self.target_count - self.qualified_count, 0)

    @property
    def satisfied(self) -> bool:
        return self.qualified_count >= self.target_count


def task_goal_satisfied(role_goals: Iterable[RoleGoalProgress]) -> bool:
    goals = list(role_goals)
    return bool(goals) and all(goal.satisfied for goal in goals)


def decide_open_task_status(
    *,
    role_goals: Iterable[RoleGoalProgress],
    pending_review_count: int,
    planned_acquisition_count: int,
    blocked_reason: str = "",
) -> CollectionTaskStatus:
    if pending_review_count < 0 or planned_acquisition_count < 0:
        raise ValueError("task counts must be non-negative")
    if task_goal_satisfied(role_goals):
        return CollectionTaskStatus.COMPLETING
    if blocked_reason.strip():
        return CollectionTaskStatus.BLOCKED
    if pending_review_count:
        return CollectionTaskStatus.AWAITING_REVIEW
    if planned_acquisition_count:
        return CollectionTaskStatus.READY_FOR_SEARCH
    return CollectionTaskStatus.AWAITING_STRATEGY
