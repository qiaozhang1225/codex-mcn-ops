# ADB Publishing SOP

## Device Setup

1. Enable Developer Options on the Android phone.
2. Enable USB debugging.
3. Connect the phone by USB.
4. Trust the Mac when the phone prompts for debugging authorization.
5. Log in to Douyin, Xiaohongshu, WeChat, and Kuaishou manually on the phone.
6. Keep the phone awake during calibration and publishing.

## Health Check

```bash
mcn adb doctor
```

Expected:

- `adb_available: true`
- one authorized device with state `device`
- model and SDK are visible

## Safe Publish Run

```bash
mcn publish push-assets --job-id <job_id>
mcn publish run --job-id <job_id> --device <serial>
```

The default run opens the app, captures evidence, and stops before the final submit step.

## Live Publish

Only run this after a human confirms the final screen:

```bash
mcn publish run --job-id <job_id> --device <serial> --allow-submit --live
```

## Failure Handling

- If `uiautomator dump` is blank or missing important nodes, use screenshot plus Computer Use/scrcpy for the app-specific step.
- If media does not appear in the picker, check file format and phone media scanner behavior.
- If a platform app changes layout, update that platform adapter calibration, not the data model.
