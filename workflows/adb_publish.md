# Workflow: ADB Publish

## Intent

Use a real Android phone and logged-in platform apps to prepare or publish content.

## Inputs

- publish job id
- Android device serial
- target platform

## Steps

1. Run `mcn adb doctor`.
2. Run `mcn publish push-assets --job-id <job_id>`.
3. Run `mcn publish run --job-id <job_id> --device <serial>`.
4. Inspect `runs/<job_id>/` screenshots.
5. If the final screen is correct, either stop for human publish or run live publish explicitly.
6. Run `mcn publish verify` with result URL or manual status.

## Output

- ADB run logs
- screenshots/UI dumps
- verified tracking snapshot
