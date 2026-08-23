# Collection Task Orchestration v1

Status: implemented and covered by migration, store, task-engine, workflow, CLI, and integration tests.

## Objective

A collection task represents one durable business objective across many searches, cursors, author traversals, transcripts, reviews, and Codex turns. A provider call or `collection_run` is evidence inside the task, never the task boundary.

For a role-targeted task, completion is based on distinct, unused, reviewed primary `formal_rewrite_base` source works. Raw candidates, transcripts, material eligibility, and automatic role matches are intermediate counters.

## Code authority

- States, action types, frontier types, review outcomes, and legal transitions: `src/mcn_ops/collection/task_contracts.py`.
- Execution and materialization: `src/mcn_ops/collection/task_engine.py` and `workflows.py`.
- Persistence: `src/mcn_ops/store.py`.
- Additive schema: `src/mcn_ops/migrations/collection_task_orchestration_v1.py`.

## Storage contract

The migration adds task state/version metadata and these tables:

- `collection_task_actions`: persisted, idempotent decisions and bounded inputs;
- `collection_task_events`: append-only task transition audit;
- `collection_task_frontiers`: keyword/author cursor state and exhaustion evidence;
- `collection_material_reviews`: immutable full-transcript semantic decisions;
- `channels_acquisition_sessions`: task-bound Windows session leases;
- `channels_acquisition_events`: worker/session lifecycle evidence.

It also links `collection_runs` to actions and adds review provenance to role decisions. Applying the migration twice is safe and every successful run finishes with integrity and foreign-key checks.

## State model

Open task states distinguish executable work, semantic review, strategy choice, external blocking, and cleanup. Terminal completion or cancellation is written only after required external cleanup succeeds.

State changes use compare-and-swap `state_version`. A stale writer cannot overwrite a newer decision.

## Action model

Supported persisted actions include:

- keyword search and cursor continuation;
- related-keyword search;
- author inspection and author-work collection;
- transcript-level material review;
- task completion and cancellation.

An idempotency key is bound to the normalized input hash. Reusing a key with the same input returns the prior action; reusing it with different input is a conflict. A task has at most one claimed/running acquisition action.

Candidate persistence, source observations, action outcome, and frontier advancement commit together. A failed action never advances its cursor. `max_pages` or another policy cap leaves the frontier open; only authoritative `has_next=false` / `source_exhausted=true` evidence exhausts it.

## Semantic review transaction

`mcn collect task review` validates:

- task and material membership;
- confirmed role and role version;
- current transcript hash;
- viral floor and material eligibility;
- prior role-specific use;
- evidence-bearing outcome and reason.

It then atomically records the immutable review, task-scoped role decision, inventory classification, action result, task event, and recalculated progress.

Legal outcomes:

- `formal_rewrite_base`: accepted role decision and reviewed primary inventory;
- `topic_clue`: reviewed non-primary inventory for discovery only;
- `rejected`: rejected role decision and non-primary rejected inventory.

Automatic rules are evidence, not semantic authority. A rules rejection cannot prevent a later full-transcript Codex review.

## Channels session lease

The Windows certificate, worker, WeChat readiness, and Mac Hub form one task-bound acquisition session. The lease may span bounded strategy iterations.

- One worker has at most one non-terminal session.
- Secrets travel through process input/environment and never command arguments or SQLite.
- Cleanup targets only the pinned executable and certificate thumbprint.
- Completion/cancellation passes through cleanup-required states until verification succeeds.
- Session status, recovery, and close operations are explicit CLI commands.

## Acceptance invariants

- Replaying the same action is idempotent.
- A stale state version fails instead of overwriting progress.
- Cursor advancement cannot survive a failed persistence transaction.
- Bounded sampling is never reported as source exhaustion.
- A review cannot bind to a stale or different transcript.
- Task completion cannot be inferred from raw result, transcript, or automatic-match counts.
- Channels terminal state cannot bypass verified pinned cleanup.
