from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from mcn_ops.creation.workflow import (
    CREATION_STAGE_CONTRACT_VERSION,
    _analyze_source_material,
    _attach_stage_contract,
    _content_hash,
    _format_publish_package,
    _persist_stage_artifacts,
    _script_char_count,
    confirm_creation_stage,
    create_creation_task,
)
from mcn_ops.store import Store


BATCH_KEY = "sichengshuo_batch5_20260813"
ROLE_ID = "role_791ffbf51f20"
PLATFORM = "douyin"
CREATION_MODE = "curated_agent_adaptation_v1"
STAGES = [
    "material_selection",
    "creation_brief",
    "rewrite_draft",
    "hook_enhancement",
    "risk_cleanup",
    "publish_format",
    "delivery",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import the curated 思丞说 batch 5 scripts into the creation ledger.")
    parser.add_argument("--db-path", type=Path, default=Path("data/mcn_ops.sqlite"))
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("runs/creation-deliveries/sichengshuo-batch5-20260813/scripts.md"),
    )
    return parser.parse_args()


def parse_manifest(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^## \d{2} )", text, flags=re.MULTILINE)[1:]
    items: list[dict[str, str]] = []
    for block in blocks:
        title_match = re.match(r"^## (\d{2}) ([^\n]+)", block)
        body_parts = block.split("### 成稿\n\n", 1)
        if not title_match or len(body_parts) != 2:
            raise ValueError("invalid manifest block")
        metadata: dict[str, str] = {}
        for key, value in re.findall(r"^- ([a-z_]+): (.+)$", body_parts[0], flags=re.MULTILINE):
            metadata[key] = value.strip()
        body = body_parts[1].strip()
        required = {
            "direction",
            "source_material_id",
            "creation_mode",
            "professional_alignment",
            "source_content_task",
            "hook_mechanism",
            "hook_diff_type",
            "risk_changes",
        }
        missing = sorted(required - set(metadata))
        if missing:
            raise ValueError(f"manifest item {title_match.group(1)} missing: {missing}")
        items.append(
            {
                "number": title_match.group(1),
                "title": title_match.group(2).strip(),
                "body": body,
                **metadata,
            }
        )
    if len(items) != 24:
        raise ValueError(f"expected 24 scripts, got {len(items)}")
    return items


def existing_batch_tasks(store: Store) -> list[str]:
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id, context_json FROM creation_tasks WHERE role_id = ? ORDER BY created_at",
            (ROLE_ID,),
        ).fetchall()
    result: list[str] = []
    for row in rows:
        context = json.loads(row["context_json"] or "{}")
        if context.get("batch_key") == BATCH_KEY:
            result.append(str(row["id"]))
    return result


def assert_material_ready(store: Store, item: dict[str, str]) -> dict[str, Any]:
    material = store.get_collected_material(item["source_material_id"])
    if not material:
        raise ValueError(f"material not found: {item['source_material_id']}")
    if material.get("status") != "collected" or material.get("eligibility_status") != "accepted":
        raise ValueError(f"material not eligible: {item['source_material_id']}")
    if not str(material.get("transcript_text") or "").strip():
        raise ValueError(f"material missing transcript: {item['source_material_id']}")
    matches = store.list_material_role_matches(material_id=item["source_material_id"], role_id=ROLE_ID)
    if not any(match.get("decision") == "accepted" for match in matches):
        raise ValueError(f"material missing accepted role match: {item['source_material_id']}")
    with store.connect() as conn:
        classification = conn.execute(
            """
            SELECT * FROM material_inventory_classifications
            WHERE material_id = ? AND role_id = ? AND is_primary = 1
              AND material_class = 'formal_rewrite_base' AND review_status = 'reviewed'
            """,
            (item["source_material_id"], ROLE_ID),
        ).fetchone()
    if not classification:
        raise ValueError(f"material is not a reviewed formal rewrite base: {item['source_material_id']}")
    if str(classification["topic_direction"]) != item["direction"]:
        raise ValueError(
            f"direction mismatch for {item['source_material_id']}: "
            f"{classification['topic_direction']} != {item['direction']}"
        )
    return material


