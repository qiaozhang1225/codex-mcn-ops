# Workflow: Create Script

## Intent

Generate publish-ready five-part oral script copy from accepted collected materials, a confirmed IP persona, and the evolving Markdown creation knowledge pack.

This workflow does not replace material collection. It starts after material understanding and role matching have produced a usable source-material pool.

## Inputs

- confirmed `ip_roles` profile and `persona_packet_json`
- `collected_materials.status='collected'`
- `collected_materials.eligibility_status='accepted'`
- promoted material understanding columns
- global creation knowledge files under `knowledge/creation/`
- IP-specific creation knowledge files under `knowledge/ip/<role_slug>/`
- target topic, goal, platform, and target material count

## Stages

Run and confirm stages in order:

```bash
mcn create task new \
  --role-id role_xxxxxxxxxxxx \
  --topic 财运 \
  --goal "生成一条知识型五段式口播" \
  --platform douyin \
  --target-count 3

mcn create task run --task-id createtask_xxxxxxxxxxxx --stage material_selection
mcn create task confirm --task-id createtask_xxxxxxxxxxxx --stage material_selection

mcn create task run --task-id createtask_xxxxxxxxxxxx --stage creation_brief
mcn create task confirm --task-id createtask_xxxxxxxxxxxx --stage creation_brief

mcn create task run --task-id createtask_xxxxxxxxxxxx --stage rewrite_draft
mcn create task confirm --task-id createtask_xxxxxxxxxxxx --stage rewrite_draft

mcn create task run --task-id createtask_xxxxxxxxxxxx --stage hook_enhancement
mcn create task confirm --task-id createtask_xxxxxxxxxxxx --stage hook_enhancement

mcn create task run --task-id createtask_xxxxxxxxxxxx --stage risk_cleanup
mcn create task confirm --task-id createtask_xxxxxxxxxxxx --stage risk_cleanup

mcn create task run --task-id createtask_xxxxxxxxxxxx --stage publish_format
mcn create task confirm --task-id createtask_xxxxxxxxxxxx --stage publish_format

mcn create task export --task-id createtask_xxxxxxxxxxxx --output data/creation-task.md
```

Use `mcn create task retry --stage ... --note "..."` when a stage needs revision. Retry keeps the previous version and writes a new `creation_stage_runs.version`.

## Material Selection

`material_selection` reads only accepted formal materials. It does not select broad candidates, rejected materials, missing transcript rows, or materials already used by the same IP role unless `--allow-reuse-material` is set at task creation.

Selection ranking uses:

- role-match score from `material_role_matches`
- topic hit in promoted material understanding fields
- role keywords and fit themes
- knowledge-core score

After selecting materials, the stage also writes source analysis:

- original or corrected source hook
- viral reasoning
- authority frame
- must-keep source elements
- discard elements
- ASR corrections such as `挂失 -> 卦师`

`rewrite_draft` must use this analysis. A draft is marked `needs_retry` when the source content task or propagation mechanism is lost without reason, an incompatible speaker perspective is fabricated, the task-specific length guardrail is broken without justification, or the body no longer fulfils the opening.

## Knowledge Packet

Audit the exact context with:

```bash
mcn create knowledge packet --task-id createtask_xxxxxxxxxxxx --json
```

The packet includes persona, global playbooks, IP playbooks, selected material understanding, and the current task brief. It does not include full transcripts by default.

The packet also includes rewrite requirements, source analysis, and recent stage feedback. This is what keeps human correction notes available during retry without putting the full raw transcript into every prompt.

For `rewrite_draft`, `knowledge/creation/global-rewrite-playbook.md` is the cross-IP methodology. It preserves content task, propagation mechanism, speaker credibility, internal logic, and stage boundaries without prescribing a fixed script structure. IP-specific playbooks should contain only genuine role differences.

## Output

`publish_format` creates:

- a `content_packages` draft
- `material_creations` rows linking selected materials to this IP and content package
- a `creation_delivery_packages` row with the five-part publish structure

## Feedback Learning

After publication, add lightweight feedback:

```bash
mcn create feedback add \
  --content-id cpkg_xxxxxxxxxxxx \
  --platform douyin \
  --metrics-json '{"likes":1200,"comments":35,"shares":18}' \
  --human-note "开头有效，但财运表达略重"
```

Before publication, add stage feedback when a draft or hook needs revision:

```bash
mcn create feedback add \
  --task-id createtask_xxxxxxxxxxxx \
  --role-id role_xxxxxxxxxxxx \
  --stage rewrite_draft \
  --platform douyin \
  --judgment rejected \
  --human-note "开头变弱、字数太长、太像讲大道理"
```

Generate but do not automatically apply learning:

```bash
mcn create learning propose --role-id role_xxxxxxxxxxxx
mcn create learning apply --proposal-id clearn_xxxxxxxxxxxx
```

This keeps SQLite as the event/audit source and Markdown as the human-readable creation knowledge source.
