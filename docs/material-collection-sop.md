# Material Collection SOP

## Purpose

Collect public Douyin works through the direct provider, verify authoritative
detail before transcription, transcribe with Alibaba Cloud Qwen ASR, and persist
platform evidence separately from material decisions.

The production default is fixed:

```text
data_provider=direct
transcription_provider=aliyun
paid_fallback=removed
```

## Configuration

Store local configuration in `.env.local` and never commit it:

```dotenv
DOUYIN_DIRECT_MODE="browser"
DASHSCOPE_API_KEY="..."
DASHSCOPE_WORKSPACE_ID="..."
DASHSCOPE_REGION="cn-beijing"
MCN_ASR_CACHE_PATH="data/transcription-cache.sqlite"
```

Keep Ego Lite logged in to Douyin. Browser-backed pagination reuses its signed-in
session and native runtime signatures; it does not require copying cookies into
the project database.

## Preflight

```bash
mcn collect douyin doctor \
  --provider direct \
  --transcription-provider aliyun \
  --json
```

Before a large batch, verify one known work:

```bash
mcn collect douyin detail 'https://www.douyin.com/video/...' --json
mcn collect douyin transcribe 'https://www.douyin.com/video/...' --json
```

## Keyword Collection

```bash
mcn collect task keyword \
  --topic '亲子关系' \
  --target-count 10 \
  --data-provider direct \
  --transcription-provider aliyun \
  --max-search-pages 3 \
  --json
```

The pipeline is:

```text
discovery
→ list_prefiltered
→ detail_verified
→ transcription_started
→ transcribed
→ eligibility_checked
→ saved / reused / rejected
```

Failed detail, ASR, or eligibility checks continue to the next ranked candidate
until the target is reached or candidates are exhausted.

## Author Collection

Use a verified Douyin `sec_uid` for a new author. Name lookup is local-only and
does not call an unverified remote user search.

```bash
mcn collect task author \
  --sec-uid '...' \
  --data-provider direct \
  --transcription-provider aliyun \
  --max-pages 3 \
  --json
```

Use `--max-pages 0` only when the intent is to traverse until the provider proves
`has_next=false`, subject to the configured safety cap.

## Pagination Semantics

Every traversal reports:

- `captured_pages`
- `captured_items`
- `has_next`
- `request_satisfied`
- `source_exhausted`
- `stop_reason`

`source_exhausted=true` is valid only when `has_next=false`. Reaching `max_pages`,
`max_items`, or a policy stop is a bounded result, not proof that the account has
no more works.

## Persistence Model

- `source_authors`: stable platform author identities.
- `source_works`: stable work identity and author relation.
- `source_observations`: time-varying metrics and provider evidence.
- `material_transcriptions`: ASR result keyed by audio/provider/model/options.
- `collection_candidates`: pipeline decisions linked to a source work.
- `collected_materials`: eligibility and understanding decisions linked to a
  source work and active transcription.
- `provider_call_logs` / `provider_call_cache`: provider-neutral operational data.

Do not persist cookies, API keys, `a_bogus`, authorization headers, or signed
audio/video URLs.

## Status Rules

- `completed`: target achieved, or all selected candidates reached a terminal
  state when no numeric target exists.
- `partial`: at least one material succeeded but the target was not achieved.
- `empty`: no material succeeded and no system-level failure occurred.
- `failed`: provider, configuration, database, or unrecoverable workflow error.

Task completion and source traversal completeness are separate facts.

## Material and Creation Handoff

Only usable knowledge-sharing oral scripts become active collected materials.
Concrete ritual instructions, non-knowledge scenes, missing transcripts, and
weak knowledge cores remain rejected candidates.

One source material can match multiple IP roles through `material_role_matches`.
Role-specific reuse is recorded in `material_creations`; the source role is not
the only role allowed to use the material.

Reviewed batch classification is a separate decision stored in
`material_inventory_classifications`. Do not infer that an accepted role match
is a formal rewrite base. Import reviewed classifications transactionally, then
check unused supply against the current allocation:

```bash
mcn material inventory pending --role-id role_xxx --json
mcn material inventory import \
  --role-id role_xxx --file reviewed-inventory.json --json
mcn material inventory summary \
  --role-id role_xxx --allocation-file allocation.json --json
```

The default list and summary exclude material already referenced by
`material_creations` for that role. Use `--include-used` only for an intentional
reuse audit.

A material can keep secondary topic classifications for retrieval, but at most
one row per material and role can be `is_primary=true`. Allocation supply counts
only distinct source works represented by reviewed primary formal bases with an
accepted role match. The allocation file keeps `video_allocation` separate from
`formal_base_targets`; an optional `expected_video_total` validates that batch's
video plan without introducing a global fixed total.

## Database Migration

The material inventory layer is an explicit additive migration for an existing
schema-v3 database:

```bash
mcn --db-path data/mcn_ops.sqlite \
  db migrate-material-inventory-v1 --json
```

It creates no classifications and does not infer them from role matches.

Dry-run validation never replaces the source database:

```bash
mcn --db-path data/mcn_ops.sqlite \
  db migrate-collection-schema-v3 \
  --json
```

Explicit replacement requires a destination and recovery path in the same
directory. Stop every writer first:

```bash
mcn --db-path data/mcn_ops.sqlite \
  db migrate-collection-schema-v3 \
  --destination data/mcn_ops.v3.sqlite \
  --replace \
  --recovery-path data/mcn_ops.pre-v3.sqlite \
  --json
```

Replacement is blocked if work identity resolution, row parity, transcript
identity, foreign keys, integrity checks, or the legacy table/column denylist
fails.