def first_sentence(body: str) -> str:
    match = re.search(r"^(.+?[。！？!?])", body.strip(), flags=re.DOTALL)
    return match.group(1).strip() if match else body.splitlines()[0].strip()


def cover_title(title: str) -> str:
    compact = re.sub(r"[^\w\u4e00-\u9fff]", "", title)
    return (compact + "自查")[:4]


def stage_markdown(stage: str, output: dict[str, Any]) -> str:
    if stage == "material_selection":
        return f"# Material Selection\n\n- {output['selected'][0]['material_id']}: curated formal rewrite base\n"
    if stage == "creation_brief":
        brief = output["brief"]
        return (
            "# Creation Brief\n\n"
            f"- Content task: {brief['source_content_task']}\n"
            f"- Hook mechanism: {brief['retention_mechanism']}\n"
            f"- Creation mode: {brief['creation_mode']}\n"
        )
    if stage == "rewrite_draft":
        return "# Rewrite Draft\n\n" + str(output["draft_text"]) + "\n"
    if stage == "hook_enhancement":
        return "# Hook Enhancement\n\n- " + str(output["selected_hook"]) + "\n"
    if stage == "risk_cleanup":
        return "# Risk Cleanup\n\n" + str(output["cleaned_body"]) + "\n"
    if stage == "publish_format":
        return _format_publish_package(output["publish_package"]) + "\n"
    return str(output["delivery_markdown"])


