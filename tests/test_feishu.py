from __future__ import annotations

from pathlib import Path

from mcn_ops.feishu import build_publish_job_payload, write_payload


def test_feishu_payload_writer(tmp_path: Path) -> None:
    payload = build_publish_job_payload(
        {"id": "job_1", "platform": "douyin", "device_serial": "d1", "status": "prepared"},
        {
            "id": "content_1",
            "title": "title",
            "body": "body",
            "media_paths_json": "[\"/tmp/video.mp4\"]",
            "cover_path": None,
            "hashtags_json": "[\"tag\"]",
        },
    )

    output = write_payload(payload, tmp_path / "payload.json")

    assert output.exists()
    assert payload["content"]["hashtags"] == ["tag"]
