# WeChat Channels Search-only PoC Runbook

This runbook validates remote keyword search before the Channels provider,
media download, ASR, or SQLite integration is implemented.

## Safety boundary

- Use the dedicated Windows tool machine and a non-core WeChat account.
- Do not install the interception certificate or proxy on the Mac.
- Do not expose the Windows worker HTTP API to the LAN.
- Do not use a public Hub.
- Do not test media download in this phase.
- Do not attempt to automate login challenges or CAPTCHA.
- Use a one-time shared secret and rotate it after an insecure LAN probe.

The repository database is not imported by `mcn-channels-probe`. For additional
evidence, hash `data/mcn_ops.sqlite` before and after the test when it exists.

## 1. Record immutable inputs

Record these values in the PoC report:

```text
Mac repository SHA
Windows worker upstream repository SHA
Windows worker executable SHA256
Windows version
WeChat version
Worker machine ID shown in its startup log
Test account label (never store account credentials)
Mac LAN IP
```

The configured worker ID must match `X-Client-ID`; use the machine ID printed by
the Windows worker rather than inventing a display name.

## 2. Prepare the Mac probe environment

From the isolated worktree:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
```

Generate a strong one-time secret without writing it to the repository:

```bash
export CHANNELS_HUB_SECRET="$(openssl rand -hex 32)"
```

For the first search-only probe on a controlled private LAN, plain WebSocket may
be enabled explicitly. Search terms and search results are the only payloads in
this phase, but the one-time secret is visible to a LAN packet observer and must
be rotated afterwards.

```bash
mcn-channels-probe \
  --host 0.0.0.0 \
  --port 18081 \
  --allow-insecure-lan \
  --worker-id 'ACTUAL_WORKER_MACHINE_ID' \
  --keyword 'AI' \
  --max-pages 2
```

Production and any media/detail phase require `--tls-cert` and `--tls-key`,
which changes the endpoint scheme to `wss://`.

## 3. Configure the dedicated Windows worker

Use a local copy of the worker configuration. Set only the Mac LAN endpoint and
the one-time secret:

```yaml
cloud_enabled: true
cloud_hub_url: "ws://MAC_LAN_IP:18081/ws/client"
cloud_secret: "ONE_TIME_SECRET"
radar_enabled: false
```

Requirements:

- Windows Firewall keeps worker HTTP/API ports inaccessible from the LAN.
- The Windows worker initiates the WebSocket connection to Mac.
- WeChat is logged in and a supported Channels page is open.
- The page reports search capability in the worker heartbeat.

The worker may require its interception certificate and proxy on Windows. That
is a separate, security-sensitive action and must be performed only on the
dedicated Windows machine after its source/binary hash is recorded.

## 4. Execute the search matrix

Run five public, low-risk keywords. At least three must have a second page.
Repeat until at least twenty calls have been observed.

For every run, retain the probe JSON output and record:

```text
keyword
captured_pages
captured_items
has_next
source_exhausted
request_satisfied
stop_reason
worker and WeChat versions
start/end timestamps
```

The probe replaces opaque markers with `<present>` and redacts signed URL query
credentials. It must not output the shared secret.

## 5. Failure checks

Run each check once:

1. Close the Channels page: the call must fail as not ready.
2. Stop the Windows worker during a call: the pending call must fail.
3. Restart the worker: it must reconnect without restarting the Mac probe.
4. Set a wrong secret: the Hub must reject the connection.
5. Return `has_more=true` without a marker in a controlled fixture: the result
   must be `cursor_missing`, not source exhaustion.

Do not retry around a WeChat login challenge. Record it as an external gate.

## 6. Pass/fail decision

Pass only when:

- at least 95% of twenty search calls return a correlated response;
- three second-page traversals are verified;
- no keyword was typed manually after the page became ready;
- bounded sampling and source exhaustion are reported truthfully;
- restart and not-ready behavior are explicit;
- no database file changed;
- no secret or signed media credential appears in retained output.

On pass, proceed to the Mac remote-provider and video-detail phase. On fail,
stop and classify the failure as worker compatibility, WeChat readiness,
pagination, transport, or platform risk control before changing the main
collection workflow.
