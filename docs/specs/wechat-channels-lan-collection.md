# WeChat Channels LAN Collection v1

Status: Phase 1 proof complete; production provider and ingestion remain gated.

## Objective

Extend the existing Mac-hosted collection workflow with a Windows WeChat
Channels acquisition worker. Codex and `mcn` remain on the Mac. The Windows
machine supplies authenticated WeChat search and detail data but never opens or
writes the Mac SQLite database.

The first proof must establish this chain without UI search and without formal
material persistence:

```text
Mac probe -> authenticated WebSocket command -> Windows worker -> WeChat page
          <- correlated paged search response <-
```

## System boundary

### Mac owns

- collection task orchestration;
- durable task and provider-call state;
- candidate selection and completeness reporting;
- media verification, ASR, understanding, and SQLite writes;
- the WebSocket Hub that accepts a configured Windows worker.

### Windows owns

- the WeChat login and supported Channels page;
- the third-party client bridge, root certificate, and proxy;
- execution of one WeChat command at a time;
- short-lived media locator and decryption-key acquisition;
- full media materialization only when a signed URL cannot be used by Mac.

### Explicit exclusions

- no SQLite access over SMB or another network filesystem;
- no inbound exposure of the third-party worker HTTP API;
- no public cloud Hub;
- no CAPTCHA, login challenge, or risk-control bypass;
- no persistence of cookies, `urlToken`, `decodeKey`, signed media URLs, or
  authorization headers;
- no automatic classification as a reviewed formal rewrite base;
- no multi-worker scheduling or concurrent WeChat searches in v1.

## Transport

The Windows project already implements an outbound WebSocket connector. The Mac
Hub therefore follows its existing wire envelope rather than defining a second
incompatible protocol.

```json
{
  "id": "clv1-<uuid>",
  "type": "command",
  "client_id": "windows-01",
  "payload": {
    "action": "search_videos",
    "data": {
      "keyword": "AI",
      "next_marker": ""
    }
  },
  "timestamp": 1787328000
}
```

The response is correlated by `payload.request_id`, which must equal the outer
command `id`. IDs prefixed with `clv1-` identify this protocol version.

Supported worker message types are:

- `heartbeat`: declares worker identity and page capabilities;
- `response`: resolves one pending Mac command;
- `sync_data`: ignored in the search-only proof;
- binary gzip frames: decoded because the worker compresses larger messages.

Supported Mac commands for v1 are:

- `search_videos`;
- `api_call`, reserved for video detail after the search gate passes;
- `download_video`, reserved for media materialization after the detail gate.

## Authentication and network policy

- The worker initiates the connection to the Mac Hub.
- Every handshake must contain `X-Cloud-Secret` and `X-Client-ID`.
- Secrets are compared in constant time and are read from an environment
  variable, never a command-line argument.
- A configured worker allowlist rejects unknown client IDs.
- Production LAN binding requires WSS. Plain `ws://` is permitted only on a
  loopback address unless the operator explicitly enables an insecure PoC.
- Only one live connection is retained per worker ID. A reconnect replaces the
  stale connection and fails its pending calls.
- The third-party worker API remains bound to Windows loopback. Windows Firewall
  does not expose it to the LAN.

## Search contract

Mac sends:

```json
{
  "keyword": "AI",
  "next_marker": "",
  "page": 1,
  "page_size": 20
}
```

Windows returns normalized search data:

```json
{
  "list": [],
  "next_marker": "opaque marker",
  "has_more": true
}
```

The Mac probe reports:

- `captured_pages`;
- `captured_items`;
- `has_next`;
- `source_exhausted`;
- `request_satisfied`;
- `stop_reason`.

`source_exhausted=true` is valid only when the worker returns
`has_more=false`. Reaching `max_pages` is a bounded sample and must report
`source_exhausted=false`. `has_more=true` without a next marker fails closed as
`cursor_missing`.

## Heartbeat readiness

The Hub retains only non-sensitive capability state:

- worker ID and hostname;
- worker and WeChat bridge version;
- last heartbeat timestamp;
- `api_ready`;
- `supports_search`;
- `supports_feed`;
- `supports_profile`;
- supported page methods.

Search is rejected before dispatch when the worker is disconnected or its
heartbeat says search is unavailable.

## Failure taxonomy

- `unauthorized_worker`
- `worker_disconnected`
- `worker_not_ready`
- `command_timeout`
- `invalid_message`
- `invalid_response`
- `remote_error`
- `cursor_missing`

Failures are terminal for the individual call. The probe does not loop around a
login challenge or retry indefinitely.

## Search-only acceptance gate

The Windows live test may proceed only after local protocol tests pass. The live
gate requires:

1. five public keywords and at least twenty search calls;
2. at least three keywords with a verified second page;
3. no manual keyword entry in WeChat after the worker is ready;
4. correct request/response correlation for every returned message;
5. explicit `worker_not_ready` behavior when the page is unavailable;
6. successful reconnect after a worker restart;
7. no secrets or signed media locators in probe output;
8. no Mac SQLite writes during the proof.

Passing this gate authorizes implementation of the Mac remote provider and
video-detail phase. It does not authorize formal database ingestion or a claim
of production readiness.

## Later-phase source package

After the search gate passes, the provider will normalize stable fields as:

```text
source_platform     = wechat_channels
work_id             = object.id
platform_author_id  = contact.username
author_name         = contact.nickname
duration_ms         = objectDesc.media[].durationMs
public_metrics      = likes/favorites/comments/shares
source_link         = stable share or feed URL
```

Signed URLs and decryption material exist only in the in-memory media job. The
verified default is Mac-side media fetch followed by ISAAC64/XOR decryption of
the first 128 KiB and FFmpeg audio extraction. The database stores the stable
work identity, observation metrics, verified media hash, and transcription
evidence.
