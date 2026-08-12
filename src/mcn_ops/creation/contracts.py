from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ADAPTATION_MODES = {"adaptation", "half_original", "original"}
MATERIAL_CLASSES = {"formal_rewrite_base", "topic_clue"}
PROFESSIONAL_ALIGNMENTS = {"aligned", "acceptable_variance", "repairable_conflict", "hard_conflict"}
PROFESSIONAL_DISPOSITIONS = {"keep", "qualify", "replace_claim", "reclassify", "reject"}
PROFESSIONAL_SUPPORT_MODES = {"none", "guardrail_only", "one_support_point"}


@dataclass(frozen=True)
class StageValidation:
    structural_errors: list[str]
    gate_failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.structural_errors and not self.gate_failures


def stage_contract(stage_key: str) -> dict[str, Any]:
    contracts: dict[str, dict[str, Any]] = {
        "material_selection": {
            "required": ["materials"],
            "item_required": [
                "material_id",
                "material_class",
                "source_content_task",
                "source_hook_mechanism",
                "speaker_position",
                "thickness_judgment",
                "professional_alignment",
                "professional_disposition",
                "salvage_boundary",
                "selection_rationale",
            ],
            "enums": {
                "material_class": sorted(MATERIAL_CLASSES),
                "professional_alignment": sorted(PROFESSIONAL_ALIGNMENTS),
                "professional_disposition": sorted(PROFESSIONAL_DISPOSITIONS),
            },
            "gate": "Only a formal_rewrite_base without hard_conflict may be selected. repairable_conflict requires an exact conflicting_claim and salvage_boundary.",
        },
        "creation_brief": {
            "required": [
                "adaptation_mode",
                "main_claim",
                "retention_mechanism",
                "must_keep_elements",
                "body_logic_plan",
                "professional_support_mode",
                "support_card_ids",
                "support_function",
                "target_gap",
                "risk_policy",
            ],
            "enums": {
                "adaptation_mode": sorted(ADAPTATION_MODES),
                "professional_support_mode": sorted(PROFESSIONAL_SUPPORT_MODES),
            },
            "gate": "Standard adaptation may use at most one support card. More professional support requires half_original or original mode.",
        },
        "rewrite_draft": {
            "required": [
                "draft_text",
                "source_content_task_preserved",
                "source_hook_mechanism_preserved",
                "source_evidence_path_preserved",
                "speaker_translation_valid",
                "new_claims",
                "source_mapping",
            ],
            "gate": "An adaptation must preserve its source content task, hook mechanism, evidence path, and speaker credibility. Every new professional claim must cite a knowledge_card_id.",
        },
        "hook_enhancement": {
            "required": ["selected_hook", "body", "hook_diff_type", "mechanism_preserved"],
            "enums": {"hook_diff_type": ["unchanged", "punctuation_asr", "minimal_dedup", "perspective_translation", "replaced"]},
            "gate": "The hook mechanism must remain intact; a replacement requires a documented incompatibility_reason.",
        },
        "risk_cleanup": {
            "required": ["cleaned_body", "claim_risks", "risk_replacement_scope", "overall_risk"],
            "gate": "Risk cleanup may change only unsafe spans and must not replace the source content task.",
        },
        "publish_format": {
            "required": ["publish_package"],
            "package_required": ["cover_title_4", "video_title_18", "video_description", "pinned_comment", "final_copy"],
            "gate": "publish_package.final_copy must exactly equal the confirmed risk_cleanup.cleaned_body.",
        },
        "delivery": {
            "required": ["delivery_markdown"],
            "gate": "Delivery may format confirmed artifacts but must not rewrite the final copy.",
        },
    }
    if stage_key not in contracts:
        raise ValueError(f"unknown creation stage: {stage_key}")
    return {"stage": stage_key, **contracts[stage_key]}


