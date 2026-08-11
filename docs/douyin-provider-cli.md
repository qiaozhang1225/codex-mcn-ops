# Douyin Provider CLI

This project can collect Douyin metadata without MXNZP and can send extracted
audio directly to Alibaba Cloud Model Studio for transcription.

## Provider policy

- `direct`: use the signed-in `ego-browser` session for video search and detail, then call
  Alibaba Cloud directly for ASR. No paid data aggregation API.
- `mxnzp`: preserve the existing paid provider for compatibility.
- `auto`: try `direct` first. MXNZP is disabled unless
  `--allow-paid-fallback` is explicitly supplied.
- `aliyun`: use `qwen3-asr-flash` for audio up to 5 minutes and 10 MB, otherwise
  use asynchronous `qwen3-asr-flash-filetrans`.

Direct Douyin access is inherently less stable than a commercial aggregation
API. Empty bodies, CAPTCHA pages, expired cookies, and endpoint changes are
reported as typed errors. They do not silently trigger a paid fallback.

## Configuration

Put local secrets in `.env.local`:

```dotenv
DOUYIN_COOKIE="..."
DOUYIN_DIRECT_MODE="browser"
DASHSCOPE_API_KEY="..."
DASHSCOPE_WORKSPACE_ID="..."
DASHSCOPE_REGION="cn-beijing"
```

Optional runtime settings:

```dotenv
DOUYIN_TIMEOUT_SECONDS="30"
DOUYIN_EMPTY_PAGE_RETRIES="1"
DOUYIN_BROWSER_EXECUTABLE="ego-browser"
DOUYIN_BROWSER_WAIT_SECONDS="8"
DOUYIN_BROWSER_TIMEOUT_SECONDS="45"
DOUYIN_BROWSER_MAX_PAGE_LIMIT="100"
DOUYIN_BROWSER_SCROLL_WAIT_SECONDS="1.5"
MCN_ASR_LANGUAGE="zh"
MCN_ASR_ENABLE_ITN="false"
MCN_ASR_CACHE_PATH="data/transcription-cache.sqlite"
```

The ASR cache key includes the normalized audio SHA-256, provider, model, and
recognition options. Therefore a second CLI process can reuse the transcript
without another paid request.

Long asynchronous task IDs and any uploaded media URL are stored in the same
SQLite file. A polling timeout keeps both records so a later CLI process can
resume the existing task instead of submitting another billed job. Uploaded
media is cleaned only after an explicit terminal result.

## Commands

```bash
# Local configuration and dependency check; does not call paid APIs.
mcn collect douyin doctor --provider direct --transcription-provider aliyun --json

# Provider-neutral data commands.
mcn collect douyin detail 'https://www.douyin.com/video/...' --provider direct --json
mcn collect douyin search-video --keyword '心理' --provider direct \
  --max-pages 3 --max-items 60 --json
mcn collect douyin search-user --keyword '思丞说' --provider direct --json
mcn collect douyin user-posts --sec-uid '...' --provider direct \
  --max-pages 3 --max-items 60 --json

# Detail -> media extraction -> Alibaba Cloud ASR -> normalized transcript.
mcn collect douyin transcribe 'https://www.douyin.com/video/...' \
  --provider direct --transcription-provider aliyun --json

# Explicitly permit the legacy paid provider only for eligible direct failures.
mcn collect douyin detail 'https://www.douyin.com/video/...' \
  --provider auto --allow-paid-fallback --json
```

The high-level collection workflows also accept `direct` and `auto`:

```bash
mcn collect task keyword --topic '亲子关系' --target-count 10 \
  --tool-provider direct --transcription-provider aliyun --json

mcn collect task author --sec-uid '...' --data-provider direct \
  --transcription-provider aliyun --json
```

## Operational gates

1. Keep ego lite logged in to Douyin. Browser-backed search, detail, and author
   sampling reuse that session and do not inject `.env.local` cookies into ego.
2. Run `doctor` before a batch.
3. Test one known video before expanding to search or author pagination.
4. Enable `--allow-paid-fallback` only for a run with an approved MXNZP budget.
5. Compare a small transcript sample against the source audio before production
   ingestion.

Browser-backed keyword search and author works support bounded pagination with
`--max-pages` and `--max-items`. The provider reuses the signed-in page's native
request layer so the current Douyin security runtime signs each new `offset` or
`max_cursor`; it does not copy a static browser signature. Responses are
deduplicated by work ID and page cursor. If a signed page request fails or a
cursor stalls, the provider raises `Douyin browser did not expose the requested
next page` instead of returning a partial batch as complete.

`--max-pages 0` requests traversal until `paging.has_next=false`, subject to
`DOUYIN_BROWSER_MAX_PAGE_LIMIT` (default 100). Claim a complete author history
only when the returned paging state proves exhaustion. A run that reaches the
configured page cap while `has_next=true` fails closed.

Direct HTTP pagination is diagnostic-only and currently triggers Douyin risk
control with the available local static signer. Production pagination must use
the browser-backed native signing path, and must not switch to MXNZP without
explicit paid approval.

The default CLI does not configure an object-storage uploader. Public Douyin
audio URLs can be submitted directly to file transcription; long local files or
long videos that must first be normalized require an injected HTTPS uploader
and cleanup callback. Keep that path disabled until OSS credentials and a
private-bucket lifecycle policy are configured and live-tested.

`DOUYIN_DIRECT_MODE=browser` is the default because current Douyin Web detail
requests depend on browser-generated runtime signatures. `http` remains an
explicit diagnostic mode, but is not the production detail path. A verification
page fails with a typed risk-control error and never silently calls MXNZP.

Alibaba Cloud Model Studio documents both the synchronous OpenAI-compatible
Qwen3-ASR request and the asynchronous submit/poll flow for file transcription.
The code keeps those transports injectable so all default tests run without
network access or charges.
