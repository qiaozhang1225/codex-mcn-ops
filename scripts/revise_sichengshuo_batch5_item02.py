from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcn_ops.store import Store, now_iso
from scripts.import_sichengshuo_batch5 import (
    BATCH_KEY,
    CREATION_MODE,
    PLATFORM,
    ROLE_ID,
    _analyze_source_material,
    _content_hash,
    _script_char_count,
    assert_material_ready,
    cover_title,
    first_sentence,
    insert_confirmed_stage,
    parse_manifest,
)


TASK_ID = "createtask_d34d392a0513"
CONTENT_PACKAGE_ID = "content_65ad690296ed"
OLD_MATERIAL_ID = "mat_3e6ad8b8c066"
ITEM_NUMBER = "02"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Revise 思丞说 Batch 5 item 02 while retaining workflow history.")
    parser.add_argument("--db-path", default="data/mcn_ops.sqlite")
    parser.add_argument(
        "--manifest",
        default="runs/creation-deliveries/sichengshuo-batch5-20260813/scripts.md",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    item = next(entry for entry in parse_manifest(manifest_path) if entry["number"] == ITEM_NUMBER)
    store = Store(args.db_path)
    store.init_db()
    material = assert_material_ready(store, item)
    task = store.get_creation_task(TASK_ID)
    if not task:
        raise SystemExit(f"creation task not found: {TASK_ID}")
    if task.get("content_package_id") != CONTENT_PACKAGE_ID:
        raise SystemExit(f"unexpected content package: {task.get('content_package_id')}")

    char_count = _script_char_count(item["body"])
    if not 280 <= char_count <= 500:
        raise SystemExit(f"revised script length out of accepted oral range: {char_count}")

    timestamp = now_iso()
    context = dict(task.get("context") or {})
    context.update(
        {
            "selected_material_id": item["source_material_id"],
            "previous_material_id": OLD_MATERIAL_ID,
            "revision_reason": "human_review_replaced_overly_narrow_shishen_topic_with_timely_ai_day_master_entry",
            "revision_at": timestamp,
        }
    )
    with store.connect() as conn:
        conn.execute(
            """
            UPDATE creation_tasks
            SET topic = ?, goal = ?, context_json = ?, status = 'ready_to_publish', updated_at = ?
            WHERE id = ?
            """,
            (
                item["title"],
                "为思丞说第5期生成一条低门槛玄学专业知识口播：借AI热点纠偏，并以日主作为理解命盘的入口",
                json.dumps(context, ensure_ascii=False, sort_keys=True),
                timestamp,
                TASK_ID,
            ),
        )
        conn.execute(
            """
            UPDATE creation_material_selections
            SET selection_status = 'superseded',
                reason = 'superseded_after_human_review_due_to_high_audience_entry_threshold',
                updated_at = ?
            WHERE task_id = ? AND material_id = ?
            """,
            (timestamp, TASK_ID, OLD_MATERIAL_ID),
        )
        conn.execute(
            """
            UPDATE material_creations
            SET status = 'superseded', updated_at = ?
            WHERE content_package_id = ? AND material_id = ?
            """,
            (timestamp, CONTENT_PACKAGE_ID, OLD_MATERIAL_ID),
        )
        conn.execute(
            """
            UPDATE creation_delivery_packages
            SET status = 'superseded', updated_at = ?
            WHERE task_id = ? AND status != 'superseded'
            """,
            (timestamp, TASK_ID),
        )

    store.upsert_creation_material_selection(
        task_id=TASK_ID,
        material_id=item["source_material_id"],
        role_id=ROLE_ID,
        selection_status="selected",
        score=1.0,
        reason="human_review_selected_for_timeliness_broad_entry_and_strong_source_metrics",
        metadata={
            "batch_key": BATCH_KEY,
            "direction": item["direction"],
            "material_class": "formal_rewrite_base",
            "professional_alignment": item["professional_alignment"],
            "replaces_material_id": OLD_MATERIAL_ID,
        },
    )

    task = store.get_creation_task(TASK_ID) or {}
    source_analysis = _analyze_source_material(material, task)
    source_analysis.update(
        {
            "material_class": "formal_rewrite_base",
            "professional_alignment": item["professional_alignment"],
            "source_content_task": item["source_content_task"],
            "source_hook_mechanism": item["hook_mechanism"],
            "thickness_judgment": "source_supplies_hook_and_day_master_entry; new explanatory body is half_original",
            "disposition": "selected",
            "salvage_boundary": "Preserve the AI-warning hook and day-master identification; remove screenshots, brands, prompt recipes, and deterministic AI conclusions.",
        }
    )
    insert_confirmed_stage(
        store,
        task,
        "material_selection",
        {
            "selected": [{"material_id": item["source_material_id"], "score": 1.0, "reason": "human-reviewed replacement"}],
            "source_analysis": {item["source_material_id"]: source_analysis},
            "skipped": [{"material_id": OLD_MATERIAL_ID, "reason": "audience entry threshold too high for this slot"}],
            "status": "needs_confirmation",
            "validation": {"passed": True, "full_transcript_reviewed": True},
            "creation_mode": CREATION_MODE,
        },
    )

    brief = {
        "target_ip": "思丞说",
        "topic": item["title"],
        "goal": task["goal"],
        "platform": PLATFORM,
        "creation_mode": item["creation_mode"],
        "professional_support_mode": "guardrail_only",
        "professional_alignment": item["professional_alignment"],
        "source_content_task": item["source_content_task"],
        "main_claim": "AI可以辅助识别排盘和解释名词，但结论只能参考；初学者应先找到日主，再理解全盘关系。",
        "retention_mechanism": item["hook_mechanism"],
        "must_keep_elements": [source_analysis.get("source_hook_text") or "", "先找到日主", "甲木与癸水取象示例"],
        "body_logic_plan": "AI热点纠错 -> 日主定位方法 -> 甲木癸水示例 -> 日主只是入口 -> 全盘边界",
        "risk_policy": "defer_to_risk_cleanup",
        "risk_watch": [item["risk_changes"]],
        "source_material_ids": [item["source_material_id"]],
    }
    insert_confirmed_stage(
        store,
        task,
        "creation_brief",
        {
            "brief": brief,
            "status": "needs_confirmation",
            "validation": {"passed": True, "viewer_copy_absent": True},
            "creation_mode": CREATION_MODE,
        },
    )

    opening = first_sentence(item["body"])
    rewrite_output = {
        "draft": {
            "title": item["title"],
            "body": item["body"],
            "draft_text": item["body"],
            "char_count": char_count,
            "source_material_id": item["source_material_id"],
            "source_opening_text": source_analysis.get("source_opening_text") or "",
            "opening_preservation_mode": item["hook_diff_type"],
            "preserved_hook_text": opening,
            "kept_source_elements": ["AI-warning hook", "day-master identification", "甲木与癸水 examples"],
            "ip_adaptation_notes": ["teacher-like oral delivery", "low beginner threshold", "traditional-imagery framing"],
            "conversion_goal_alignment": "natural educational close",
            "deferred_risk_terms": source_analysis.get("deferred_risk_terms") or [],
            "source_to_draft_mapping": {
                "content_task": item["source_content_task"],
                "hook_mechanism": item["hook_mechanism"],
                "evidence_path": "AI warning and day-master entry preserved; prompt tutorial replaced",
            },
            "new_claims": ["甲木与癸水仅按传统命理取象作入门说明"],
            "metadata_version": "curated-stage-output-v1",
        },
        "draft_text": item["body"],
        "char_count": char_count,
        "opening_preservation_mode": item["hook_diff_type"],
        "deferred_risk_terms": source_analysis.get("deferred_risk_terms") or [],
        "quality_checks": {
            "opening_preservation": {"passed": True, "mode": item["hook_diff_type"]},
            "source_content_task_preserved": {"passed": True},
            "hook_mechanism_preserved": {"passed": True},
            "evidence_path_preserved": {"passed": True},
            "speaker_translation_valid": {"passed": True},
            "internal_logic_alignment": {"passed": True},
            "length_guardrail": {"passed": True, "char_count": char_count},
        },
        "validation": {"passed": True, "dimensions": {"source_fidelity": True, "ip_alignment": True}},
        "status": "needs_confirmation",
        "creation_mode": CREATION_MODE,
    }
    insert_confirmed_stage(store, task, "rewrite_draft", rewrite_output)

    insert_confirmed_stage(
        store,
        task,
        "hook_enhancement",
        {
            "hooks": [opening],
            "selected_hook": opening,
            "body": item["body"],
            "source_opening_text": source_analysis.get("source_opening_text") or "",
            "hook_diff_type": item["hook_diff_type"],
            "mechanism_preserved": True,
            "dedup_change_summary": "preserved the warning mechanism while translating from prompt advice to bounded AI use",
            "validation": {"passed": True, "mechanism_preserved": True, "strength_parity": True, "speaker_translation_valid": True},
            "status": "needs_confirmation",
            "creation_mode": CREATION_MODE,
        },
    )

    insert_confirmed_stage(
        store,
        task,
        "risk_cleanup",
        {
            "cleaned_body": item["body"],
            "high_risk_replacements": ["removed screenshots and prompt recipes", "removed product names", "bounded AI output as reference only"],
            "unchanged_source_risk_terms": [],
            "risk_diagnosis": [item["risk_changes"]],
            "risk_replacement_scope": {"passed": True, "mode": "mechanism_preserved_claims_bounded"},
            "overall_risk": "publishable_after_claim_level_review",
            "validation": {
                "passed": True,
                "diagnosis_risk": True,
                "single_cause_risk": True,
                "universalization_risk": True,
                "fabricated_evidence_risk": True,
                "certainty_and_outcome_risk": True,
            },
            "status": "needs_confirmation",
            "creation_mode": CREATION_MODE,
        },
    )

    package = {
        "cover_title_4": cover_title(item["title"]),
        "video_title_18": item["title"][:18],
        "description_100": first_sentence(item["body"])[:100],
        "pinned_comment": "你知道自己是什么日主吗？",
        "final_copy": item["body"],
        "body_char_count": char_count,
    }
    with store.connect() as conn:
        row = conn.execute("SELECT metadata_json FROM content_packages WHERE id = ?", (CONTENT_PACKAGE_ID,)).fetchone()
        metadata = json.loads(row["metadata_json"] or "{}")
        metadata.update({"revised_at": timestamp, "revision": 2, "source_material_id": item["source_material_id"]})
        conn.execute(
            """
            UPDATE content_packages
            SET title = ?, body = ?, hashtags_json = ?, metadata_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                package["video_title_18"],
                item["body"],
                json.dumps([item["direction"]], ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                timestamp,
                CONTENT_PACKAGE_ID,
            ),
        )

    store.insert_material_creation(
        material_id=item["source_material_id"],
        role_id=ROLE_ID,
        content_package_id=CONTENT_PACKAGE_ID,
        task_id=None,
        platform=PLATFORM,
        rewrite_angle=item["direction"],
        status="draft",
        metadata={
            "creation_task_id": TASK_ID,
            "batch_key": BATCH_KEY,
            "batch_number": int(item["number"]),
            "revision": 2,
            "replaces_material_id": OLD_MATERIAL_ID,
        },
    )
    delivery_package_id = store.insert_creation_delivery_package(
        task_id=TASK_ID,
        platform=PLATFORM,
        package=package,
        content_package_id=CONTENT_PACKAGE_ID,
        markdown_path=str(manifest_path),
        status="draft",
    )
    insert_confirmed_stage(
        store,
        task,
        "publish_format",
        {
            "content_package_id": CONTENT_PACKAGE_ID,
            "delivery_package_id": delivery_package_id,
            "publish_package": package,
            "body_char_count": char_count,
            "validation": {"passed": True, "final_copy_locked": True},
            "status": "needs_confirmation",
            "creation_mode": CREATION_MODE,
        },
    )

    delivery_markdown = (
        f"# {item['number']} {item['title']}\n\n"
        f"- source_material_id: {item['source_material_id']}\n"
        f"- creation_mode: {item['creation_mode']}\n"
        f"- source_content_task: {item['source_content_task']}\n"
        f"- hook_mechanism: {item['hook_mechanism']}\n"
        f"- risk_changes: {item['risk_changes']}\n\n"
        f"## Final Copy\n\n{item['body']}\n"
    )
    insert_confirmed_stage(
        store,
        task,
        "delivery",
        {
            "delivery_markdown": delivery_markdown,
            "source_material_id": item["source_material_id"],
            "creation_mode": item["creation_mode"],
            "source_mapping": {"content_task": item["source_content_task"], "hook_mechanism": item["hook_mechanism"]},
            "professional_card_ids": [],
            "risk_changes": [item["risk_changes"]],
            "publish_fields_hash": _content_hash(json.dumps(package, ensure_ascii=False, sort_keys=True)),
            "validation": {"passed": True, "confirmed_artifacts_only": True},
            "status": "needs_confirmation",
            "creation_mode_label": CREATION_MODE,
        },
    )

    print(
        json.dumps(
            {
                "task_id": TASK_ID,
                "item_number": ITEM_NUMBER,
                "source_material_id": item["source_material_id"],
                "content_package_id": CONTENT_PACKAGE_ID,
                "delivery_package_id": delivery_package_id,
                "body_char_count": char_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
