# Codex MCN Ops PRD

## Product definition

`codex-mcn-ops` is a local, Codex-operated production system for one creator-operations owner. It turns a business content objective into an auditable sequence of source collection, transcript review, material classification, script creation, publish preparation, and result review.

The product surface is a Python CLI plus Markdown knowledge and runbooks. SQLite is the local operational ledger. Feishu is a delivery surface, not the source of truth. Logged-in browsers, the Windows WeChat worker, and Android apps are external execution environments.

## Primary user outcomes

1. Collect public Douyin or WeChat Channels evidence without confusing search candidates with approved material.
2. Know exactly which unused, reviewed materials can support one confirmed IP and content allocation.
3. Create a script through one linear Writer → Quality Review → Risk Review chain with traceable revisions.
4. Prepare a platform package and reach the final Android publish checkpoint without silently submitting.
5. Retain enough local evidence to explain what happened without committing runtime data or research artifacts to Git.

## Product capabilities

### Collection

- Douyin search, detail, author works, media access, and ASR through the signed-in Ego Lite/direct-provider path.
- WeChat Channels search, cursor continuation, author inspection, detail/media acquisition, and task-bound Windows session control through the authenticated LAN worker.
- Durable task actions, events, frontiers, semantic material reviews, and resumable task state.
- Explicit separation of source identity, observations, transcriptions, candidates, formal materials, role matches, and reviewed inventory.
- A formal WeChat Channels material retains a verified public `weixin.qq.com/sph` source link resolved from its stable work ID.

### Material governance

- Confirmed IP-role ownership and versioning.
- Evidence-bearing classification into formal rewrite base, topic clue, or rejection.
- One reviewed primary allocation per material/role, with optional secondary retrieval directions.
- Completion based on distinct, unused, reviewed primary formal bases—not raw result or transcript counts.

### Content creation

- Adaptation, half-original, and original modes.
- Formal stage packets and validated JSON submissions.
- Script Writer as the only viewer-copy owner.
- Read-only Quality Review and Risk Review bound to the latest Writer run and body hash.
- `贪、瞋、痴、慢、疑` evidence restricted to the first two spoken sentences, with exact body payoff.
- Publish formatting that cannot rewrite the double-reviewed body.

### Publishing and reporting

- Platform-specific validation and ADB job preparation for Douyin, Xiaohongshu, WeChat Channels, and Kuaishou.
- Evidence capture and a default stop before final submission.
- Manual verification snapshots, daily reports, and Feishu-ready payloads.

## Operating principles

- Fail closed on unavailable login, CAPTCHA, provider uncertainty, stale cursor, missing transcript, database integrity failure, or unverifiable cleanup.
- Store stable facts and audit state in SQLite; keep short-lived credentials and signed locators in memory or ignored runtime directories.
- Preserve source identity, metrics, traversal completeness, transcript provenance, and IP-fit evidence separately.
- Do not treat automatic rules or popularity as semantic approval.
- Do not let reviewers write replacement copy or let publish formatting modify approved copy.
- Keep the Git repository limited to code, durable contracts, current documentation, knowledge, and reusable workflows.

## Non-goals

- A browser-based operations center or always-on application server.
- Bypassing platform login challenges, CAPTCHA, signatures, or account risk control.
- Public exposure of the Windows worker or direct access from Windows to the Mac SQLite database.
- Automatic promotion of candidates into formal rewrite bases.
- Unattended final publishing without explicit operator authorization.
- Storing production databases, transcripts, media, research batches, or generated client deliverables in Git.

## Acceptance criteria

- A collection task can resume from persisted state and truthfully distinguish bounded sampling from source exhaustion.
- A reviewed material decision atomically preserves transcript evidence, role decision, inventory classification, and task progress.
- A creation task can complete the v3 chain and publish only the latest Writer body approved by both reviewers.
- Quality Review rejects third-sentence opening evidence, weak opening sentences, artificial drivers, sparse stimulus evidence, and missing body payoff.
- A Channels task can fail closed when its worker/session is unavailable and verify pinned cleanup before terminal completion or cancellation.
- A publish job can reach the final app checkpoint with logs and screenshots while stopping before submit by default.
- The repository remains reproducible from tracked code/docs while all operational data stays local.
