# WeChat Channels PoC Checkpoint — 2026-08-22

## Outcome

The Windows-tool-host architecture is the highest-confidence implementation
candidate and has passed its search, reconnect, detail, media-locator,
in-memory decryption, full media acquisition, and Mac-side ASR proofs.

The verified path is:

```text
Mac task/Hub
  -> authenticated outbound worker connection
  -> Windows WeChat Channels page
  -> search and detail API
  <- stable work data + short-lived media locator + decryption key
Mac
  -> ranged or full media fetch
  -> decrypt first 128 KiB
  -> FFmpeg audio extraction
  -> ASR and controlled candidate ingestion (database write remains disabled)
```

Screen recording is now a last-resort fallback, not the primary collection
design. A durable Mac provider, ephemeral media job, and ASR handoff are now
implemented and live-tested. This checkpoint still does not claim production
readiness: WSS transport and controlled candidate/database ingestion remain
separate implementation stages.

## Hosts and immutable inputs

| Field | Value |
| --- | --- |
| Mac LAN address | `192.168.3.120` |
| Windows LAN address | `192.168.3.112` |
| Windows host / user | `WORKSTATION` / `qiaoz` |
| Windows OS | Windows 11 Pro, x64, build `26200` |
| WeChat version | `4.1.11.55` |
| Worker hardware ID | `DEV-IyZU9C5DDMKxsY36` |
| Upstream repository | `https://github.com/nobiyou/wx_channel` |
| Upstream tag / commit | `v5.6.9` / `3dd74f0e21f7d9f6bdc5bec9338e433c57cbe8d0` |
| Hardened artifact | `wx_channel_cloud_hardened_v5.6.9.exe` |
| Hardened SHA-256 | `c5cff437248220edd113403987e6c3005136a23aee2b410e09736dd26bd2b0ea` |
| Windows artifact path | `D:\wx-channel-poc\wx_channel_cloud_hardened_v5.6.9.exe` |

The build is reproducible from the pinned source using
`scripts/build-wx-channel-worker.sh` and
`scripts/patch-wx-channel-worker.py`. The SunnyNet DLL inputs are also pinned by
commit and SHA-256 in the build script. The staged Windows SHA matched the Mac
build output.

## Security hardening proven live

The hardened worker changes the upstream behavior in four material ways:

1. TCP 2025, TCP 2026, and metrics bind to `127.0.0.1`, not all interfaces.
2. The configured `secret_token` is injected into the Channels page before the
   local API client starts.
3. Page and media URLs are sanitized before worker log output, and decryption
   keys are replaced by `<redacted>`.
4. Startup verifies the expected executable SHA and the explicit Windows
   Firewall inbound block before execution.

A nonempty local token was used in the live run. After the Channels page was
refreshed, its heartbeat reported `api_ready=true`, `supports_search=true`,
`supports_feed=true`, and `supports_profile=true`. This proves authenticated
page-to-worker communication; the earlier empty-token workaround is no longer
part of the design.

From the Mac, TCP 2025 and 2026 timed out while the worker was running. The
Windows listeners were independently observed on `127.0.0.1` only. The
additional firewall block `Codex-WxChannel-PoC-Block-Inbound` remains enabled.

## Search reliability matrix

The live matrix used five low-risk public keywords, four repetitions, and 20
Mac-initiated calls. No keyword was entered manually after the page became
ready.

| Metric | Result |
| --- | --- |
| Total calls | 20 |
| Successful / failed | 20 / 0 |
| Success rate | 100% |
| Second-page keywords | `AI`, `创业`, `职场沟通` |
| Search acceptance booleans | all `true` |

Two-page item counts were 96–98 for `AI` and 100 for both `创业` and
`职场沟通`. One-page samples returned 50 items for `读书` and `心理学`.
Every response still advertised more data, so the probe correctly reported
`stop_reason=max_pages` and `source_exhausted=false`; none was mislabeled as a
complete source traversal.

## Reconnect and failure evidence

The Mac Hub stayed running while the Windows worker task was stopped and
started. The Hub observed, in order:

```text
worker_ready_before_restart
worker_disconnected
worker_reconnected_and_search_passed
```

