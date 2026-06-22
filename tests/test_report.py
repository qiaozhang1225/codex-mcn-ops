from __future__ import annotations

from pathlib import Path

from mcn_ops.report import build_daily_report
from mcn_ops.store import Store


def test_daily_report_has_empty_state(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()

    report = build_daily_report(store, "2099-01-01")

    assert "# MCN Ops Daily Report - 2099-01-01" in report
    assert "No publish jobs created." in report
