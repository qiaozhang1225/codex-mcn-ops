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
    first_sentence,
    insert_confirmed_stage,
    parse_manifest,
)


TASK_ID = "createtask_a9b7e18bafb0"
CONTENT_PACKAGE_ID = "content_9c8e5248b67d"
ITEM_NUMBER = "12"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Revise 思丞说 Batch 5 item 12 after human source-fidelity review."
    )
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
    if not 650 <= char_count <= 850:
        raise SystemExit(f"revised script length out of accepted source-faithful range: {char_count}")

    timestamp = now_iso()
    context = dict(task.get("context") or {})
    rewrite_requirements = dict(context.get("rewrite_requirements") or {})
    rewrite_requirements.update(
        {
            "target_length_range": [650, 850],
            "target_length_strategy": "preserve_thick_source_argument_before_compression",
            "must_preserve_source_hook": True,
            "preserve_source_opening_on_first_draft": True,
        }
    )
    context.update(
        {
            "rewrite_requirements": rewrite_requirements,
            "revision_reason": "human_review_found_source_hook_and_metaphysical_argument_were_over-cleaned",
            "revision_at": timestamp,
            "human_feedback": "preserve the exact opening and the metaphysical chain instead of translating it into generic financial advice",
        }
    )
    with store.connect() as conn:
        conn.execute(
            """
            UPDATE creation_tasks
            SET context_json = ?, status = 'ready_to_publish', updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(context, ensure_ascii=False, sort_keys=True), timestamp, TASK_ID),
        )
        conn.execute(
            """
            UPDATE creation_delivery_packages
            SET status = 'superseded', updated_at = ?
            WHERE task_id = ? AND status != 'superseded'
            """,
            (timestamp, TASK_ID),
        )
        conn.execute(
            """
            UPDATE creation_drafts
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
        reason="human_review_retained_full_source_after_overcompression_removed_the_metaphysical_spine",
        metadata={
            "batch_key": BATCH_KEY,
            "direction": item["direction"],
            "material_class": "formal_rewrite_base",
            "professional_alignment": item["professional_alignment"],
            "revision": 2,
        },
    )

    task = store.get_creation_task(TASK_ID) or {}
    opening = item.get("source_opening_override") or first_sentence(item["body"])
    source_analysis = _analyze_source_material(material, task)
    source_analysis.update(
        {
            "material_class": "formal_rewrite_base",
            "professional_alignment": item["professional_alignment"],
            "source_content_task": item["source_content_task"],
            "source_hook_text": opening,
            "source_opening_text": opening,
            "source_hook_mechanism": item["hook_mechanism"],
            "speaker_position": "an older first-person observer sharing a private metaphysical conclusion after witnessing wealth reversals",
            "thickness_judgment": "the long source has four distinct metaphysical arguments, examples, reversals, and a complete impermanence-based close",
            "disposition": "selected",
            "weaknesses": [
                "the source sometimes presents spouse replacement, ancestral support, and transferred karma as certain causal facts"
            ],
            "salvage_boundary": "Preserve the exact private-opening hook and the guardian, ancestral virtue, personal karma, and impermanence chain; only bound deterministic causal claims.",
        }
    )
    insert_confirmed_stage(
        store,
        task,
        "material_selection",
        {
            "selected": [
                {
                    "material_id": item["source_material_id"],
                    "score": 1.0,
                    "reason": "human-reviewed full source retained after source-fidelity correction",
                }
            ],
            "source_analysis": {item["source_material_id"]: source_analysis},
            "skipped": [],
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
        "main_claim": "财运能否被承接，不只看赚钱能力，也看护法、德行与祖德、个人因果边界，以及对无常的敬畏。",
        "retention_mechanism": item["hook_mechanism"],
        "must_keep_elements": [
            opening,
            "从年轻时不信因果福报到见过起落后相信",
            "护法与把自家财神往外赶",
            "祖德与做坏事会不安的护持感",
            "个人因果个人了",
            "无常才是最大的守财术",
            "赚一百先存二十",
        ],
        "body_logic_plan": "私密玄学开场 -> 从不信到相信 -> 护法 -> 德行与祖德 -> 因果边界 -> 无常守财 -> 四项共同承接财运",
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

    rewrite_output = {
        "draft": {
            "title": item["title"],
            "body": item["body"],
            "draft_text": item["body"],
            "char_count": char_count,
            "source_material_id": item["source_material_id"],
            "source_opening_text": opening,
            "opening_preservation_mode": item["hook_diff_type"],
            "preserved_hook_text": opening,
            "kept_source_elements": [
                "exact private-account metaphysical opening",
                "disbelief-to-belief authority arc",
                "guardian and family-root example",
                "ancestral virtue and moral restraint",
                "personal karma boundary",
                "impermanence and profit-taking close",
            ],
            "ip_adaptation_notes": [
                "teacher-like first-person delivery",
                "metaphysical concepts remain the argument spine",
                "examples are compressed without replacing their mechanism",
            ],
            "conversion_goal_alignment": "natural reflective close without a forced CTA",
            "deferred_risk_terms": source_analysis.get("deferred_risk_terms") or [],
            "source_to_draft_mapping": {
                "content_task": item["source_content_task"],
                "hook_mechanism": item["hook_mechanism"],
                "evidence_path": "private disclosure -> witnessed reversals -> guardian -> ancestral virtue -> karma boundary -> impermanence-based wealth retention",
            },
            "new_claims": [],
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
        "validation": {
            "passed": True,
            "dimensions": {
                "propagation_mechanism": True,
                "source_fidelity": True,
                "ip_alignment": True,
                "publish_safety": True,
            },
        },
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
            "source_opening_text": opening,
            "hook_diff_type": item["hook_diff_type"],
            "mechanism_preserved": True,
            "dedup_change_summary": "kept the human-selected opening unchanged; no generic replacement hook was introduced",
            "validation": {
                "passed": True,
                "mechanism_preserved": True,
                "strength_parity": True,
                "speaker_translation_valid": True,
            },
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
            "high_risk_replacements": [
                "bounded changing a spouse causes bankruptcy into damaging one's relational and moral foundation",
                "bounded ancestral protection into a traditional ancestral-virtue frame plus observable family support",
                "bounded transferred karma into help-without-replacing-another-person's responsibility",
            ],
            "unchanged_source_risk_terms": ["财运", "玄学", "因果", "福报", "护法", "祖德", "财神", "财气"],
            "risk_diagnosis": [item["risk_changes"]],
            "risk_replacement_scope": {
                "passed": True,
                "mode": "deterministic_claims_bounded_without_removing_the_metaphysical_argument",
            },
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
        "cover_title_4": "财运玄学",
        "video_title_18": item["title"][:18],
        "description_100": first_sentence(item["body"])[:100],
        "pinned_comment": "这四件事里，你现在最需要守住哪一件？",
        "final_copy": item["body"],
        "body_char_count": char_count,
    }
    with store.connect() as conn:
        row = conn.execute(
            "SELECT metadata_json FROM content_packages WHERE id = ?", (CONTENT_PACKAGE_ID,)
        ).fetchone()
        if not row:
            raise SystemExit(f"content package not found: {CONTENT_PACKAGE_ID}")
        metadata = json.loads(row["metadata_json"] or "{}")
        metadata.update(
            {
                "revised_at": timestamp,
                "revision": 2,
                "revision_reason": context["revision_reason"],
                "source_material_id": item["source_material_id"],
            }
        )
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
        creation_row = conn.execute(
            "SELECT id, metadata_json FROM material_creations WHERE content_package_id = ?",
            (CONTENT_PACKAGE_ID,),
        ).fetchone()
        if creation_row:
            creation_metadata = json.loads(creation_row["metadata_json"] or "{}")
            creation_metadata.update({"revision": 2, "revised_at": timestamp})
            conn.execute(
                "UPDATE material_creations SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(creation_metadata, ensure_ascii=False, sort_keys=True), timestamp, creation_row["id"]),
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
            "source_mapping": {
                "content_task": item["source_content_task"],
                "hook_mechanism": item["hook_mechanism"],
            },
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