The post-reconnect search returned 48 items. Unit/contract tests separately
cover wrong Hub secret, unknown worker, not-ready heartbeat, pending-call
disconnect, timeout, invalid messages, response correlation, and
`cursor_missing` behavior. A live WeChat-page closure/reopen and a live wrong
secret run were deliberately not added after the successful matrix because
they would add disruption without extending the validated protocol behavior.
They remain operational acceptance checks for a resident deployment.

## Detail and direct-media proof

One `AI` search returned 48 candidates. The selected work had both
`object.id` and `objectNonceId`; the worker successfully called
`finderGetCommentDetail` through `key:channels:feed_profile`.

The detail response contained:

- an HTTPS locator on `finder.video.qq.com`;
- short-lived query credentials, retained only in memory;
- a decryption key, retained only in memory;
- duration `258734` ms and advertised size `159546575` bytes.

The Mac requested only bytes `0-4095`. The CDN returned HTTP `206`,
`Content-Type: video/mp4`, and a valid content-range response. The encrypted
sample did not expose an MP4 header. The Mac then generated the worker-compatible
ISAAC64 stream from the in-memory key, XOR-decrypted the sample, and recovered a
standard MP4 `ftyp` header. The Python ISAAC64 implementation was checked against
the pinned Go worker with a reference vector.

Therefore, the preferred media route is direct Mac download plus prefix
decryption. Windows full-file materialization is a fallback only if a future
locator becomes host-bound or CDN policy changes. No complete video or audio
file was downloaded in this PoC.

## Data and log boundary

- Probe output contains stable work evidence and locator metadata only; it does
  not contain locator values, token values, cookies, session buffers, or keys.
- The media probe persists neither encrypted nor decrypted media.
- No Mac SQLite write path is imported by the probe executables.
- The worker's raw logs and internal test database were cleared after the run.
- Formal material ingestion was not attempted.

## Real IP workflow proof

A live business-oriented run used five Song Li Psychology positioning keywords:
`青春期孩子`, `孩子厌学`, `孩子沉迷手机`, `亲子沟通`, and `父母焦虑`.
The Mac issued all five requests, received 250 candidates (246 unique), and
found 227 candidates between 20 and 300 seconds. Every search stopped at the
configured one-page boundary with `source_exhausted=false`.

Candidate `14990314353584704109` was then resolved to a fresh media lease,
downloaded and decrypted on the Mac, verified as MP4, normalized through
FFmpeg, and transcribed by `qwen3-asr-flash`. The 260-second transcription cost
was estimated at CNY 0.0572. No formal material or candidate row was persisted.

The complete evidence and shortlist are recorded in
`docs/specs/songli-wechat-channels-live-search-2026-08-22.md`.

## Post-test cleanup

Cleanup was verified independently after the worker stopped:

- no worker process and no TCP 2025/2026 listener;
- SunnyNet thumbprint `D70CD039051F77C30673B8209FC15EFA650ED52C`
  count is zero in both `CurrentUser\Root` and `LocalMachine\Root`;
- cloud mode is disabled and `cloud_hub_url`, `cloud_secret`, and
  `secret_token` are empty in the Windows config;
- temporary certificate, inspection, refresh, and registration files were
  removed;
- temporary scheduled tasks were removed; `CodexWxChannelPoC` remains `Ready`
  with no trigger;
- the upstream unhardened executable was removed, while the pinned hardened
  executable remains for the next development stage;
- worker logs and the worker's test `records.db` were cleared or removed;
- no media file exists in the worker download directory;
- Clash WinINET remains `127.0.0.1:7890`; WinHTTP remains direct;
- the explicit inbound firewall block remains enabled.

The deletions are not recoverable except by rebuilding or rerunning the PoC.

## Current checkpoint and next gates

Current status:

```text
search_matrix_passed
page_auth_hardened
restart_reconnect_passed
detail_api_passed
direct_encrypted_media_and_mac_decryption_passed
mac_provider_and_asr_handoff_passed
candidate_database_ingestion_not_enabled
```

The next safe implementation sequence is:

1. run a second, narrower Song Li keyword pass and batch-transcribe 5–10
   high-fit candidates;
2. add WSS or an authenticated private overlay before resident unattended use;
3. run live page-not-ready, WeChat restart, locator-expiry, interrupted download,
   and retry/idempotency tests;
4. enable candidate-only database ingestion behind a feature flag, with no
   automatic promotion to formal materials;
5. require content and professional review before a candidate can become a
   formal rewrite source.
