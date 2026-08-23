from __future__ import annotations

import pytest

from mcn_ops.collection.task_contracts import (
    CollectionActionType,
    CollectionTaskStatus,
    is_acquisition_action,
    is_terminal_task_status,
    require_task_transition,
)


def test_task_contract_distinguishes_open_and_terminal_states() -> None:
    assert not is_terminal_task_status(CollectionTaskStatus.AWAITING_REVIEW)
    assert is_terminal_task_status(CollectionTaskStatus.COMPLETED)
    assert is_terminal_task_status(CollectionTaskStatus.CANCELLED)


def test_task_contract_requires_cleanup_before_completed() -> None:
    with pytest.raises(ValueError, match="awaiting_review -> completed"):
        require_task_transition(
            CollectionTaskStatus.AWAITING_REVIEW,
            CollectionTaskStatus.COMPLETED,
        )

    require_task_transition(
        CollectionTaskStatus.AWAITING_REVIEW,
        CollectionTaskStatus.COMPLETING,
    )
    require_task_transition(
        CollectionTaskStatus.COMPLETING,
        CollectionTaskStatus.COMPLETED,
    )


def test_task_contract_marks_only_remote_discovery_as_acquisition() -> None:
    assert is_acquisition_action(CollectionActionType.SEARCH_KEYWORD)
    assert is_acquisition_action(CollectionActionType.COLLECT_AUTHOR_WORKS)
    assert not is_acquisition_action(CollectionActionType.REVIEW_MATERIAL)
