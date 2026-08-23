# WeChat Channels Task-Centered Collection v2

## Product outcome

The unit of work is a business objective, not one remote search call or one
certificate installation cycle.

Example objective:

> Collect 20 reviewed viral scripts that can serve as formal rewrite bases for
> the 宋立心理 IP.

The objective is complete only when 20 distinct, unused source works are classified as
reviewed, primary `formal_rewrite_base` inventory for the target role. Search
results, transcripts, locally eligible materials, and automatic role matches
are intermediate evidence and never satisfy the objective by themselves.

## Three different lifecycles

### 1. Collection task

The durable Mac-side objective. It may span many Codex turns, keywords, search
pages, source-account expansions, transcripts, and review decisions.

Terminal states:

- `completed`: the reviewed formal-base target is satisfied;
- `cancelled`: the user explicitly stops the objective;
- `failed`: a non-recoverable error prevents further progress.

Open states:

- `ready_for_search`: another planned search iteration is available;
- `awaiting_review`: new transcripts require semantic role and inventory review;
- `awaiting_strategy`: Codex must choose pagination, a new keyword, or an author
  expansion before dispatching another Windows action;
- `blocked`: an external prerequisite such as unavailable WeChat login needs
  attention.

### 2. Strategy iteration

One bounded decision-action-observation loop inside a task:

1. choose one keyword, cursor continuation, or source author;
2. dispatch one bounded Windows operation;
3. persist all candidates and traversal evidence on the Mac;
4. materialize only a limited number of high-value candidates;
5. review full transcripts for role fit and formal-base eligibility;
6. update task progress and choose the next action.

For WeChat Channels, one CLI invocation performs at most one search iteration
and materializes at most five candidates by default. This prevents a single
keyword from consuming the whole objective or triggering uncontrolled ASR
work before Codex reviews the evidence.

### 3. Windows acquisition session

The Windows worker, SunnyNet root certificate, WeChat interception state, and
Mac Hub form a leased acquisition session. The session is not tied to a single
keyword request.

The certificate and worker may remain active across strategy iterations while
the collection task is open. Cleanup is required when the task completes or is
cancelled, and on a safety lease timeout that is not renewed by an active task.
Cleanup must remain pinned to the known certificate thumbprint and worker
binary; it must not remove unrelated certificates or processes.

## Goal accounting

The task report exposes separate counters:

- `saved_count`: material results with transcripts and persisted understanding;
- `accepted_role_match_count`: automatic role-match results;
- `qualified_formal_base_count`: distinct available reviewed primary formal rewrite bases;
- `remaining_count`: target minus `qualified_formal_base_count`.

Only `qualified_formal_base_count` controls task completion. Every transcript
created for a role-targeted task enters the semantic review queue even when the
rules-based automatic matcher rejected it. Automatic rejection is evidence,
not a substitute for transcript-level Codex review.

## Strategy actions

The task controller must eventually support these persisted actions:

- `search_keyword(keyword, max_pages, cursor)`;
- `continue_keyword(keyword, cursor)`;
- `review_material(material_id, role_decision, inventory_decision, evidence)`;
- `search_related_keyword(keyword, reason)`;
- `inspect_author(author_id, reason)`;
- `collect_author_works(author_id, like_floor, traversal_limit)`;
- `complete_task()` and `cancel_task(reason)`.

Every action records its reason, input boundary, result counts, traversal
completeness, and the next recommended decision. Repeated searches must reuse
the same `collection_task.id` while creating separate `collection_runs`.

## Current implemented slice

The Mac workflow now:

- reports progress against reviewed formal bases instead of raw saved materials;
- keeps an unmet role-targeted task open with `completed_at = NULL`;
- pauses Channels collection after one bounded keyword iteration;
- caps materialization before semantic review;
- includes automatically rejected materials in the task semantic review queue;
- resumes the same task instead of representing each search as a new objective.

## Explicit remaining gates

The following are not yet production-complete:

1. The Channels provider supports keyword search and work detail/media, but no
   production author-home traversal command is wired into the Mac provider.
2. Semantic review decisions still need a first-class transactional task action
   that can record an evidence-bearing role decision and inventory
   classification together.
3. The Windows certificate/worker session needs a task-bound lease controller,
   heartbeat renewal, and automatic pinned cleanup on terminal task states.
4. Keyword continuation must persist the real Channels cursor as a reusable
   strategy action rather than treating `max_pages` as the end of the task.
5. The controller needs account-ranking policy so repeated high-quality authors
   can trigger author-home inspection without blindly expanding every account.

Until these gates are implemented and tested, a search run may prove transport
and persistence, but it must not be described as completing a 20-script formal
collection objective.