def response_template(stage_key: str) -> dict[str, Any]:
    templates: dict[str, dict[str, Any]] = {
        "material_selection": {
            "materials": [
                {
                    "material_id": "material_id_from_packet",
                    "material_class": "formal_rewrite_base",
                    "source_content_task": "",
                    "source_hook_mechanism": "",
                    "speaker_position": "",
                    "thickness_judgment": "",
                    "professional_alignment": "aligned",
                    "conflicting_claim": "",
                    "professional_disposition": "keep",
                    "salvage_boundary": "",
                    "selection_rationale": "",
                    "selection_weaknesses": [],
                }
            ]
        },
        "creation_brief": {
            "adaptation_mode": "adaptation",
            "main_claim": "",
            "retention_mechanism": "",
            "must_keep_elements": [],
            "body_logic_plan": [],
            "professional_support_mode": "none",
            "support_card_ids": [],
            "support_function": "",
            "target_gap": "",
            "risk_policy": "defer_to_risk_cleanup",
        },
        "rewrite_draft": {
            "draft_text": "",
            "source_content_task_preserved": True,
            "source_hook_mechanism_preserved": True,
            "source_evidence_path_preserved": True,
            "speaker_translation_valid": True,
            "new_claims": [],
            "source_mapping": [],
        },
        "hook_enhancement": {"selected_hook": "", "body": "", "hook_diff_type": "unchanged", "mechanism_preserved": True},
        "risk_cleanup": {"cleaned_body": "", "claim_risks": [], "risk_replacement_scope": {"changed_spans": []}, "overall_risk": "safe"},
        "publish_format": {"publish_package": {"cover_title_4": "", "video_title_18": "", "video_description": "", "pinned_comment": "", "final_copy": ""}},
        "delivery": {"delivery_markdown": ""},
    }
    if stage_key not in templates:
        raise ValueError(f"unknown creation stage: {stage_key}")
    return templates[stage_key]


def validate_stage_submission(stage_key: str, result: Any, packet: dict[str, Any]) -> StageValidation:
    structural: list[str] = []
    gates: list[str] = []
    contract = stage_contract(stage_key)
    if not isinstance(result, dict):
        return StageValidation(["result must be a JSON object"], [])
    _require_fields(result, contract.get("required") or [], structural)
    if structural:
        return StageValidation(structural, gates)

    if stage_key == "material_selection":
        _validate_material_selection(result, packet, structural, gates)
    elif stage_key == "creation_brief":
        _validate_creation_brief(result, packet, structural, gates)
    elif stage_key == "rewrite_draft":
        _validate_rewrite_draft(result, packet, structural, gates)
    elif stage_key == "hook_enhancement":
        _validate_hook(result, structural, gates)
    elif stage_key == "risk_cleanup":
        _validate_risk(result, structural, gates)
    elif stage_key == "publish_format":
        _validate_publish(result, packet, structural, gates)
    elif stage_key == "delivery":
        if not str(result.get("delivery_markdown") or "").strip():
            structural.append("delivery_markdown must not be empty")
    return StageValidation(structural, gates)


def _require_fields(value: dict[str, Any], fields: list[str], errors: list[str], *, prefix: str = "") -> None:
    for field in fields:
        if field not in value:
            errors.append(f"{prefix}{field} is required")


