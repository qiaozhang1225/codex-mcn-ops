from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcn_ops.creation.contracts import validate_stage_submission


CASES = json.loads((Path(__file__).parent / "fixtures" / "ip_recreation_golden_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_golden_material_decisions_satisfy_contract(case: dict) -> None:
    material_id = f"material_{case['id']}"
    conflict = "中心处方与IP稳定边界冲突" if case["alignment"] in {"repairable_conflict", "hard_conflict"} else ""
    result = {
        "materials": [
            {
                "material_id": material_id,
                "material_class": case["material_class"],
                "source_content_task": case["source_excerpt"],
                "source_hook_mechanism": "direct_topic_entry",
                "speaker_position": "source_speaker",
                "thickness_judgment": "enough" if case["material_class"] == "formal_rewrite_base" else "thin_or_incompatible",
                "professional_alignment": case["alignment"],
                "conflicting_claim": conflict,
                "professional_disposition": case["disposition"],
                "salvage_boundary": "保留内容任务，只修正冲突主张" if case["alignment"] == "repairable_conflict" else "按分类处理",
                "selection_rationale": "golden evaluation decision",
                "selection_weaknesses": [],
            }
        ]
    }
    validation = validate_stage_submission(
        "material_selection",
        result,
        {"candidate_materials": [{"id": material_id}]},
    )
    if case["material_class"] == "formal_rewrite_base":
        assert validation.passed is True
    else:
        assert validation.structural_errors == []
        assert "no formal rewrite base passed" in " ".join(validation.gate_failures)


def test_golden_fixture_covers_three_ip_shapes_and_twenty_four_cases() -> None:
    assert len(CASES) == 24
    assert {case["ip"] for case in CASES} == {"songlixinli", "sichengshuo", "generic"}
    assert {case["alignment"] for case in CASES} == {"aligned", "acceptable_variance", "repairable_conflict", "hard_conflict"}
