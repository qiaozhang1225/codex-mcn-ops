# Workflow: Collect Materials

## Intent

Collect public source evidence, transcribe authoritative media, and promote only
reviewed records into formal material inventory. Discovery evidence, candidate
decisions, formal materials, and IP-role judgments remain separate.

The active providers are:

- Douyin through the Direct provider and an authenticated Ego Lite session;
- WeChat Channels through the private Mac Hub and authorized Windows Worker.

## Shared gates

- Confirm the target IP role before role-fit classification.
- Require authoritative detail before transcription or formal ingestion.
- Stop on login expiry, CAPTCHA, cursor stall, lease failure, or incomplete
  traversal. Do not bypass platform security challenges.
- Treat page/item limits as bounded samples, not complete source exhaustion.
- Keep credentials, databases, transcripts, downloads, and generated reports
  outside Git.

## Douyin

Run preflight:

```bash
mcn collect douyin doctor \
  --provider direct \
  --transcription-provider aliyun \
  --json
```

Keyword discovery and verification:

```bash
mcn collect douyin search-video \
  --keyword '目标关键词' --provider direct \
  --max-pages 3 --max-items 60 --json

mcn collect douyin detail \
  'https://www.douyin.com/video/WORK_ID' --provider direct --json

mcn collect douyin transcribe \
  'https://www.douyin.com/video/WORK_ID' \
  --provider direct --transcription-provider aliyun --json
```

Persist a reviewed keyword or known-author task:

```bash
mcn collect task keyword \
  --topic '目标方向' --target-count 3 \
  --data-provider direct --transcription-provider aliyun \
  --max-search-pages 3 --json

mcn collect task author \
  --sec-uid 'SEC_UID' \
  --data-provider direct --transcription-provider aliyun \
  --max-pages 3 --json
```

Claim source exhaustion only when the provider reports compatible
`source_exhausted=true`, `has_next=false`, and `stop_reason` values.

## WeChat Channels

Install the additive orchestration schema, then create a durable task so
discovery, detail, transcription, review, and formalization remain resumable
and auditable:

```bash
mcn db migrate-collection-task-orchestration-v1 --json

mcn collect task keyword \
  --topic '目标方向' \
  --target-count 3 \
  --role-id role_xxx \
  --data-provider wechat_channels_remote \
  --transcription-provider aliyun \
  --max-search-pages 1 \
  --max-materials-per-iteration 5 \
  --json

mcn collect task session-status --task-id TASK_ID --json
mcn collect task plan \
  --task-id TASK_ID --keyword '下一轮关键词' \
  --max-pages 1 --json
mcn collect task step --task-id TASK_ID --json
mcn collect task show --task-id TASK_ID --json
```

When semantic review is required, inspect the full source evidence and submit a
bounded decision through the task review command. Resume the same task rather
than creating a duplicate. Public share links must be resolved from the stable
work ID and verified as `https://weixin.qq.com/sph/...` before persistence.

See `docs/specs/wechat-channels-lan-collection.md` and
`docs/specs/collection-task-orchestration-v1.md` for the transport and state
contracts.

## Persistence contract

- `source_authors`: stable author identity;
- `source_works`: stable work identity;
- `source_observations`: time-varying metrics and provider evidence;
- `material_transcriptions`: provider/model-aware ASR output;
- `collection_candidates`: discovery and pipeline decisions;
- `collected_materials`: formal eligibility and understanding decisions;
- `material_role_matches`: many-to-many IP-fit judgments;
- `material_inventory_classifications`: reviewed IP-specific taxonomy;
- `material_creations`: creation/use evidence;
- `collection_tasks`, `collection_task_steps`, `collection_task_reviews`:
  durable orchestration state and review decisions.

Never treat popularity or a role match as sufficient for a formal rewrite base.
Classify against the complete transcript and content mechanism.

## Inventory handoff

```bash
mcn material inventory pending --role-id role_xxx --json

mcn material inventory classify \
  --material-id mat_xxx --role-id role_xxx \
  --topic-direction '目标方向' \
  --content-mechanism '原因解释' \
  --material-class formal_rewrite_base \
  --primary \
  --review-status reviewed \
  --decision-source manual-review \
  --reason '原文有完整观点和解释链'

mcn material inventory list --role-id role_xxx --json
mcn material inventory summary \
  --role-id role_xxx --allocation-file allocation.json --json
```

Used material is excluded by default. Add `--include-used` only for an explicit
reuse audit.
