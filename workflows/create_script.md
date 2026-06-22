# Workflow: Create Script

## Intent

Turn confirmed material into a platform-ready content package.

## Inputs

- IP profile
- confirmed material
- target platform
- desired tone and topic

## Steps

1. Draft the script.
2. Generate title, body, hashtags, and platform notes.
3. Check platform limits from `docs/platform-rules.md`.
4. Create a local content package with `mcn content create`.
5. Prepare publish jobs for selected platforms.

## Output

- `content_packages` row
- one or more `publish_jobs`
- optional Feishu handoff payload
