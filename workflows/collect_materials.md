# Workflow: Collect Materials

## Intent

Collect public Douyin evidence through the current Direct provider, turn only
verified and usable scripts into formal materials, then review them for a
confirmed IP role. Keep discovery evidence, candidate decisions, formal
materials, and role-specific judgments separate.

## Preconditions

- Ego Lite is signed in to Douyin.
- `.env.local` contains a valid `DASHSCOPE_API_KEY` for Alibaba Cloud Qwen ASR.
- The target IP role is confirmed before formal role classification.

Run preflight first:

```bash
mcn collect douyin doctor \
  --provider direct \
  --transcription-provider aliyun \
  --json
```

Stop on expired login, CAPTCHA, provider failure, cursor stall, or an incomplete
browser traversal. Hand browser verification back to the operator; do not loop
around a security challenge.

## Keyword Workflow

1. Discover a bounded candidate set:

   ```bash
   mcn collect douyin search-video \
     --keyword '目标关键词' --provider direct \
     --max-pages 3 --max-items 60 --json
   ```

2. Prefilter by relevance, duration, and public metrics. For each shortlist
   entry, verify authoritative detail before transcription:

   ```bash
   mcn collect douyin detail \
     'https://www.douyin.com/video/WORK_ID' --provider direct --json

   mcn collect douyin transcribe \
     'https://www.douyin.com/video/WORK_ID' \
     --provider direct --transcription-provider aliyun --json
   ```

3. Persist through the high-level workflow when the intent is to create formal
   material records:

   ```bash
   mcn collect task keyword \
     --topic '目标方向' --target-count 3 \
     --data-provider direct --transcription-provider aliyun \
     --max-search-pages 3 --json
   ```

## Known-Author Workflow

Use a verified `sec_uid` and a bounded page count:

```bash
mcn collect task author \
  --sec-uid 'SEC_UID' \
  --data-provider direct --transcription-provider aliyun \
  --max-pages 3 --json
```

Reaching a page or item limit is only bounded pagination. Claim complete source
exhaustion only when the result reports `source_exhausted=true`,
`has_next=false`, and a compatible `stop_reason`.

## Persistence Contract

- `source_authors`: stable author identity.
- `source_works`: stable work identity.
- `source_observations`: time-varying metrics and provider evidence.
- `material_transcriptions`: provider/model-aware ASR output.
- `collection_candidates`: discovery and pipeline decisions.
- `collected_materials`: formal eligibility and understanding decisions.
- `material_role_matches`: many-to-many IP fit judgments.
- `material_inventory_classifications`: reviewed, IP-specific batch taxonomy.
- `material_creations`: role-specific creation/use evidence.

Never treat a popular or role-matched video as a formal rewrite base without a
reviewed classification. Classify by audience value and content mechanism, not
title words. Existing accepted role matches remain unclassified until reviewed.
One material may retain secondary topic directions for discovery, but only its
single reviewed primary formal-base classification can fill an allocation quota.

## Inventory Handoff

List distinct, accepted, unused source works still awaiting review:

```bash
mcn material inventory pending --role-id role_xxx --json
```

Read the full transcript before classifying one reviewed material:

```bash
mcn material inventory classify \
  --material-id mat_xxx --role-id role_xxx \
  --topic-direction '目标方向' \
  --content-mechanism '原因解释' \
  --material-class formal_rewrite_base \
  --primary \
  --review-status reviewed \
  --decision-source manual-review \
  --reason '原文有完整观点和解释链'
```

Inspect available, unused inventory and its allocation gap:

```bash
mcn material inventory list --role-id role_xxx --json
mcn material inventory summary \
  --role-id role_xxx --allocation-file allocation.json --json
```

Used material is excluded by default. Add `--include-used` only for an explicit
reuse audit.
