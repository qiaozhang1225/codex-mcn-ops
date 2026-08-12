# Workflow: Create Script

## Intent

Generate publish-ready oral script copy from accepted materials, a confirmed IP persona, common and domain rules, IP professional knowledge, and the evolving creation knowledge pack.

This workflow starts after material collection, transcription, understanding, and eligibility review have produced a usable source pool.

## Inputs

- confirmed `ip_roles` profile and `persona_packet_json`
- `collected_materials.status='collected'`
- `collected_materials.eligibility_status='accepted'`
- promoted material understanding and complete transcript text
- global rules under `knowledge/creation/`
- common and selected domain rules under `knowledge/domains/`
- IP files under `knowledge/ip/<role_slug>/`
- target topic, goal, platform, and material count

## Formal Agent Workflow

Create a task and validate the IP knowledge pack:

```bash
mcn create task new \
  --role-id role_xxxxxxxxxxxx \
  --topic 财运 \
  --goal "生成一条知识型口播" \
  --platform douyin \
  --target-count 1

mcn create knowledge validate --role-id role_xxxxxxxxxxxx --json
```

For each stage, prepare a packet, let Codex produce one JSON result matching `response_template`, submit it, inspect both validation reports, and confirm only a passing result:

```bash
mcn create stage prepare \
  --task-id createtask_xxxxxxxxxxxx \
  --stage material_selection \
  --output /tmp/material-selection-packet.json

mcn create stage submit \
  --task-id createtask_xxxxxxxxxxxx \
  --stage material_selection \
  --input /tmp/material-selection-result.json \
  --json

mcn create task confirm \
  --task-id createtask_xxxxxxxxxxxx \
  --stage material_selection
```

Run stages in order:

1. `material_selection`
2. `creation_brief`
3. `rewrite_draft`
4. `hook_enhancement`
5. `risk_cleanup`
6. `publish_format`
7. `delivery`

A corrected submission writes a new `creation_stage_runs.version` and preserves the previous result. `mcn create task run` is a deterministic `rules-fallback` path for regression tests and emergency drafts; it is not formal `codex-agent` output.

## Material Selection

Preparation is read-only. It ranks eligible candidates and includes complete transcript text without persisting a selection. Submission records:

- source content task and hook mechanism;
- speaker position and thickness judgment;
- `formal_rewrite_base` or `topic_clue`;
- `aligned`, `acceptable_variance`, `repairable_conflict`, or `hard_conflict`;
- exact conflicting claim, disposition, weaknesses, and maximum salvage boundary.

`topic_clue` and `hard_conflict` cannot advance as standard adaptation. A repairable conflict must preserve the source task, hook mechanism, and evidence path after local correction.

## Creation Modes And Professional Support

`creation_brief` selects:

- `adaptation`: the source provides the main claim, evidence path, and structure;
- `half_original`: IP knowledge supplies a material part of the argument;
- `original`: the source is not the drafting spine.

Professional support uses `none`, `guardrail_only`, or `one_support_point`. Standard adaptation may cite at most one professional card. Every added professional claim must carry a valid knowledge card ID.

## Knowledge Packet

Audit context with:

```bash
mcn create knowledge packet --task-id createtask_xxxxxxxxxxxx --json
```

Stage packets contain only the knowledge required for that stage: persona, global playbooks, common and selected domain playbooks, IP playbook, professional cards, recent memory, feedback, selected material understanding, upstream outputs, task brief, and output contract. Full transcripts are included for selection, brief, and rewrite stages.

## Output And Learning

`publish_format` creates a `content_packages` draft, `material_creations` links, and a `creation_delivery_packages` record. `final_copy` must equal the confirmed risk-cleaned body.

Record pre-publish and post-publish feedback separately. Generate learning proposals, but apply them only after explicit review:

```bash
mcn create feedback add --task-id createtask_xxx --role-id role_xxx --stage rewrite_draft --platform douyin --judgment rejected --human-note "开头变弱"
mcn create learning propose --role-id role_xxx
mcn create learning apply --proposal-id clearn_xxx
```

SQLite remains the audit source; Markdown and professional cards remain the human-readable knowledge source.
