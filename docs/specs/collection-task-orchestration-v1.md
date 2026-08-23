# Collection Task Orchestration v1

## Objective

This contract makes a business collection objective durable across many Codex
turns, remote searches, cursor continuations, author traversals, transcripts,
and semantic reviews. A remote run is evidence inside a task; it is never the
task boundary.

For the first production objective, completion means 20 distinct, unused,
reviewed primary `formal_rewrite_base` source works for the confirmed 宋立心理
role. Existing Channels runs with no `task_id` are historical experiments and
do not count unless an explicit reuse action links and re-reviews a material.

## Shared code contract

`src/mcn_ops/collection/task_contracts.py` is the authority for task states,
action types, frontier states, review outcomes, Channels acquisition-session
states, and legal task transitions. Parallel branches must import this module
instead of defining local strings.

## Additive storage contract

The explicit `collection_task_orchestration_v1` migration adds:

- state version and update metadata to `collection_tasks`;
- `collection_task_actions` for idempotent persisted decisions;
- `collection_task_events` for append-only transition audit;
- `collection_task_frontiers` for keyword and author cursors;
- `collection_material_reviews` for immutable full-transcript decisions;
- `channels_acquisition_sessions` and `channels_acquisition_events` for the
  Windows certificate/worker lease;
- `action_id` on `collection_runs` and review provenance on role matches.

All changes are additive. Existing rows remain readable. Applying the migration
twice must be safe, and the migration must finish with SQLite integrity and
foreign-key checks.

## Concurrency and idempotency

- Task state updates use a `state_version` compare-and-swap.
- A task has at most one claimed or running acquisition action.
- A worker has at most one non-terminal acquisition session.
- An idempotency key with the same input hash returns the prior action; the same
  key with a different input hash is a conflict.
- Candidate persistence and frontier advancement commit together. A failed
  action never advances its cursor.
- `max_pages` leaves a frontier open. Only an authoritative
  `source_exhausted=true` result exhausts it.

## Review transaction

A full-transcript review validates task membership, confirmed role version,
transcript hash, viral floor, material eligibility, and prior use. It then
atomically writes the immutable review, the task-scoped role decision, the
inventory classification, the action result, the event, and the recalculated
task state.

Legal outcomes are:

- formal rewrite base: accepted role, reviewed primary formal inventory;
- topic clue: reviewed non-primary topic inventory;
- rejected: rejected role, rejected non-primary topic inventory.

An automatic rules rejection remains evidence but cannot prevent a later
evidence-bearing full-transcript semantic acceptance.

## Windows acquisition-session contract

The Windows certificate and hardened worker are leased to the collection task,
not to one keyword. The initial implementation keeps the Mac Hub ephemeral per
provider action because the worker already reconnects. Windows owns the hard
lease and watchdog cleanup.

Open and renewal secrets travel through SSH stdin, never argv or SQLite. The
production cleanup script may stop only the pinned executable and remove only
the pinned SunnyNet certificate. Task completion and cancellation pass through
`completing` or `cancelling`; cleanup verification is required before a terminal
status is written.

## Integration ownership

Parallel branches own disjoint files. The primary agent alone integrates
`workflows.py` and `cli.py`, controls the real database, and performs Windows
live calls. Subagents use temporary SQLite databases and mock workers.
