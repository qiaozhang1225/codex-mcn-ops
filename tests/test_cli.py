from __future__ import annotations

from pathlib import Path
import json

from mcn_ops.cli import main


def _read_json(capsys):
    return json.loads(capsys.readouterr().out.strip())


def test_cli_content_prepare_and_dry_run(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "mcn.sqlite"
    media_path = tmp_path / "video.mp4"
    media_path.write_text("fake", encoding="utf-8")

    assert main(["--db-path", str(db_path), "init-db"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "content",
                "create",
                "--title",
                "title",
                "--body",
                "body",
                "--media",
                str(media_path),
            ]
        )
        == 0
    )
    content_id = capsys.readouterr().out.strip().splitlines()[-1]

    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "publish",
                "prepare",
                "--content-id",
                content_id,
                "--platform",
                "douyin",
            ]
        )
        == 0
    )
    job_id = capsys.readouterr().out.strip().splitlines()[-1]

    assert main(["--db-path", str(db_path), "publish", "run", "--job-id", job_id, "--dry-run"]) == 0
    assert "dry_run_completed" in capsys.readouterr().out


def test_cli_collection_material_flow(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "mcn.sqlite"

    assert main(["--db-path", str(db_path), "init-db"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "collect",
                "role",
                "upsert",
                "--name",
                "知识型老师",
                "--search-keyword",
                "知识型口播",
                "--json",
            ]
        )
        == 0
    )
    role_payload = _read_json(capsys)
    role_id = role_payload["role_id"]

    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "collect",
                "run",
                "--topic",
                "知识型口播",
                "--target-count",
                "1",
                "--like-floor",
                "1",
                "--role-id",
                role_id,
                "--json",
            ]
        )
        == 0
    )
    run_payload = _read_json(capsys)
    run_id = run_payload["run_id"]
    material_id = run_payload["saved_material_ids"][0]

    assert main(["--db-path", str(db_path), "collect", "understand", "--run-id", run_id, "--json"]) == 0
    understand_payload = _read_json(capsys)
    assert understand_payload["updated"][0]["material_id"] == material_id
    assert understand_payload["matches"][0]["role_id"] == role_id

    assert main(["--db-path", str(db_path), "collect", "match", "--run-id", run_id, "--role-id", role_id]) == 0
    assert capsys.readouterr().out.strip()

    assert main(["--db-path", str(db_path), "collect", "report", "--run-id", run_id]) == 0
    assert "Collection Report" in capsys.readouterr().out

    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "material",
                "promote",
                "--material-id",
                material_id,
                "--platform",
                "douyin",
                "--role-id",
                role_id,
                "--json",
            ]
        )
        == 0
    )
    promote_payload = _read_json(capsys)
    assert promote_payload["content_id"].startswith("content_")

    assert main(["--db-path", str(db_path), "material", "creations", "--material-id", material_id, "--json"]) == 0
    creations_payload = _read_json(capsys)
    assert creations_payload["creations"][0]["role_id"] == role_id
    assert creations_payload["creations"][0]["content_package_id"] == promote_payload["content_id"]
