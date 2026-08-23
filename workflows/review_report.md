# Workflow: Review Report

## Intent

Turn verified publishing results into the next operating decision without
overstating incomplete metrics or unsupported causality.

## Inputs

- verified publish job IDs and result URLs;
- comparable tracking snapshots;
- platform, IP, topic, format, and publish-time context;
- qualitative notes with their evidence source.

## Steps

1. Exclude jobs that are only prepared or submitted but not verified.
2. Compare like-for-like snapshots by IP, platform, topic, and format.
3. Separate observed performance from interpretation and recommendation.
4. Identify patterns worth retesting; do not infer content quality from one
   isolated metric or one post.
5. Generate the local report:

   ```bash
   mcn report daily --output runs/daily-report.md
   ```

6. Read back the report and check every decision against its source snapshot
   before sharing it externally.

`runs/` and exported reports are local operating artifacts. Commit only durable
workflow or specification changes, not account-level performance data.

## Output

- an evidence-scoped review summary;
- repeat, revise, or stop decisions;
- bounded recommendations for the next content package.
