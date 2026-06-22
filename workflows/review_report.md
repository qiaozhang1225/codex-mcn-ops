# Workflow: Review Report

## Intent

Turn publishing results into the next operating decision.

## Inputs

- publish job ids
- result URLs
- metrics
- qualitative notes

## Steps

1. Read `tracking_snapshots`.
2. Compare performance by IP, platform, topic, and format.
3. Identify content patterns worth repeating.
4. Write a short Feishu-ready report.
5. Propose next content packages.

Quick local command:

```bash
mcn report daily --output runs/daily-report.md
```

## Output

- Review summary
- next-round content recommendations
