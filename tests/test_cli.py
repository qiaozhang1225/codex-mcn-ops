from __future__ import annotations

from pathlib import Path
import json

from mcn_ops.cli import main
from mcn_ops.store import Store


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


def test_cli_collect_task_keyword_reaches_target_and_reports_draft_understanding(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "mcn.sqlite"

    assert main(["--db-path", str(db_path), "init-db"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "collect",
                "task",
                "keyword",
                "--topic",
                "知识型口播",
                "--target-count",
                "3",
                "--like-floor",
                "1",
                "--json",
            ]
        )
        == 0
    )
    payload = _read_json(capsys)
    task_id = payload["task"]["id"]

    assert payload["task"]["target_scope"] == "keyword"
    assert payload["saved_count"] == 3
    assert payload["understanding_summary"]["draft_local_count"] == 3
    assert payload["understanding_summary"]["pending_codex_understanding_count"] == 3
    assert payload["api_call_summary"]["total_calls"] >= 1

    assert main(["--db-path", str(db_path), "collect", "task", "report", "--task-id", task_id]) == 0
    report_text = capsys.readouterr().out
    assert "Collection Task Report" in report_text
    assert "待 Codex 深度理解" in report_text


def test_cli_author_videos_ranks_stored_viral_candidates(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "mcn.sqlite"
    store = Store(db_path)
    store.init_db()
    sec_uid = store.upsert_douyin_author({"sec_uid": "sec_1", "nickname": "娜说智慧"})
    store.upsert_douyin_author_video(
        sec_uid,
        {
            "work_id": "low",
            "title": "普通作品",
            "duration_ms": 60000,
            "metrics": {"digg_count": 100},
        },
    )
    store.upsert_douyin_author_video(
        sec_uid,
        {
            "work_id": "hot",
            "title": "爆款作品",
            "duration_ms": 90000,
            "metrics": {"digg_count": 3000, "share_count": 2000},
        },
    )

    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "collect",
                "author",
                "videos",
                "--name",
                "娜说智慧",
                "--like-floor",
                "5000",
                "--json",
            ]
        )
        == 0
    )
    payload = _read_json(capsys)
    assert payload["viral_count"] == 1
    assert payload["videos"][0]["work_id"] == "hot"
    assert payload["videos"][0]["score"] == 11000


def test_cli_collect_task_author_preserves_existing_codex_understanding(tmp_path: Path, capsys, monkeypatch) -> None:
    db_path = tmp_path / "mcn.sqlite"
    store = Store(db_path)
    store.init_db()
    sec_uid = store.upsert_douyin_author({"sec_uid": "sec_1", "nickname": "娜说智慧"})
    run_id = store.create_collection_run(
        task_id=None,
        role_id=None,
        topic="原采集",
        target_count=1,
        like_floor=1,
        super_like_threshold=100,
        tool_provider="mxnzp",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "source_link": "https://example.com/video",
            "title": "八个旺自己的秘密",
            "transcript_text": "旺自己要先稳住能量。",
            "source_platform": "douyin",
            "work_id": "756",
            "author_name": "娜说智慧",
            "author_sec_uid": sec_uid,
        },
        material_understanding={
            "topic_summary": "Codex 深度摘要",
            "hook": "八个旺自己的秘密",
            "core_claim": "先稳住能量。",
            "content_type": "方法清单",
            "understanding_provider": "codex-agent",
            "understanding_model": "gpt-5-codex",
            "status": "success",
        },
        raw={},
    )
    store.upsert_douyin_author_video(
        sec_uid,
        {
            "work_id": "756",
            "title": "八个旺自己的秘密",
            "source_url": "https://example.com/video",
            "duration_ms": 60000,
            "metrics": {"digg_count": 10000},
        },
    )
    monkeypatch.delenv("MXNZP_APP_ID", raising=False)
    monkeypatch.delenv("MXNZP_APP_SECRET", raising=False)

    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "collect",
                "task",
                "author",
                "--name",
                "娜说智慧",
                "--skip-expand",
                "--materialize-top",
                "1",
                "--json",
            ]
        )
        == 0
    )
    payload = _read_json(capsys)
    refreshed = Store(db_path).get_collected_material(material_id)

    assert payload["saved_count"] == 1
    assert payload["existing_reused_count"] == 1
    assert payload["understanding_summary"]["final_codex_count"] == 1
    assert refreshed["understanding_provider"] == "codex-agent"
    assert refreshed["understanding_model"] == "gpt-5-codex"
    assert refreshed["summary_text"] == "Codex 深度摘要"


