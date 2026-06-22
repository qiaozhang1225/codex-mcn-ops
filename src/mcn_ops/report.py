from __future__ import annotations

from datetime import date

from .store import Store


def build_daily_report(store: Store, report_date: str | None = None) -> str:
    target_date = report_date or date.today().isoformat()
    with store.connect() as conn:
        jobs = conn.execute(
            """
            SELECT platform, status, COUNT(*) AS count
            FROM publish_jobs
            WHERE substr(created_at, 1, 10) = ?
            GROUP BY platform, status
            ORDER BY platform, status
            """,
            (target_date,),
        ).fetchall()
        logs = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM publish_run_logs
            WHERE substr(created_at, 1, 10) = ?
            GROUP BY status
            ORDER BY status
            """,
            (target_date,),
        ).fetchall()
        snapshots = conn.execute(
            """
            SELECT platform, COUNT(*) AS count
            FROM tracking_snapshots
            WHERE substr(created_at, 1, 10) = ?
            GROUP BY platform
            ORDER BY platform
            """,
            (target_date,),
        ).fetchall()

    lines = [
        f"# MCN Ops Daily Report - {target_date}",
        "",
        "## Publish Jobs",
    ]
    if jobs:
        lines.extend(f"- {row['platform']} / {row['status']}: {row['count']}" for row in jobs)
    else:
        lines.append("- No publish jobs created.")

    lines.extend(["", "## Run Logs"])
    if logs:
        lines.extend(f"- {row['status']}: {row['count']}" for row in logs)
    else:
        lines.append("- No run logs recorded.")

    lines.extend(["", "## Tracking Snapshots"])
    if snapshots:
        lines.extend(f"- {row['platform']}: {row['count']}" for row in snapshots)
    else:
        lines.append("- No tracking snapshots recorded.")

    return "\n".join(lines) + "\n"
