# Workflow: ADB Publish

## Intent

Use an authorized Android device and an already signed-in platform app to
prepare a publish job. Submission is always an explicit live action.

## Preconditions

- the device serial and target platform are confirmed;
- the publish job contains approved copy and assets;
- `adb devices` shows one authorized target;
- no account switch, login flow, or CAPTCHA is pending.

## Steps

1. Run `mcn adb doctor`.
2. Push the approved assets:

   ```bash
   mcn publish push-assets --job-id JOB_ID
   ```

3. Run the non-submitting preparation flow:

   ```bash
   mcn publish run --job-id JOB_ID --device DEVICE_SERIAL
   ```

4. Inspect screenshots and UI dumps under `runs/JOB_ID/`.
5. Only after the final screen is verified, repeat with both explicit gates:

   ```bash
   mcn publish run \
     --job-id JOB_ID \
     --device DEVICE_SERIAL \
     --allow-submit \
     --live
   ```

6. Record the result URL or an explicit manual status with
   `mcn publish verify`.

Stop on device ambiguity, unexpected UI, authentication prompts, or missing
evidence. Logs, screenshots, UI dumps, and account state remain local and are
not committed to Git.

## Output

- local ADB logs, screenshots, and UI dumps;
- one verified tracking snapshot;
- a clear distinction between prepared, submitted, and verified states.
