from __future__ import annotations

import pytest

from mcn_ops.collection.task_contracts import CollectionTaskStatus
from mcn_ops.collection.task_state import (
    RoleGoalProgress,
    decide_open_task_status,
    task_goal_satisfied,
)


def test_task_goal_requires_every_role_to_reach_its_target() -> None:
    goals = [
        RoleGoalProgress("role-a", target_count=20, qualified_count=20),
        RoleGoalProgress("role-b", target_count=2, qualified_count=1),
    ]

    assert task_goal_satisfied(goals) is False
    assert goals[1].remaining_count == 1


def test_task_state_prioritizes_goal_then_block_then_review_then_action() -> None:
    incomplete = [RoleGoalProgress("role-a", target_count=20, qualified_count=3)]
    complete = [RoleGoalProgress("role-a", target_count=20, qualified_count=20)]

    assert decide_open_task_status(
        role_goals=complete,
        pending_review_count=1,
        planned_acquisition_count=1,
        blocked_reason="worker offline",
    ) == CollectionTaskStatus.COMPLETING
    assert decide_open_task_status(
        role_goals=incomplete,
        pending_review_count=1,
        planned_acquisition_count=1,
        blocked_reason="worker offline",
    ) == CollectionTaskStatus.BLOCKED
    assert decide_open_task_status(
        role_goals=incomplete,
        pending_review_count=1,
        planned_acquisition_count=1,
    ) == CollectionTaskStatus.AWAITING_REVIEW
    assert decide_open_task_status(
        role_goals=incomplete,
        pending_review_count=0,
        planned_acquisition_count=1,
    ) == CollectionTaskStatus.READY_FOR_SEARCH
    assert decide_open_task_status(
        role_goals=incomplete,
        pending_review_count=0,
        planned_acquisition_count=0,
    ) == CollectionTaskStatus.AWAITING_STRATEGY


def test_role_goal_rejects_invalid_counts() -> None:
    with pytest.raises(ValueError, match="target_count"):
        RoleGoalProgress("role-a", target_count=0, qualified_count=0)
