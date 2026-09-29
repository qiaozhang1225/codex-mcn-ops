# Documentation Map

This directory contains only current, reusable project documentation.

## Authoritative documents

- `prd.md`: current product scope, user outcomes, and acceptance boundaries.
- `technical-spec.md`: current architecture, data ownership, contracts, migrations, and safety rules.
- `specs/collection-task-orchestration-v1.md`: durable collection-task and review transaction contract.
- `specs/wechat-channels-lan-collection.md`: Mac/Windows Channels transport and security contract.

When implementation and prose disagree, executable contracts and migrations under `src/mcn_ops/` are authoritative. Update the matching document in the same change.

## Operator documentation

- `material-collection-sop.md` and `douyin-provider-cli.md`: Douyin operations.
- `adb-publishing-sop.md`, `device-calibration.md`, and `platform-rules.md`: publishing operations.
- `../workflows/create_original.md`: current knowledge-led original writing path; `create_script.md` is historical v3 adaptation.
- `../workflows/`: concise end-to-end runbooks for collection, creation, publishing, and reporting.

## Repository policy

Do not add these artifacts to `docs/`:

- one-off implementation plans or plugin-generated task plans;
- dated PoC reports, host snapshots, run IDs, database counts, or machine paths;
- transcripts, candidate lists, generated scripts, research images, or batch JSON;
- live credentials, signed media locators, cookies, certificates, or device state.

Keep temporary and evidence-heavy artifacts under the ignored local `research/`, `data/`, or `runs/` directories. Use Git history to recover superseded plans and specifications instead of retaining stale copies in the current tree.
