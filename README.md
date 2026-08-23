# codex-mcn-ops

`codex-mcn-ops` is a Codex-first command-line workspace for creator operations. It keeps public-source collection, material review, content creation, publish preparation, and audit evidence in one local SQLite-backed workflow.

The repository contains product code, durable contracts, reusable knowledge, and operator runbooks. Runtime databases, credentials, media, transcripts, research notes, and generated content stay local.

## Current capabilities

- Douyin discovery and author traversal through the signed-in Ego Lite session.
- WeChat Channels acquisition through a task-bound Mac/Windows LAN workflow.
- Qwen ASR transcription and provider-neutral evidence persistence.
- Reviewed material inventory and role-specific allocation.
- Content Creation Workflow v3 with Script Writer, Quality Review, and Risk Review.
- Evidence-based `贪、瞋、痴、慢、疑` opening validation and body-payoff checks.
- Safe Android publishing preparation through ADB.
- Markdown and Feishu-ready delivery/report payloads.

The project intentionally has no web control center and no autonomous final publish. External login state, CAPTCHA, platform risk control, device UI changes, and Windows worker availability remain explicit operator gates.

## Documentation

- [Product requirements](docs/prd.md)
- [Technical specification](docs/technical-spec.md)
- [Documentation map](docs/README.md)
- [Material collection workflow](workflows/collect_materials.md)
- [Content Creation Workflow v3](workflows/create_script.md)
- [ADB publish workflow](workflows/adb_publish.md)
- [Reporting workflow](workflows/review_report.md)

## Setup

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
mcn init-db
mcn platforms
```

Local configuration belongs in `.env.local`. At minimum, real Douyin transcription requires `DASHSCOPE_API_KEY`; browser-backed Douyin operations reuse the signed-in Ego Lite session.

```bash
mcn collect douyin doctor \
  --provider direct \
  --transcription-provider aliyun \
  --json
```

## Collection entry points

Douyin keyword or author collection:

```bash
mcn collect task keyword \
  --topic '亲子关系' --target-count 10 \
  --data-provider direct --transcription-provider aliyun --json

mcn collect task author \
  --sec-uid SEC_UID --like-floor 10000 \
  --data-provider direct --transcription-provider aliyun --json
```

WeChat Channels collection uses the same durable task ledger but requires the configured Windows worker and task orchestration migration:

```bash
mcn db migrate-collection-task-orchestration-v1 --json

mcn collect task keyword \
  --topic '青春期亲子沟通' --target-count 20 \
  --role-id role_xxx \
  --data-provider wechat_channels_remote \
  --transcription-provider aliyun \
  --max-materials-per-iteration 5 --json
```

Continue with `collect task plan`, `step`, and evidence-bearing `review` commands. A task completes only from reviewed, unused, primary formal rewrite bases—not from raw search results or automatic matches.

## Creation entry point

```bash
mcn create task new \
  --role-id role_xxx \
  --topic '目标主题' \
  --goal '生成一条可发布口播' \
  --platform douyin \
  --target-count 1 \
  --creation-mode adaptation
```

For every formal stage, use `mcn create stage prepare`, let Codex produce the response JSON, then use `mcn create stage submit`. `create task run` is a deterministic fallback and is not formal agent output.

## Publishing

```bash
mcn publish prepare \
  --content-id content_xxx \
  --platform douyin \
  --device DEVICE_SERIAL

mcn publish push-assets --job-id job_xxx
mcn publish run --job-id job_xxx --device DEVICE_SERIAL
```

The default run stops before final submission. `--allow-submit --live` is reserved for an explicit human-approved publish action.

## Repository boundary

Tracked:

- `src/`, `tests/`, `scripts/` and migration code;
- `knowledge/`, `workflows/` and current product/technical documentation;
- stable protocol and data contracts.

Local-only:

- `data/`, `runs/` runtime artifacts;
- `research/` transcripts, investigation notes, generated scripts, images, and batch evidence;
- credentials, browser profiles, media, screenshots, and device-specific state.

Git history remains the archive for retired plans and superseded specifications. Do not keep obsolete execution plans beside current documentation.
