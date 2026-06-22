# codex-mcn-ops

Codex-native MCN operations for IP building and matrix publishing.

This project replaces `opc-mcn-center` with a smaller execution model:

- Codex is the operating brain.
- SQLite is the local audit ledger.
- Feishu is the human collaboration and delivery surface.
- Android publishing runs through ADB against real logged-in apps.

It intentionally does not include a React/FastAPI operations center, private web publishing APIs, AiToEarn API/MCP integration, or a complex task-state product layer.

## Quick Start

```bash
python -m pip install -e .
mcn init-db
mcn platforms
mcn adb doctor
```

Run a local material-collection rehearsal without external API credentials:

```bash
mcn collect role upsert \
  --name "知识型老师" \
  --positioning "解释型口播" \
  --search-keyword 知识型口播

mcn collect run \
  --topic 知识型口播 \
  --target-count 2 \
  --tool-provider mock \
  --like-floor 1

mcn collect report --run-id crun_xxxxxxxxxxxx
mcn material promote --material-id mat_xxxxxxxxxxxx --platform douyin
```

Run the reusable high-level collection task entry:

```bash
mcn collect task keyword --topic 财运 --target-count 30 --tool-provider mxnzp
mcn collect task author --name "娜说智慧" --like-floor 10000
mcn collect task discover-authors --min-appearances 2 --like-floor 10000 --top-authors 10

mcn collect task show --task-id ctask_xxxxxxxxxxxx
mcn collect task report --task-id ctask_xxxxxxxxxxxx
mcn collect task resume --task-id ctask_xxxxxxxxxxxx
```

The task layer creates `collection_tasks`, links all search/materialization runs through `collection_runs.task_id`, preserves existing materials by `work_id/source_url/title+author`, and runs material understanding by default. Material understanding is treated as the searchable metadata layer for later IP matching and rewrite work.

For real Douyin material collection, set `MXNZP_APP_ID` and `MXNZP_APP_SECRET` in `.env.local`, start with `--target-count 1`, and review the resulting material before expanding collection.

Create a content package and a safe publish job:

```bash
mcn content create \
  --title "测试标题" \
  --body "测试正文" \
  --media /absolute/path/video.mp4 \
  --cover /absolute/path/cover.jpg \
  --hashtag 知识型口播

mcn publish prepare \
  --content-id content_xxxxxxxxxxxx \
  --platform douyin \
  --device YOUR_ADB_SERIAL

mcn publish run --job-id job_xxxxxxxxxxxx --dry-run
```

For a real connected phone flow, keep the default safety stop:

```bash
mcn publish push-assets --job-id job_xxxxxxxxxxxx
mcn publish run --job-id job_xxxxxxxxxxxx --device YOUR_ADB_SERIAL
```

The runner stops before final submit by default. Use live publish only after an explicit manual decision:

```bash
mcn publish run --job-id job_xxxxxxxxxxxx --allow-submit --live
```

Generate a local daily report:

```bash
mcn report daily --output runs/daily-report.md
```

## V1 Platforms

- `douyin`
- `xhs`
- `wechat_channels`
- `kwai`

Each adapter currently supplies package names, content validation, audit steps, screenshots, and manual calibration checkpoints. Device-specific tap/select/type flows should be added only after running dry-runs against the actual phone/app versions.

## Runtime State

- SQLite ledger: `data/mcn_ops.sqlite`
- Run artifacts: `runs/<job_id>/`
- Local secrets: `.env.local` or platform app login on the phone, never committed
- MXNZP credentials: `MXNZP_APP_ID`, `MXNZP_APP_SECRET`, optional `DOUYIN_COOKIE`
- Douyin anonymous cookie probe: `mcn collect douyin-cookie --json`
- Douyin logged-in cookie flow: `mcn collect douyin-login-cookie --write-env --json`; author `user_post` can also use `--login-cookie` when `DOUYIN_COOKIE` is missing.
- Douyin author expansion: `mcn collect author expand --name "娜说智慧" --sort-type 1 --max-pages 0 --json`
- Douyin author materialization: `mcn collect author materialize --name "娜说智慧" --top 5 --json`
- High-level keyword collection: `mcn collect task keyword --topic 财运 --target-count 30 --tool-provider mxnzp`
- High-level author collection: `mcn collect task author --name "娜说智慧" --like-floor 10000`
- High-level database author discovery: `mcn collect task discover-authors --min-appearances 2 --top-authors 10 --like-floor 10000`

## Local Inspection

Use DB Browser for SQLite to inspect the local ledger when reviewing collected material, raw MXNZP payloads, and publish logs:

```text
/Applications/DB Browser for SQLite.app
```

Open:

```text
data/mcn_ops.sqlite
```

## Safety Rules

- Real publishing is opt-in.
- `stop_before_submit` is the default.
- DeepSeek is intentionally not used. Collection defaults to `codex-agent/gpt-5.5/success` material understanding. `local-rules/material-understanding-rules-v2` is only an explicit fallback draft for exceptional cases.
- ADB screenshots/UI dumps are stored for every major step.
- Platform accounts are assumed to be logged in on the Android phone.
- If UI XML is insufficient, hand off to Codex Computer Use for the visible phone/scrcpy session rather than using private platform APIs.