def test_cli_collect_task_discover_authors_dry_run_ranks_candidates(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "mcn.sqlite"
    store = Store(db_path)
    store.init_db()
    sec_uid = store.upsert_douyin_author({"sec_uid": "sec_hot", "nickname": "高频作者", "follower_count": 50000})
    store.upsert_douyin_author_video(
        sec_uid,
        {"work_id": "hot_1", "title": "爆款一", "duration_ms": 60000, "metrics": {"digg_count": 20000}},
    )
    store.upsert_douyin_author_video(
        sec_uid,
        {"work_id": "hot_2", "title": "爆款二", "duration_ms": 60000, "metrics": {"digg_count": 12000}},
    )
    store.upsert_douyin_author({"sec_uid": "sec_low", "nickname": "低频作者"})
    store.upsert_douyin_author_video(
        "sec_low",
        {"work_id": "low_1", "title": "普通", "duration_ms": 60000, "metrics": {"digg_count": 500}},
    )

    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "collect",
                "task",
                "discover-authors",
                "--min-appearances",
                "2",
                "--top-authors",
                "1",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    payload = _read_json(capsys)

    assert payload["task"]["target_scope"] == "discovered_authors"
    assert payload["source_authors_discovered"][0]["author_sec_uid"] == "sec_hot"
    assert payload["source_authors_discovered"][0]["appearances"] == 2


def test_cli_author_materialize_preserves_existing_understanding(tmp_path: Path, capsys, monkeypatch) -> None:
    db_path = tmp_path / "mcn.sqlite"
    store = Store(db_path)
    store.init_db()
    sec_uid = store.upsert_douyin_author({"sec_uid": "sec_1", "nickname": "娜说智慧"})
    run_id = store.create_collection_run(
        task_id=None,
        role_id=None,
        topic="原采集",
        target_count=1,
        like_floor=1,
        super_like_threshold=100,
        tool_provider="mxnzp",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "source_link": "https://example.com/video",
            "title": "八个旺自己的秘密",
            "transcript_text": "旺自己要先稳住能量。",
            "source_platform": "douyin",
            "work_id": "756",
            "author_name": "娜说智慧",
            "author_sec_uid": sec_uid,
        },
        material_understanding={
            "topic_summary": "Codex 深度摘要",
            "hook": "八个旺自己的秘密",
            "core_claim": "先稳住能量。",
            "content_type": "方法清单",
            "understanding_provider": "codex-agent",
            "understanding_model": "gpt-5-codex",
            "status": "success",
        },
        raw={},
    )
    store.upsert_douyin_author_video(
        sec_uid,
        {
            "work_id": "756",
            "title": "八个旺自己的秘密",
            "source_url": "https://example.com/video",
            "duration_ms": 60000,
            "metrics": {"digg_count": 10000},
        },
    )
    monkeypatch.delenv("MXNZP_APP_ID", raising=False)
    monkeypatch.delenv("MXNZP_APP_SECRET", raising=False)

    assert (
        main(
            [
                "--db-path",
                str(db_path),
                "collect",
                "author",
                "materialize",
                "--name",
                "娜说智慧",
                "--top",
                "1",
                "--json",
            ]
        )
        == 0
    )
    payload = _read_json(capsys)
    refreshed = Store(db_path).get_collected_material(material_id)
    assert payload["materialized"][0]["status"] == "existing_preserved"
    assert refreshed["understanding_provider"] == "codex-agent"
    assert refreshed["understanding_model"] == "gpt-5-codex"
    assert refreshed["summary_text"] == "Codex 深度摘要"
