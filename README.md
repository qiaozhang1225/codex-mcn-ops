# codex-mcn-ops

`codex-mcn-ops` is a Codex-first command-line workspace for creator operations. Its new writing direction is original scripts grounded in an IP's knowledge, experience, and complete external examples. Collection, publishing preparation, and audit history remain in one local SQLite-backed workspace.

The repository contains product code, durable contracts, reusable knowledge, and operator runbooks. Runtime databases, credentials, media, transcripts, research notes, and generated content stay local.

## Current capabilities

- Douyin discovery and author traversal through the signed-in Ego Lite session.
- WeChat Channels acquisition through a task-bound Mac/Windows LAN workflow.
- Qwen ASR transcription and provider-neutral evidence persistence.
- Reviewed material inventory and role-specific allocation.
- `mcn original` private source library, scoped retrieval, writing packets, candidate drafts, and exact-copy acceptance.
- Manual same-account, same-platform, same-post-age organic-view reports and recorded human iteration decisions.
- Historical Content Creation Workflow v3 for existing adaptation tasks; its opening validation does not apply to the new original path.
- Safe Android publishing preparation through ADB.
- Markdown and Feishu-ready delivery/report payloads.

The project has no web control center. Autonomous final publishing and automatic creator-center metric reading are future slices; current publish commands stop before final submission by default.

## Documentation

- [Product requirements](docs/prd.md)
- [Technical specification](docs/technical-spec.md)
- [Documentation map](docs/README.md)
- [Material collection workflow](workflows/collect_materials.md)
- [Content Creation Workflow v3](workflows/create_script.md)
- [Knowledge-led original creation](workflows/create_original.md)
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

## Original creation entry point

```bash
mcn original source add --role-id role_xxx --kind ip_knowledge \
  --title 'IP 的观点与经验' --origin 'private interview' --input data/source.txt
mcn original source add --role-id role_xxx --kind viral_work \
  --title '完整作品' --origin 'https://example.org/work' --input data/work.txt
mcn original source import-material --role-id role_xxx --material-id material_xxx
mcn original source find --role-id role_xxx --query '青春期亲子沟通'
mcn original task new --role-id role_xxx --topic '青春期沉默' --platform douyin
mcn original task prepare --task-id createtask_xxx
```

Let Codex use the writing packet, reread complete sources, research any gap, and write one JSON response with `title`, `angle`, `body`, `source_ids`, and optional `research_notes`. Then run `mcn original task submit --task-id ... --input data/response.json`. Candidates stay in history; accept one using `mcn original task accept --task-id ... --draft-id ...`. Complete client sources under `data/original-knowledge/` are ignored by Git. See the [runbook](workflows/create_original.md) for the full operator journey.

After publication, manually record comparable organic views with `mcn original performance add --task-id ... --account-id ... --age-hours 24 --organic-views ...`. `performance report` groups observations by IP, account, platform, and post age. Codex can propose a hypothesis citing observation IDs; the owner records its decision with `performance decide`. These records do not imply creator-center automation or a causal conclusion.

## Historical v3 creation

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

The default run stops before final submission. In the current workflow, `--allow-submit --live` requires an explicit human-approved publish action. Account-level automation is a later, separately verified slice.

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
