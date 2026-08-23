from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEPENDENT_TABLES = (
    "creation_material_selections",
    "material_creations",
    "material_inventory_classifications",
)


def placeholders(values: list[str]) -> str:
    return ", ".join("?" for _ in values)


def load_json(value: Any, default: Any) -> Any:
    try:
        parsed = json.loads(str(value or ""))
    except json.JSONDecodeError:
        return default
    return parsed


def select_materials(connection: sqlite3.Connection, min_digg_count: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        WITH latest_observation AS (
            SELECT o.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY source_work_id
                       ORDER BY observed_at DESC, id DESC
                   ) AS row_number
            FROM source_observations o
        )
        SELECT m.id AS material_id,
               m.run_id,
               m.source_work_id,
               m.transcription_id,
               w.platform_work_id,
               w.title,
               a.display_name AS author_name,
               CAST(COALESCE(json_extract(o.metrics_json, '$.digg_count'), 0) AS INTEGER)
                   AS digg_count
        FROM collected_materials m
        JOIN source_works w ON w.id = m.source_work_id
        LEFT JOIN source_authors a ON a.id = w.author_id
        LEFT JOIN latest_observation o
               ON o.source_work_id = w.id AND o.row_number = 1
        WHERE w.platform = 'wechat_channels'
          AND CAST(COALESCE(json_extract(o.metrics_json, '$.digg_count'), 0) AS INTEGER) < ?
        ORDER BY digg_count DESC, m.id
        """,
        (min_digg_count,),
    ).fetchall()
    return [dict(row) for row in rows]


def assert_no_downstream_usage(connection: sqlite3.Connection, material_ids: list[str]) -> None:
    marker = placeholders(material_ids)
    conflicts: dict[str, int] = {}
    for table in DEPENDENT_TABLES:
        count = int(
            connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE material_id IN ({marker})',
                material_ids,
            ).fetchone()[0]
        )
        if count:
            conflicts[table] = count
    if conflicts:
        raise RuntimeError(f"materials have downstream usage and cannot be cleaned: {conflicts}")


def annotate_runs(
    connection: sqlite3.Connection,
    *,
    run_ids: list[str],
    material_ids: list[str],
    min_digg_count: int,
    cleaned_at: str,
) -> None:
    for run_id in run_ids:
        row = connection.execute(
            "SELECT summary_json FROM collection_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            continue
        summary = load_json(row[0], {})
        cleanups = list(summary.get("post_collection_cleanups") or [])
        cleanups.append(
            {
                "cleaned_at": cleaned_at,
                "criterion": "wechat_channels_digg_count_below_floor",
                "min_digg_count": min_digg_count,
                "removed_material_ids": material_ids,
                "history_preserved": True,
            }
        )
        summary["post_collection_cleanups"] = cleanups
        connection.execute(
            "UPDATE collection_runs SET summary_json = ? WHERE id = ?",
            (json.dumps(summary, ensure_ascii=False, sort_keys=True), run_id),
        )


def clean(
    connection: sqlite3.Connection,
    *,
    cache_path: Path,
    materials: list[dict[str, Any]],
    min_digg_count: int,
) -> dict[str, Any]:
    material_ids = [str(item["material_id"]) for item in materials]
    source_work_ids = [str(item["source_work_id"]) for item in materials]
    transcription_ids = [
        str(item["transcription_id"])
        for item in materials
        if item.get("transcription_id")
    ]
    platform_work_ids = [str(item["platform_work_id"]) for item in materials]
    marker = placeholders(material_ids)
    work_marker = placeholders(source_work_ids)
    transcription_marker = placeholders(transcription_ids)
    cleaned_at = datetime.now(timezone.utc).isoformat()

    assert_no_downstream_usage(connection, material_ids)
    run_ids = [
        str(row[0])
        for row in connection.execute(
            f"SELECT DISTINCT run_id FROM collection_candidates WHERE material_id IN ({marker})",
            material_ids,
        ).fetchall()
    ]
    candidate_count = int(
        connection.execute(
            f"SELECT COUNT(*) FROM collection_candidates WHERE material_id IN ({marker})",
            material_ids,
        ).fetchone()[0]
    )
    connection.execute("ATTACH DATABASE ? AS asr_cache", (str(cache_path),))
    cache_keys = [
        str(row[0])
        for work_id in platform_work_ids
        for row in connection.execute(
            """
            SELECT DISTINCT tc.cache_key
            FROM asr_cache.transcription_cache tc, json_tree(tc.result_json) jt
            WHERE jt.key = 'work_id' AND CAST(jt.value AS TEXT) = ?
            """,
            (work_id,),
        ).fetchall()
    ]

    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            f"""
            UPDATE collection_candidates
            SET material_id = NULL,
                status = 'below_threshold',
                skip_reason = 'cleaned_below_viral_floor',
                skip_detail = ?,
                threshold_mode = 'floor',
                updated_at = ?
            WHERE material_id IN ({marker})
            """,
            [f"视频点赞低于清洗后的爆款门槛 {min_digg_count}。", cleaned_at, *material_ids],
        )
        connection.execute(
            f"DELETE FROM source_observations WHERE source_work_id IN ({work_marker}) AND observation_type = 'material'",
            source_work_ids,
        )
        connection.execute(
            f"DELETE FROM material_role_matches WHERE material_id IN ({marker})",
            material_ids,
        )
        connection.execute(
            f"DELETE FROM material_understanding_logs WHERE material_id IN ({marker})",
            material_ids,
        )
        connection.execute(
            f"DELETE FROM collected_materials WHERE id IN ({marker})",
            material_ids,
        )
        if transcription_ids:
            connection.execute(
                f"""
                DELETE FROM material_transcriptions
                WHERE id IN ({transcription_marker})
                  AND NOT EXISTS (
                      SELECT 1 FROM collected_materials m
                      WHERE m.transcription_id = material_transcriptions.id
                  )
                """,
                transcription_ids,
            )
        if cache_keys:
            cache_marker = placeholders(cache_keys)
            connection.execute(
                f"DELETE FROM asr_cache.transcription_jobs WHERE cache_key IN ({cache_marker})",
                cache_keys,
            )
            connection.execute(
                f"DELETE FROM asr_cache.transcription_cache WHERE cache_key IN ({cache_marker})",
                cache_keys,
            )
        annotate_runs(
            connection,
            run_ids=run_ids,
            material_ids=material_ids,
            min_digg_count=min_digg_count,
            cleaned_at=cleaned_at,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    foreign_key_issues = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    return {
        "cleaned_at": cleaned_at,
        "min_digg_count": min_digg_count,
        "removed_material_ids": material_ids,
        "removed_transcription_ids": transcription_ids,
        "removed_asr_cache_keys": cache_keys,
        "updated_candidate_rows": candidate_count,
        "annotated_run_ids": run_ids,
        "integrity_check": integrity,
        "foreign_key_issue_count": foreign_key_issues,
    }


def backup_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as backup:
        source_connection.backup(backup)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove WeChat Channels formal materials below a verified digg floor."
    )
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--cache-path", type=Path, required=True)
    parser.add_argument("--min-digg-count", type=int, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.min_digg_count < 1:
        raise SystemExit("--min-digg-count must be positive")

    with sqlite3.connect(args.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        materials = select_materials(connection, args.min_digg_count)
    plan = {
        "apply": args.apply,
        "min_digg_count": args.min_digg_count,
        "material_count": len(materials),
        "materials": materials,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not materials:
        print(json.dumps({**plan, "result": "nothing_to_clean"}, ensure_ascii=False, indent=2))
        return 0

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_dir = args.backup_dir or args.db_path.parent / "backups"
    database_backup = backup_dir / f"mcn_ops-before-channels-floor-{args.min_digg_count}-{timestamp}.sqlite"
    cache_backup = backup_dir / f"transcription-cache-before-channels-floor-{args.min_digg_count}-{timestamp}.sqlite"
    backup_database(args.db_path, database_backup)
    backup_database(args.cache_path, cache_backup)

    with sqlite3.connect(args.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        result = clean(
            connection,
            cache_path=args.cache_path,
            materials=materials,
            min_digg_count=args.min_digg_count,
        )
    print(
        json.dumps(
            {
                **plan,
                "database_backup": str(database_backup),
                "cache_backup": str(cache_backup),
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
