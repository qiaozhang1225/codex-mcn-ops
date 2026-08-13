# Content Creation Workflow v3

Use one session with three linear roles. Do not create persistent role agents. Script Writer is the only role allowed to modify viewer-facing copy.

## Stage chain

Adaptation and half-original work:

```text
material_selection → creation_brief → script_writing → quality_review → risk_review → publish_format → delivery
```

Original work starts at `creation_brief`.

## Task

```bash
mcn create task new \
  --role-id role_xxxxxxxxxxxx \
  --topic "topic" \
  --goal "goal" \
  --platform douyin \
  --target-count 1 \
  --creation-mode adaptation
```

Use `half_original` when IP knowledge supplies a material part of the main argument. Use `original` when no source remains the drafting spine.

## Formal stage execution

For every stage, prepare a packet, produce one JSON result, submit it, inspect both validation reports, and confirm only a structurally valid result.

```bash
mcn create stage prepare --task-id TASK_ID --stage STAGE --knowledge-root knowledge --output /tmp/packet.json --json
mcn create stage submit --task-id TASK_ID --stage STAGE --knowledge-root knowledge --input /tmp/result.json --json
mcn create task confirm --task-id TASK_ID --stage STAGE --json
```

Do not use `mcn create task run` for `script_writing`, `quality_review`, or `risk_review`.

## Script Writer

Load the prepared source, brief, IP, domain, professional knowledge, current script, and pending revision request. Produce a complete script. On revision, bind to the base script and review run, obey the declared scope, preserve exact protected spans, and declare changes that mechanically reconstruct the new body.

Writing modes:

- `initial_draft`;
- `opening_only`;
- `opening_and_bridge`;
- `localized_body_revision`;
- `risk_localized_revision`;
- `full_rewrite`.

## Quality Review

Do not output copy. Review content task, viewer value, source mechanism, IP voice, speaker credibility, reasoning, oral integrity, opening attention, and body payoff.

Review `贪、瞋、痴、慢、疑` separately with `strong`, `weak`, `absent`, or `artificial`. Strong and weak statuses require exact opening evidence; strong requires exact body payoff evidence. Five natural strong drivers are the highest target. A pass normally requires at least three strong drivers, no artificial driver, one coherent contract, and complete payoff. Never add unsupported stimulation to reach five.

Return `pass`, `revise`, or `return_upstream`. A non-pass result must give a bounded revision request and exact protected spans.

## Risk Review

Do not output cleaned copy. Review the latest quality-approved body for diagnosis, single-cause claims, universalization, fabricated identity or evidence, professional conflict, regulated claims, certainty, outcome promises, and platform risk.

Return `pass`, `revise`, `return_upstream`, or `reject`. Every issue must quote an exact span and give the maximum repair boundary. Repairs return to Script Writer.

## Revision routing

```text
Quality revise → Script Writer → Quality Review
Risk revise → Script Writer → Quality Review → Risk Review
```

Every review binds to the Script Writer stage run ID and body hash. A new body invalidates all earlier review passes.

## Publish gate

`publish_format.final_copy` must exactly equal the latest Script Writer body passed by both Quality Review and Risk Review. Delivery formats confirmed artifacts only and never rewrites the body.

## Legacy

Methodology-v2 stages `rewrite_draft`, `hook_enhancement`, and `risk_cleanup` remain available for historical task reading and export. Do not use them for new tasks.
