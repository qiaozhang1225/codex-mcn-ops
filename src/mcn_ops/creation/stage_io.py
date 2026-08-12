from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..store import Store
from .contracts import response_template, stage_contract, validate_stage_submission
from .workflow import (
    CREATION_STAGES,
    CREATION_STAGE_CONTRACT_VERSION,
    DEFAULT_CREATION_MODEL,
    DEFAULT_CREATION_PROVIDER,
    _analyze_source_material,
    _assert_previous_stage_confirmed,
    _attach_stage_contract,
    _explicit_selected_material_ids,
    _material_packet,
    _material_search_text,
    _persist_stage_artifacts,
    _selection_reason,
    _task,
    _upstream_stage_run_ids,
    build_creation_context_packet,
)


FORMAL_STAGE_MODE = "codex_stage_submission_v1"
def prepare_creation_stage(
    store: Store,
    task_id: str,
    *,
    stage_key: str,
    knowledge_root: Path,
    candidate_limit: int = 20,
) -> dict[str, Any]:
    if stage_key not in CREATION_STAGES:
        raise ValueError(f"unknown creation stage: {stage_key}")
    task = _task(store, task_id)
    _assert_previous_stage_confirmed(store, task_id, stage_key)
    include_transcript = stage_key in {"material_selection", "creation_brief", "rewrite_draft"}
    packet = build_creation_context_packet(
        store,
        task_id,
        knowledge_root=knowledge_root,
        stage_key=stage_key,
        include_transcript=include_transcript,
    )
    if stage_key == "material_selection":
        packet["candidate_materials"] = _candidate_materials(store, task, limit=candidate_limit)
    packet["upstream_outputs"] = _upstream_outputs(store, task_id, stage_key)
    packet["output_contract"] = stage_contract(stage_key)
    packet["response_template"] = response_template(stage_key)
    packet["submission_rules"] = [
        "Return one JSON object matching response_template; do not wrap it in Markdown.",
        "Use only claims supported by the source packet or cited professional knowledge cards.",
        "Preserve the source content task and propagation mechanism before applying IP or domain constraints.",
        "Do not advance a topic clue or hard professional conflict as a formal rewrite base.",
    ]
    packet["prepared_for"] = {
        "provider": str(task.get("provider") or DEFAULT_CREATION_PROVIDER),
        "model": str(task.get("model") or DEFAULT_CREATION_MODEL),
        "mode": FORMAL_STAGE_MODE,
    }
    return packet


def submit_creation_stage(
    store: Store,
    task_id: str,
    *,
    stage_key: str,
    result: dict[str, Any],
    knowledge_root: Path,
    note: str = "",
    candidate_limit: int = 20,
) -> dict[str, Any]:
    task = _task(store, task_id)
    _assert_previous_stage_confirmed(store, task_id, stage_key)
    packet = prepare_creation_stage(store, task_id, stage_key=stage_key, knowledge_root=knowledge_root, candidate_limit=candidate_limit)
    validation = validate_stage_submission(stage_key, result, packet)
    if validation.structural_errors:
        raise ValueError("invalid stage submission: " + "; ".join(validation.structural_errors))

    output = _normalize_stage_output(stage_key, result, packet)
    output["validation"] = {
        "passed": validation.passed,
        "structural_errors": validation.structural_errors,
        "gate_failures": validation.gate_failures,
    }
    output["status"] = "needs_confirmation" if validation.passed else "needs_retry"
    output["creation_mode"] = FORMAL_STAGE_MODE
    if stage_key == "material_selection":
        _persist_material_decisions(store, task, result, packet)
    if stage_key == "publish_format" and validation.passed:
        _persist_publish_package(store, task, output)

    upstream_ids = _upstream_stage_run_ids(store, task_id, stage_key)
    output = _attach_stage_contract(store, task, stage_key, output, upstream_ids)
    stage_run_id = store.insert_creation_stage_run(
        task_id=task_id,
        stage_key=stage_key,
        status=str(output["status"]),
        provider=str(task.get("provider") or DEFAULT_CREATION_PROVIDER),
        model=str(task.get("model") or DEFAULT_CREATION_MODEL),
        input_data={
            "task_id": task_id,
            "stage_key": stage_key,
            "submission_mode": FORMAL_STAGE_MODE,
            "stage_contract_version": CREATION_STAGE_CONTRACT_VERSION,
            "upstream_stage_run_ids": upstream_ids,
        },
        output_data=output,
        output_markdown=_stage_markdown(stage_key, output),
        note=note,
    )
    _persist_stage_artifacts(store, task, stage_key, stage_run_id, output)
    store.update_creation_task(task_id, status="material_selected" if stage_key == "material_selection" else stage_key)
    return {
        "task": store.get_creation_task(task_id),
        "stage_run": store.latest_creation_stage_run(task_id, stage_key),
        "output": output,
    }


