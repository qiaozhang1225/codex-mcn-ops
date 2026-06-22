# Device Calibration

Calibration converts a platform adapter checkpoint into a reliable device action sequence.

## Calibration Artifacts

For each platform and app version, keep:

- device model
- Android version
- app version
- screen resolution
- publish entry screenshots
- UI XML dumps when available
- known tap/text/swipe sequence
- fallback note for Computer Use

## Calibration Order

1. Run `mcn publish run --job-id <job_id> --device <serial>`.
2. Open `runs/<job_id>/`.
3. Inspect screenshots and XML dumps.
4. Add the smallest reliable action sequence for the checkpoint.
5. Repeat with `stop-before-submit`.
6. Do one safe live test with a test account and harmless test package.

## Rule

Prefer robust text/selector-based UI XML actions when possible. Use coordinates only after confirming the target phone resolution and app version.
