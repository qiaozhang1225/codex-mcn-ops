from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


SENSITIVE_REGEXES = (
    ("signed_finder_media_url", re.compile(r"https?://finder\.video\.qq\.com/", re.IGNORECASE)),
    ("url_token_query", re.compile(r"(?:urltoken|authkey)=", re.IGNORECASE)),
    (
        "unredacted_decode_key",
        re.compile(r'"(?:decodekey|decode_key|decrypt_key)"\s*:\s*"(?!<redacted>)', re.IGNORECASE),
    ),
    ("cloud_secret_field", re.compile(r'"cloud_secret"\s*:', re.IGNORECASE)),
    ("worker_secret_field", re.compile(r'"secret_token"\s*:', re.IGNORECASE)),
)


def load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def fetch_candidates(connection: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
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
        SELECT c.id AS candidate_id,
               c.run_id,
               c.status,
               c.selection_reason,
               c.skip_reason,
               c.skip_detail,
               c.threshold_mode,
               c.material_id,
               w.id AS source_work_id,
               w.platform_work_id,
               w.title,
               w.published_at,
               w.duration_ms,
               a.platform_author_id,
               a.display_name AS author_name,
               o.metrics_json,
               o.payload_json,
               o.observed_at
        FROM collection_candidates c
        JOIN source_works w ON w.id = c.source_work_id
        LEFT JOIN source_authors a ON a.id = w.author_id
        LEFT JOIN latest_observation o
               ON o.source_work_id = w.id AND o.row_number = 1
        WHERE c.run_id = ?
        ORDER BY c.created_at, c.id
        """,
        (run_id,),
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        payload = load_json(row["payload_json"], {})
        identity = payload.get("identity") if isinstance(payload, dict) else {}
        metrics = load_json(row["metrics_json"], {})
        candidates.append(
            {
                "candidate_id": row["candidate_id"],
                "run_id": row["run_id"],
                "status": row["status"],
                "selection_reason": row["selection_reason"],
                "skip_reason": row["skip_reason"],
                "skip_detail": row["skip_detail"],
                "threshold_mode": row["threshold_mode"],
                "material_id": row["material_id"],
                "source_work_id": row["source_work_id"],
                "platform_work_id": row["platform_work_id"],
                "title": row["title"],
                "published_at": row["published_at"],
                "duration_ms": row["duration_ms"],
                "platform_author_id": row["platform_author_id"],
                "author_name": row["author_name"],
                "public_metrics": metrics,
                "matched_search_keywords": list((identity or {}).get("matched_search_keywords") or []),
                "observed_at": row["observed_at"],
            }
        )
    return candidates


def fetch_materials(connection: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
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
        SELECT DISTINCT
               m.id AS material_id,
               m.run_id AS material_origin_run_id,
               m.status AS material_status,
               m.clean_title,
               m.summary_text,
               m.hook_text,
               m.core_claim,
               m.content_type,
               m.audience,
               m.emotion_trigger,
               m.risk_level,
               m.material_understanding_json,
               m.understanding_provider,
               m.understanding_model,
               m.understanding_status,
               m.eligibility_status,
               m.knowledge_core_score,
               m.oral_script_fit_score,
               m.ip_fit_score,
               w.id AS source_work_id,
               w.platform_work_id,
               w.title,
               w.duration_ms,
               a.platform_author_id,
               a.display_name AS author_name,
               o.metrics_json,
               t.provider AS transcription_provider,
               t.model AS transcription_model,
               t.audio_sha256,
               t.transcript_text,
               mr.role_id,
               mr.fit_score AS role_fit_score,
               mr.decision AS role_decision,
               mr.reasons_json AS role_reasons_json,
               mr.matched_keywords_json
        FROM collection_candidates c
        JOIN collected_materials m ON m.id = c.material_id
        JOIN source_works w ON w.id = m.source_work_id
        LEFT JOIN source_authors a ON a.id = w.author_id
        LEFT JOIN latest_observation o
               ON o.source_work_id = w.id AND o.row_number = 1
        LEFT JOIN material_transcriptions t ON t.id = m.transcription_id
        LEFT JOIN material_role_matches mr
               ON mr.material_id = m.id AND mr.role_id = c.role_id
        WHERE c.run_id = ? AND c.material_id IS NOT NULL
        ORDER BY m.id
        """,
        (run_id,),
    ).fetchall()
    return [
        {
            "material_id": row["material_id"],
            "material_origin_run_id": row["material_origin_run_id"],
            "material_status": row["material_status"],
            "source_work_id": row["source_work_id"],
            "platform_work_id": row["platform_work_id"],
            "title": row["title"],
            "clean_title": row["clean_title"],
            "duration_ms": row["duration_ms"],
            "platform_author_id": row["platform_author_id"],
            "author_name": row["author_name"],
            "public_metrics": load_json(row["metrics_json"], {}),
            "transcription_provider": row["transcription_provider"],
            "transcription_model": row["transcription_model"],
            "audio_sha256": row["audio_sha256"],
            "transcript_text": row["transcript_text"],
            "summary_text": row["summary_text"],
            "hook_text": row["hook_text"],
            "core_claim": row["core_claim"],
            "content_type": row["content_type"],
            "audience": row["audience"],
            "emotion_trigger": row["emotion_trigger"],
            "risk_level": row["risk_level"],
            "material_understanding": load_json(row["material_understanding_json"], {}),
            "understanding_provider": row["understanding_provider"],
            "understanding_model": row["understanding_model"],
            "understanding_status": row["understanding_status"],
            "eligibility_status": row["eligibility_status"],
            "knowledge_core_score": row["knowledge_core_score"],
            "oral_script_fit_score": row["oral_script_fit_score"],
            "ip_fit_score": row["ip_fit_score"],
            "role_id": row["role_id"],
            "role_fit_score": row["role_fit_score"],
            "role_decision": row["role_decision"],
            "role_reasons": load_json(row["role_reasons_json"], []),
            "matched_role_keywords": load_json(row["matched_keywords_json"], []),
        }
        for row in rows
    ]