def _candidate_materials(store: Store, task: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    role_id = str(task["role_id"])
    role = store.get_ip_role(role_id) or {}
    explicit_ids = _explicit_selected_material_ids(task)
    materials = store.list_collected_materials(status="collected")
    if explicit_ids:
        by_id = {
            item["id"]: item
            for item in materials
            if item.get("eligibility_status") == "accepted" and str(item.get("transcript_text") or "").strip()
        }
        ranked = [(1.0, by_id[item_id], "explicit_selected_material") for item_id in explicit_ids if item_id in by_id]
    else:
        topic = str(task.get("topic") or "")
        allow_reuse = bool(task.get("allow_reuse_material"))
        used_ids = {item["material_id"] for item in store.list_material_creations(role_id=role_id)}
        matches = {item["material_id"]: item for item in store.list_material_role_matches(role_id=role_id)}
        role_terms = list(role.get("search_keywords") or []) + list(role.get("fit_themes") or [])
        ranked = []
        for material in materials:
            if material.get("eligibility_status") != "accepted":
                continue
            if not str(material.get("transcript_text") or "").strip():
                continue
            if material["id"] in used_ids and not allow_reuse:
                continue
            text = _material_search_text(material)
            topic_hit = 1 if topic and topic in text else 0
            role_hit_count = len([term for term in role_terms if term and str(term) in text])
            match = matches.get(material["id"])
            match_score = float(match.get("fit_score") or 0) if match and match.get("decision") == "accepted" else 0.0
            score = match_score + topic_hit * 0.35 + min(role_hit_count, 4) * 0.12 + float(material.get("knowledge_core_score") or 0) * 0.2
            if score <= 0 and topic not in text:
                continue
            reason = _selection_reason(material, topic_hit=topic_hit, role_hit_count=role_hit_count, match_score=match_score)
            ranked.append((score, material, reason))
        ranked.sort(key=lambda item: item[0], reverse=True)

    candidates: list[dict[str, Any]] = []
    for score, material, reason in ranked[: max(1, limit)]:
        analysis = _analyze_source_material(material, task)
        candidates.append(
            {
                **_material_packet(material, include_transcript=True, source_analysis=analysis),
                "suggested_score": round(float(score), 3),
                "suggested_reason": reason,
            }
        )
    return candidates


def _upstream_outputs(store: Store, task_id: str, stage_key: str) -> dict[str, Any]:
    current_index = CREATION_STAGES.index(stage_key)
    outputs: dict[str, Any] = {}
    for key in CREATION_STAGES[:current_index]:
        stage = store.latest_creation_stage_run(task_id, key)
        if stage:
            outputs[key] = dict(stage.get("output") or {})
    return outputs


def _normalize_stage_output(stage_key: str, result: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    if stage_key == "material_selection":
        candidate_map = {str(item["id"]): item for item in packet.get("candidate_materials") or []}
        selected: list[dict[str, Any]] = []
        analysis: dict[str, Any] = {}
        for item in result["materials"]:
            material_id = str(item["material_id"])
            is_selected = (
                item.get("material_class") == "formal_rewrite_base"
                and item.get("professional_alignment") != "hard_conflict"
                and item.get("professional_disposition") not in {"reclassify", "reject"}
            )
            if is_selected:
                selected.append({"material_id": material_id, "score": candidate_map[material_id].get("suggested_score", 0), "reason": item["selection_rationale"]})
                analysis[material_id] = {
                    **dict(candidate_map[material_id].get("source_analysis") or {}),
                    **item,
                }
        return {"materials": result["materials"], "selected": selected, "source_analysis": analysis}
    if stage_key == "creation_brief":
        return {"brief": result}
    if stage_key == "rewrite_draft":
        body = str(result["draft_text"])
        return {
            **result,
            "draft": {
                "title": str((packet.get("selected_materials") or [{}])[0].get("clean_title") or packet["task"].get("topic") or "")[:40],
                "body": body,
                "draft_text": body,
                "source_mapping": result.get("source_mapping") or [],
                "new_claims": result.get("new_claims") or [],
            },
        }
    return dict(result)


def _persist_material_decisions(store: Store, task: dict[str, Any], result: dict[str, Any], packet: dict[str, Any]) -> None:
    candidate_map = {str(item["id"]): item for item in packet.get("candidate_materials") or []}
    for item in result["materials"]:
        material_id = str(item["material_id"])
        selected = (
            item.get("material_class") == "formal_rewrite_base"
            and item.get("professional_alignment") != "hard_conflict"
            and item.get("professional_disposition") not in {"reclassify", "reject"}
        )
        candidate = candidate_map[material_id]
        store.upsert_creation_material_selection(
            task_id=task["id"],
            material_id=material_id,
            role_id=str(task["role_id"]),
            selection_status="selected" if selected else "rejected",
            score=float(candidate.get("suggested_score") or 0),
            reason=str(item.get("selection_rationale") or ""),
            metadata={
                "material_class": item.get("material_class"),
                "professional_alignment": item.get("professional_alignment"),
                "conflicting_claim": item.get("conflicting_claim") or "",
                "professional_disposition": item.get("professional_disposition"),
                "salvage_boundary": item.get("salvage_boundary") or "",
                "selection_weaknesses": item.get("selection_weaknesses") or [],
            },
        )


def _persist_publish_package(store: Store, task: dict[str, Any], output: dict[str, Any]) -> None:
    package = dict(output["publish_package"])
    body = str(package["final_copy"])
    content_id = store.create_content_package(
        title=str(package["video_title_18"]),
        body=body,
        media_paths=[],
        hashtags=[str(task.get("topic") or "")],
        metadata={"source": FORMAL_STAGE_MODE, "creation_task_id": task["id"], "role_id": task["role_id"]},
    )
    store.update_creation_task(task["id"], content_package_id=content_id)
    for selection in store.list_creation_material_selections(task["id"], selection_status="selected"):
        store.insert_material_creation(
            material_id=selection["material_id"],
            role_id=str(task["role_id"]),
            content_package_id=content_id,
            task_id=None,
            platform=str(task["platform"]),
            rewrite_angle=str(task.get("topic") or ""),
            status="draft",
            metadata={"source": FORMAL_STAGE_MODE, "creation_task_id": task["id"]},
        )
    delivery_id = store.insert_creation_delivery_package(
        task_id=task["id"],
        platform=str(task["platform"]),
        package=package,
        content_package_id=content_id,
        status="draft",
    )
    output["content_package_id"] = content_id
    output["delivery_package_id"] = delivery_id


def _stage_markdown(stage_key: str, output: dict[str, Any]) -> str:
    if stage_key == "rewrite_draft":
        return "# Rewrite Draft\n\n" + str(output.get("draft_text") or "")
    if stage_key == "risk_cleanup":
        return "# Risk Cleanup\n\n" + str(output.get("cleaned_body") or "")
    if stage_key == "delivery":
        return str(output.get("delivery_markdown") or "")
    return f"# {stage_key.replace('_', ' ').title()}\n\n```json\n{json.dumps(output, ensure_ascii=False, indent=2)}\n```\n"