def _validate_material_selection(result: dict[str, Any], packet: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    items = result.get("materials")
    if not isinstance(items, list) or not items:
        structural.append("materials must be a non-empty list")
        return
    candidate_ids = {str(item.get("id")) for item in packet.get("candidate_materials") or []}
    seen_material_ids: set[str] = set()
    selected_count = 0
    for index, item in enumerate(items):
        prefix = f"materials[{index}]."
        if not isinstance(item, dict):
            structural.append(f"materials[{index}] must be an object")
            continue
        _require_fields(item, stage_contract("material_selection")["item_required"], structural, prefix=prefix)
        material_id = str(item.get("material_id") or "")
        if material_id not in candidate_ids:
            structural.append(f"{prefix}material_id is not in the prepared candidate pool")
        if material_id in seen_material_ids:
            structural.append(f"{prefix}material_id is duplicated")
        seen_material_ids.add(material_id)
        material_class = item.get("material_class")
        alignment = item.get("professional_alignment")
        disposition = item.get("professional_disposition")
        if material_class not in MATERIAL_CLASSES:
            structural.append(f"{prefix}material_class is invalid")
        if alignment not in PROFESSIONAL_ALIGNMENTS:
            structural.append(f"{prefix}professional_alignment is invalid")
        if disposition not in PROFESSIONAL_DISPOSITIONS:
            structural.append(f"{prefix}professional_disposition is invalid")
        if material_class == "formal_rewrite_base" and alignment != "hard_conflict" and disposition not in {"reclassify", "reject"}:
            selected_count += 1
        if alignment == "repairable_conflict":
            if not str(item.get("conflicting_claim") or "").strip():
                gates.append(f"{prefix}repairable_conflict requires conflicting_claim")
            if not str(item.get("salvage_boundary") or "").strip():
                gates.append(f"{prefix}repairable_conflict requires salvage_boundary")
        if alignment == "hard_conflict" and material_class == "formal_rewrite_base":
            gates.append(f"{prefix}hard_conflict cannot remain a formal_rewrite_base")
    if selected_count == 0:
        gates.append("no formal rewrite base passed the professional and thickness gates")
    target_count = int((packet.get("task") or {}).get("target_count") or 1)
    if selected_count > target_count:
        gates.append(f"selected {selected_count} materials but task target_count is {target_count}")


def _validate_creation_brief(result: dict[str, Any], packet: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    mode = result.get("adaptation_mode")
    support_mode = result.get("professional_support_mode")
    cards = result.get("support_card_ids")
    if mode not in ADAPTATION_MODES:
        structural.append("adaptation_mode is invalid")
    if support_mode not in PROFESSIONAL_SUPPORT_MODES:
        structural.append("professional_support_mode is invalid")
    if not isinstance(cards, list):
        structural.append("support_card_ids must be a list")
        return
    if support_mode == "one_support_point" and len(cards) != 1:
        gates.append("one_support_point requires exactly one support_card_id")
    if support_mode in {"none", "guardrail_only"} and cards:
        gates.append(f"{support_mode} must not inject support cards into the draft")
    if mode == "adaptation" and len(cards) > 1:
        gates.append("adaptation may not use more than one professional support card")
    valid_card_ids = {str(item.get("id") or "") for item in packet.get("professional_knowledge_cards") or []}
    for card_id in cards:
        if str(card_id) not in valid_card_ids:
            gates.append(f"unknown professional support card: {card_id}")


def _validate_rewrite_draft(result: dict[str, Any], packet: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    if not str(result.get("draft_text") or "").strip():
        structural.append("draft_text must not be empty")
    brief = packet.get("brief") or {}
    if brief.get("adaptation_mode") == "adaptation":
        for field in ["source_content_task_preserved", "source_hook_mechanism_preserved", "source_evidence_path_preserved", "speaker_translation_valid"]:
            if result.get(field) is not True:
                gates.append(f"adaptation requires {field}=true")
    claims = result.get("new_claims")
    mapping = result.get("source_mapping")
    if not isinstance(claims, list):
        structural.append("new_claims must be a list")
    else:
        valid_card_ids = {str(item.get("id") or "") for item in packet.get("professional_knowledge_cards") or []}
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict) or not str(claim.get("claim") or "").strip():
                structural.append(f"new_claims[{index}] requires claim")
            if brief.get("adaptation_mode") == "adaptation" and not str((claim or {}).get("knowledge_card_id") or "").strip():
                gates.append(f"new_claims[{index}] requires knowledge_card_id in adaptation mode")
            card_id = str((claim or {}).get("knowledge_card_id") or "")
            if card_id and card_id not in valid_card_ids:
                gates.append(f"new_claims[{index}] cites unknown knowledge_card_id: {card_id}")
    if not isinstance(mapping, list):
        structural.append("source_mapping must be a list")


def _validate_hook(result: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    if result.get("hook_diff_type") not in {"unchanged", "punctuation_asr", "minimal_dedup", "perspective_translation", "replaced"}:
        structural.append("hook_diff_type is invalid")
    if not str(result.get("body") or "").strip():
        structural.append("body must not be empty")
    if result.get("mechanism_preserved") is not True:
        gates.append("hook mechanism was not preserved")
    if result.get("hook_diff_type") == "replaced" and not str(result.get("incompatibility_reason") or "").strip():
        gates.append("replaced hook requires incompatibility_reason")


def _validate_risk(result: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    if not str(result.get("cleaned_body") or "").strip():
        structural.append("cleaned_body must not be empty")
    if not isinstance(result.get("claim_risks"), list):
        structural.append("claim_risks must be a list")
    if result.get("source_content_task_preserved") is False:
        gates.append("risk cleanup changed the source content task")


def _validate_publish(result: dict[str, Any], packet: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    package = result.get("publish_package")
    if not isinstance(package, dict):
        structural.append("publish_package must be an object")
        return
    _require_fields(package, stage_contract("publish_format")["package_required"], structural, prefix="publish_package.")
    risk = packet.get("upstream_outputs", {}).get("risk_cleanup") or {}
    expected = str(risk.get("cleaned_body") or "")
    if expected and package.get("final_copy") != expected:
        gates.append("publish_package.final_copy must equal risk_cleanup.cleaned_body")