def build_account_rollup(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    accounts: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "candidate_count": 0,
            "saved_or_reused_count": 0,
            "digg_count_sum": 0,
            "digg_count_max": 0,
            "share_count_sum": 0,
            "share_count_max": 0,
            "matched_search_keywords": set(),
        }
    )
    for candidate in candidates:
        key = str(candidate.get("platform_author_id") or candidate.get("author_name") or "unknown")
        account = accounts[key]
        account["platform_author_id"] = candidate.get("platform_author_id")
        account["author_name"] = candidate.get("author_name")
        account["candidate_count"] += 1
        if candidate.get("material_id"):
            account["saved_or_reused_count"] += 1
        metrics = candidate.get("public_metrics") or {}
        digg = int(metrics.get("digg_count") or 0)
        share = int(metrics.get("share_count") or 0)
        account["digg_count_sum"] += digg
        account["digg_count_max"] = max(account["digg_count_max"], digg)
        account["share_count_sum"] += share
        account["share_count_max"] = max(account["share_count_max"], share)
        account["matched_search_keywords"].update(candidate.get("matched_search_keywords") or [])
    rows = []
    for account in accounts.values():
        account["matched_search_keywords"] = sorted(account["matched_search_keywords"])
        rows.append(dict(account))
    return sorted(
        rows,
        key=lambda item: (
            item["saved_or_reused_count"],
            item["share_count_max"],
            item["digg_count_max"],
            item["candidate_count"],
        ),
        reverse=True,
    )


def safety_scan(connection: sqlite3.Connection) -> dict[str, Any]:
    matches: dict[str, int] = {name: 0 for name, _ in SENSITIVE_REGEXES}
    scanned_cells = 0
    for table_row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        table = str(table_row[0])
        text_columns = [
            str(row[1])
            for row in connection.execute(f'PRAGMA table_info("{table}")')
            if str(row[2] or "").upper() in {"TEXT", ""}
        ]
        if not text_columns:
            continue
        selection = ", ".join(f'"{column}"' for column in text_columns)
        for row in connection.execute(f'SELECT {selection} FROM "{table}"'):
            for value in row:
                if value is None:
                    continue
                scanned_cells += 1
                text = str(value)
                for name, pattern in SENSITIVE_REGEXES:
                    if pattern.search(text):
                        matches[name] += 1
    return {
        "scanned_text_cells": scanned_cells,
        "sensitive_pattern_counts": matches,
        "passed": not any(matches.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a sanitized WeChat Channels collection run.")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db_path) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute("SELECT * FROM collection_runs WHERE id = ?", (args.run_id,)).fetchone()
        if run is None:
            raise SystemExit(f"collection run not found: {args.run_id}")
        candidates = fetch_candidates(connection, args.run_id)
        materials = fetch_materials(connection, args.run_id)
        accounts = build_account_rollup(candidates)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_issues = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        safety = safety_scan(connection)

    status_counts: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        status_counts[str(candidate.get("status") or "unknown")] += 1
    manifest = {
        "run": {key: run[key] for key in run.keys() if key != "summary_json"},
        "candidate_count": len(candidates),
        "candidate_status_counts": dict(sorted(status_counts.items())),
        "material_count": len(materials),
        "new_material_count": sum(
            1 for material in materials if material["material_origin_run_id"] == args.run_id
        ),
        "reused_material_count": sum(
            1 for material in materials if material["material_origin_run_id"] != args.run_id
        ),
        "account_count": len(accounts),
        "database_integrity": integrity,
        "foreign_key_issue_count": foreign_key_issues,
        "safety_scan_passed": safety["passed"],
    }
    write_json(output_dir / "manifest.json", manifest)
    write_jsonl(output_dir / "candidates.jsonl", candidates)
    write_jsonl(output_dir / "materials.jsonl", materials)
    write_json(output_dir / "accounts.json", accounts)
    write_json(output_dir / "safety-scan.json", safety)
    with (output_dir / "accounts.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(accounts[0].keys()) if accounts else [])
        if accounts:
            writer.writeheader()
            for account in accounts:
                writer.writerow(
                    {
                        **account,
                        "matched_search_keywords": " | ".join(account["matched_search_keywords"]),
                    }
                )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