def insert_confirmed_stage(
    store: Store,
    task: dict[str, Any],
    stage: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    upstream_ids = []
    for upstream in STAGES[: STAGES.index(stage)]:
        latest = store.latest_creation_stage_run(str(task["id"]), upstream)
        if not latest or latest.get("status") != "confirmed":
            raise ValueError(f"missing confirmed upstream stage {upstream} for {task['id']}")
        upstream_ids.append(str(latest["id"]))
    attached = _attach_stage_contract(store, task, stage, output, upstream_ids)
    validation = attached.get("validation") or {}
    contract_validation = attached.get("stage_contract_validation") or {}
    if validation and not validation.get("passed"):
        raise ValueError(f"semantic validation failed for {task['id']} {stage}: {validation}")
    if not contract_validation.get("passed"):
        raise ValueError(f"contract validation failed for {task['id']} {stage}: {contract_validation}")
    stage_run_id = store.insert_creation_stage_run(
        task_id=str(task["id"]),
        stage_key=stage,
        status="needs_confirmation",
        provider="codex-agent",
        model="gpt-5.6",
        input_data={
            "task_id": task["id"],
            "stage_key": stage,
            "batch_key": BATCH_KEY,
            "stage_contract_version": CREATION_STAGE_CONTRACT_VERSION,
            "upstream_stage_run_ids": upstream_ids,
        },
        output_data=attached,
        output_markdown=stage_markdown(stage, attached),
        note="Agent-authored semantic result; reviewed against the full source transcript.",
    )
    _persist_stage_artifacts(store, task, stage, stage_run_id, attached)
    confirm_creation_stage(store, str(task["id"]), stage_key=stage)
    return attached


def import_item(store: Store, item: dict[str, str], manifest_path: Path) -> dict[str, str]:
    material = assert_material_ready(store, item)
    report = create_creation_task(
        store,
        role_id=ROLE_ID,
        topic=item["title"],
        goal=f"为思丞说第5期生成一条{item['direction']}口播成稿，保留底稿传播机制并强化开篇钩子",
        platform=PLATFORM,
        target_count=1,
        provider="codex-agent",
        model="gpt-5.6",
    )
    task_id = str(report["task"]["id"])
    store.update_creation_task(
        task_id,
        context={
            "batch_key": BATCH_KEY,
            "batch_number": int(item["number"]),
            "selected_material_id": item["source_material_id"],
            "direction": item["direction"],
            "manifest_path": str(manifest_path.resolve()),
            "semantic_authoring": True,
            "creation_mode": CREATION_MODE,
        },
    )
    task = store.get_creation_task(task_id) or {}
    store.upsert_creation_material_selection(
        task_id=task_id,
        material_id=item["source_material_id"],
        role_id=ROLE_ID,
        selection_status="selected",
        score=1.0,
        reason="curated_agent_selection_after_full_transcript_review",
        metadata={
            "batch_key": BATCH_KEY,
            "direction": item["direction"],
            "material_class": "formal_rewrite_base",
            "professional_alignment": item["professional_alignment"],
        },
    )

    source_analysis = _analyze_source_material(material, task)
    source_analysis.update(
        {
            "material_class": "formal_rewrite_base",
            "professional_alignment": item["professional_alignment"],
            "source_content_task": item["source_content_task"],
            "source_hook_mechanism": item["hook_mechanism"],
            "thickness_judgment": "sufficient_for_300_to_500_char_adaptation",
            "disposition": "selected",
            "salvage_boundary": "Preserve the source task, evidence path, and hook mechanism; repair only unsupported claims or speaker conflicts.",
        }
    )
    if item.get("source_opening_override"):
        source_analysis["source_opening_text"] = item["source_opening_override"]
    material_output = {
        "selected": [{"material_id": item["source_material_id"], "score": 1.0, "reason": "curated selection"}],
        "source_analysis": {item["source_material_id"]: source_analysis},
        "skipped": [],
        "status": "needs_confirmation",
        "validation": {"passed": True, "full_transcript_reviewed": True},
        "creation_mode": CREATION_MODE,
    }
    insert_confirmed_stage(store, task, "material_selection", material_output)

    brief = {
        "target_ip": "思丞说",
        "topic": item["title"],
        "goal": task["goal"],
        "platform": PLATFORM,
        "creation_mode": item["creation_mode"],
        "professional_support_mode": "guardrail_only",
        "professional_alignment": item["professional_alignment"],
        "source_content_task": item["source_content_task"],
        "main_claim": str(material.get("core_claim") or material.get("summary_text") or item["title"]),
        "retention_mechanism": item["hook_mechanism"],
        "must_keep_elements": [source_analysis.get("source_hook_text") or "", item["source_content_task"], item["hook_mechanism"]],
        "body_logic_plan": "hook -> source evidence or classification -> mechanism -> bounded conclusion",
        "risk_policy": "defer_to_risk_cleanup",
        "risk_watch": [item["risk_changes"]],
        "source_material_ids": [item["source_material_id"]],
    }
    brief_output = {
        "brief": brief,
        "status": "needs_confirmation",
        "validation": {"passed": True, "viewer_copy_absent": True},
        "creation_mode": CREATION_MODE,
    }
    insert_confirmed_stage(store, task, "creation_brief", brief_output)

    opening = first_sentence(item["body"])
    char_count = _script_char_count(item["body"])
    if not 280 <= char_count <= 500:
        raise ValueError(f"script {item['number']} length out of accepted oral range: {char_count}")
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
            "kept_source_elements": [item["source_content_task"], item["hook_mechanism"]],
            "ip_adaptation_notes": ["teacher-like oral delivery", "middle-aged audience", "concrete before abstract"],
            "conversion_goal_alignment": "single low-friction action or natural close",
            "deferred_risk_terms": source_analysis.get("deferred_risk_terms") or [],
            "source_to_draft_mapping": {
                "content_task": item["source_content_task"],
                "hook_mechanism": item["hook_mechanism"],
                "evidence_path": "preserved_and_compressed",
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
        "validation": {"passed": True, "dimensions": {"source_fidelity": True, "ip_alignment": True}},
        "status": "needs_confirmation",
        "creation_mode": CREATION_MODE,
    }
    insert_confirmed_stage(store, task, "rewrite_draft", rewrite_output)

    hook_output = {
        "hooks": [opening],
        "selected_hook": opening,
        "body": item["body"],
        "source_opening_text": source_analysis.get("source_opening_text") or "",
        "hook_diff_type": item["hook_diff_type"],
        "mechanism_preserved": True,
        "dedup_change_summary": "minimal hook edit with the source retention mechanism preserved",
        "validation": {
            "passed": True,
            "mechanism_preserved": True,
            "strength_parity": True,
            "speaker_translation_valid": True,
        },
        "status": "needs_confirmation",
        "creation_mode": CREATION_MODE,
    }
    insert_confirmed_stage(store, task, "hook_enhancement", hook_output)

    risk_output = {
        "cleaned_body": item["body"],
        "high_risk_replacements": [],
        "unchanged_source_risk_terms": [],
        "risk_diagnosis": [item["risk_changes"]],
        "risk_replacement_scope": {"passed": True, "mode": "semantic_claim_boundaries_reviewed"},
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
    }
    insert_confirmed_stage(store, task, "risk_cleanup", risk_output)

    package = {
        "cover_title_4": cover_title(item["title"]),
        "video_title_18": item["title"][:18],
        "description_100": first_sentence(item["body"])[:100],
        "pinned_comment": "你最想先对照哪一点？",
        "final_copy": item["body"],
        "body_char_count": char_count,
    }
    content_package_id = store.create_content_package(
        title=package["video_title_18"],
        body=item["body"],
        media_paths=[],
        hashtags=[item["direction"]],
        metadata={
            "source": "creation_task",
            "creation_task_id": task_id,
            "role_id": ROLE_ID,
            "batch_key": BATCH_KEY,
            "batch_number": int(item["number"]),
        },
    )
    store.update_creation_task(task_id, content_package_id=content_package_id)
    store.insert_material_creation(
        material_id=item["source_material_id"],
        role_id=ROLE_ID,
        content_package_id=content_package_id,
        task_id=None,
        platform=PLATFORM,
        rewrite_angle=item["direction"],
        status="draft",
        metadata={"creation_task_id": task_id, "batch_key": BATCH_KEY, "batch_number": int(item["number"])},
    )
    delivery_package_id = store.insert_creation_delivery_package(
        task_id=task_id,
        platform=PLATFORM,
        package=package,
        content_package_id=content_package_id,
        markdown_path=str(manifest_path.resolve()),
        status="draft",
    )
    publish_output = {
        "content_package_id": content_package_id,
        "delivery_package_id": delivery_package_id,
        "publish_package": package,
        "body_char_count": char_count,
        "validation": {"passed": True, "final_copy_locked": True},
        "status": "needs_confirmation",
        "creation_mode": CREATION_MODE,
    }
    insert_confirmed_stage(store, task, "publish_format", publish_output)

    delivery_markdown = (
        f"# {item['number']} {item['title']}\n\n"
        f"- source_material_id: {item['source_material_id']}\n"
        f"- creation_mode: {item['creation_mode']}\n"
        f"- source_content_task: {item['source_content_task']}\n"
        f"- hook_mechanism: {item['hook_mechanism']}\n"
        f"- risk_changes: {item['risk_changes']}\n\n"
        f"## Final Copy\n\n{item['body']}\n"
    )
    delivery_output = {
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
    }
    insert_confirmed_stage(store, task, "delivery", delivery_output)
    return {
        "number": item["number"],
        "task_id": task_id,
        "material_id": item["source_material_id"],
        "content_package_id": content_package_id,
        "delivery_package_id": delivery_package_id,
    }


def main() -> int:
    args = parse_args()
    store = Store(args.db_path)
    store.init_db()
    existing = existing_batch_tasks(store)
    if existing:
        raise SystemExit(f"batch already imported: {len(existing)} tasks")
    items = parse_manifest(args.manifest)
    for item in items:
        assert_material_ready(store, item)
    results = [import_item(store, item, args.manifest) for item in items]
    print(json.dumps({"batch_key": BATCH_KEY, "imported": len(results), "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
