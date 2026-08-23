from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path


def write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create short-lived worker and Hub PoC secrets.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--hub-url", default="ws://192.168.3.120:18081/ws/client")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    hub_secret = secrets.token_hex(32)
    local_secret = secrets.token_hex(32)

    write_private(output_dir / "hub.env", f"CHANNELS_HUB_SECRET={hub_secret}\n")
    write_private(
        output_dir / "config.yaml",
        f'''port: 2025
download_dir: "D:/wx-channel-poc/downloads"
log_file: "D:/wx-channel-poc/logs/wx_channel.log"
max_log_size_mb: 2
save_page_snapshot: false
save_page_js: false
enable_log_interception: false
cloud_enabled: true
cloud_hub_url: "{args.hub_url}"
cloud_secret: "{hub_secret}"
machine_id: "workstation-channels-01"
secret_token: "{local_secret}"
allowed_origins:
  - "https://channels.weixin.qq.com"
radar_enabled: false
metrics_enabled: false
hub_sync:
  enabled: false
  push_enabled: false
''',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
