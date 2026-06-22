from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_publish_job_payload(job: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
    """Build a Feishu-friendly payload without requiring live Feishu credentials."""
    return {
        "job_id": job["id"],
        "platform": job["platform"],
        "device_serial": job.get("device_serial"),
        "status": job["status"],
        "content": {
            "id": content["id"],
            "title": content["title"],
            "body": content["body"],
            "media_paths": json.loads(content["media_paths_json"]),
            "cover_path": content.get("cover_path"),
            "hashtags": json.loads(content["hashtags_json"]),
        },
    }


def write_payload(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
