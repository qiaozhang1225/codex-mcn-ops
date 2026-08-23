# WeChat Channels LAN Collection

Status: Mac provider, durable task orchestration, bounded materialization, semantic review, and task-bound Windows session control are implemented. Live operation still depends on the configured Windows machine, WeChat login/readiness, compatible worker build, LAN transport, and ASR credentials.

## Objective

Extend the Mac-hosted collection system with authenticated access to the operator's logged-in WeChat Channels environment on a dedicated Windows machine. Windows supplies bounded acquisition results; Mac remains the only owner of task state, media verification, transcription, semantic review, and SQLite writes.

## Ownership boundary

### Mac

- durable collection task, action, event, and frontier state;
- authenticated Hub and provider command dispatch;
- candidate/source persistence and completeness accounting;
- bounded materialization, media validation, ASR, understanding, and review;
- session lease orchestration and cleanup verification.

### Windows

- WeChat login and supported Channels page;
- pinned worker process and certificate/proxy integration;
- one authenticated Channels command at a time;
- short-lived media locator/decryption metadata;
- task-bound status and pinned cleanup actions.

### Prohibited

- Windows access to the Mac database or Git worktree over SMB;
- public exposure of the worker's loopback API or a public Hub;
- CAPTCHA/login/risk-control bypass;
- durable storage of cookies, Hub secrets, authorization headers, signed media URLs, or decode keys;
- automatic conversion of candidates into reviewed formal material;
- concurrent searches from one leased worker.

## Transport contract

The Windows worker initiates an authenticated WebSocket connection to the Mac Hub. Every handshake carries `X-Cloud-Secret` and `X-Client-ID`; the Hub uses constant-time secret comparison and a worker allowlist.

Production LAN transport requires WSS or an authenticated private overlay. Plain `ws://` is restricted to loopback unless an explicit controlled-PoC flag is supplied.

Protocol messages correlate the outer command ID and response request ID. The Hub retains only non-sensitive readiness state such as worker ID, hostname, versions, heartbeat time, and supported page capabilities.

Reconnect replaces the stale connection and fails pending calls explicitly. The provider does not silently replay a command whose persistence outcome is unknown.

## Provider actions

The Mac registry supports bounded operations for:

- keyword search and cursor continuation;
- author inspection and author works;
- work detail;
- durable public share-link resolution from a stable work ID;
- media locator/materialization;
- transcript extraction handoff.

Search normalization preserves stable work and author identity, public metrics, duration, source keyword, cursor, and provenance. HTML highlighting is removed without rewriting source text.

Before a Channels candidate becomes a formal material, the worker resolves the
stable work ID through `finderGetFeedH5Url`. Mac accepts only a matching public
`https://weixin.qq.com/sph/...` URL, marks it verified, and persists that URL as
the durable source link. Private locators, mismatched work IDs, and arbitrary
hosts fail closed.

## Pagination and completeness

Every search reports captured pages/items, `has_next`, `source_exhausted`, request satisfaction, and a stop reason.

- `source_exhausted=true` requires authoritative `has_next=false`.
- Reaching `max_pages`, an item cap, or a materialization cap is bounded sampling.
- `has_next=true` without a reusable marker fails as `cursor_missing`.
- The next marker and origin keyword are persisted in a task frontier before another iteration.

## Media and transcription

The preferred path is Mac-side media acquisition from a short-lived locator, prefix decryption compatible with the pinned worker, container validation, FFmpeg normalization, and Qwen ASR. Windows full-file materialization is a fallback when the locator cannot be consumed by Mac.

Locator values and decode keys remain in memory or ignored runtime state. Durable evidence contains stable work identity, observation metrics, media hash/verification result, and transcription provenance.

## Task execution

Initialize the additive schema once:

```bash
mcn db migrate-collection-task-orchestration-v1 --json
```

Create one bounded role-targeted task:

```bash
mcn collect task keyword \
  --topic '目标主题' --target-count 20 \
  --role-id role_xxx \
  --data-provider wechat_channels_remote \
  --transcription-provider aliyun \
  --max-search-pages 1 \
  --max-materials-per-iteration 5 \
  --json
```

Use `collect task plan` and `step` for subsequent strategy iterations. Use `collect task review` for each full-transcript semantic decision. Use `show`/`report` for progress and `session-status`, `session-recover`, or `session-close` for the leased Windows environment.

## Failure taxonomy

- unauthorized or unknown worker;
- worker disconnected or not ready;
- command timeout, invalid message/response, or remote error;
- cursor missing/stalled;
- public share-link resolution or work-ID verification failure;
- media locator expiry, download, decrypt, container, or ASR failure;
- stale task/action state or idempotency conflict;
- transcript/review mismatch;
- cleanup required or cleanup verification failure.

Failures remain explicit task/action evidence. The workflow never retries around a WeChat login challenge or reports a task complete while cleanup remains unverified.

## Acceptance invariants

- Mac is the only durable state owner.
- No credential or short-lived media secret appears in SQLite, reports, or Git.
- Every remote result is correlated to one persisted action and bounded input.
- Search candidates are persisted before selective materialization.
- Every formal Channels material has a verified public `weixin.qq.com/sph` source link.
- Semantic review, not automatic matching, controls formal-base progress.
- Completion/cancellation verifies the pinned worker and certificate are cleaned up.
