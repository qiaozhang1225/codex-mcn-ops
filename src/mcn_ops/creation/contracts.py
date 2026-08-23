from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


ADAPTATION_MODES = {"adaptation", "half_original", "original"}
MATERIAL_CLASSES = {"formal_rewrite_base", "topic_clue"}
PROFESSIONAL_ALIGNMENTS = {"aligned", "acceptable_variance", "repairable_conflict", "hard_conflict"}
PROFESSIONAL_DISPOSITIONS = {"keep", "qualify", "replace_claim", "reclassify", "reject"}
PROFESSIONAL_SUPPORT_MODES = {"none", "guardrail_only", "one_support_point"}
WRITING_MODES = {"initial_draft", "opening_only", "opening_and_bridge", "localized_body_revision", "risk_localized_revision", "full_rewrite"}
REVIEW_VERDICTS = {"pass", "revise", "return_upstream"}
RISK_REVIEW_VERDICTS = {"pass", "revise", "return_upstream", "reject"}
AFFLICTION_DRIVERS = ("贪", "瞋", "痴", "慢", "疑")
AFFLICTION_STATUSES = {"strong", "weak", "absent", "artificial"}
REVIEW_COPY_KEYS = {"body", "draft", "draft_text", "cleaned_body", "final_copy", "publish_package", "replacement_copy", "suggested_copy"}


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
        "script_writing": {
            "required": [
                "writing_mode", "creation_mode", "base_script_run_id", "base_body_hash", "revision_request_stage_run_id",
                "body", "opening", "body_contract", "source_content_task_preserved", "source_hook_mechanism_preserved",
                "source_evidence_path_preserved", "speaker_translation_valid", "new_claims", "source_mapping",
                "protected_elements", "changed_spans",
            ],
            "enums": {"writing_mode": sorted(WRITING_MODES), "creation_mode": sorted(ADAPTATION_MODES)},
            "gate": "Script Writer is the only copy owner. Revisions must bind to a review request and reconstruct the new body only from declared changed_spans.",
        },
        "quality_review": {
            "required": [
                "reviewed_script_run_id", "reviewed_body_hash", "verdict", "quality_dimensions", "five_affliction_review",
                "opening_scope_review", "source_mechanism_review", "body_contract_review", "protected_elements", "failed_dimensions", "revision_request",
            ],
            "enums": {"verdict": sorted(REVIEW_VERDICTS)},
            "gate": "Quality Review is read-only. Opening evidence is limited to spoken sentences one and two; both must be strong, each must carry strong evidence, and together they need at least three strong organic drivers, four literal high-stimulus keywords, no artificial driver, and complete body payoff.",
        },
        "risk_review": {
            "required": ["reviewed_script_run_id", "reviewed_body_hash", "verdict", "issues", "overall_risk", "revision_request"],
            "enums": {"verdict": sorted(RISK_REVIEW_VERDICTS)},
            "gate": "Risk Review is read-only and must review the same script version passed by Quality Review. Repairable issues return bounded directions to Script Writer.",
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
            "risk_policy": "defer_to_risk_review",
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
        "script_writing": {
            "writing_mode": "initial_draft", "creation_mode": "adaptation", "base_script_run_id": "", "base_body_hash": "",
            "revision_request_stage_run_id": "", "body": "", "opening": "", "body_contract": "",
            "source_content_task_preserved": True, "source_hook_mechanism_preserved": True,
            "source_evidence_path_preserved": True, "speaker_translation_valid": True, "new_claims": [], "source_mapping": [],
            "protected_elements": [], "changed_spans": [],
        },
        "quality_review": {
            "reviewed_script_run_id": "", "reviewed_body_hash": "", "verdict": "pass", "quality_dimensions": {},
            "opening_scope_review": {
                "opening_sentence_1": "", "opening_sentence_2": "", "bridge_starts_at_sentence": 3,
                "sentence_1_hook_task": "", "sentence_2_hook_task": "", "sentence_1_strength": "strong",
                "sentence_2_strength": "strong", "high_stimulus_keywords": [],
            },
            "five_affliction_review": {
                **{driver: {"status": "absent", "evidence_span": "", "reason": "", "body_payoff": False, "body_payoff_span": "", "revision_direction": ""} for driver in AFFLICTION_DRIVERS},
                "coherent_body_contract": True, "rationale_for_not_forcing_missing": "",
            },
            "source_mechanism_review": {}, "body_contract_review": {}, "protected_elements": [], "failed_dimensions": [], "revision_request": None,
        },
        "risk_review": {"reviewed_script_run_id": "", "reviewed_body_hash": "", "verdict": "pass", "issues": [], "overall_risk": "safe", "revision_request": None},
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
    elif stage_key == "script_writing":
        _validate_script_writing(result, packet, structural, gates)
    elif stage_key == "quality_review":
        _validate_quality_review(result, packet, structural, gates)
    elif stage_key == "risk_review":
        _validate_risk_review(result, packet, structural, gates)
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
    requested_mode = str((packet.get("task_context") or {}).get("creation_mode") or "adaptation")
    if mode != requested_mode:
        gates.append(f"adaptation_mode must match task creation_mode: {requested_mode}")
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


def _validate_script_writing(result: dict[str, Any], packet: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    writing_mode = result.get("writing_mode")
    creation_mode = result.get("creation_mode")
    body = str(result.get("body") or "")
    opening = str(result.get("opening") or "")
    if writing_mode not in WRITING_MODES:
        structural.append("writing_mode is invalid")
    if creation_mode not in ADAPTATION_MODES:
        structural.append("creation_mode is invalid")
    requested_mode = str((packet.get("task_context") or {}).get("creation_mode") or "adaptation")
    if creation_mode != requested_mode:
        gates.append(f"creation_mode must match task creation_mode: {requested_mode}")
    if not body.strip():
        structural.append("body must not be empty")
    if not opening.strip() or not body.lstrip().startswith(opening.strip()):
        gates.append("opening must be the exact leading span of body")
    for field in ["new_claims", "source_mapping", "protected_elements", "changed_spans"]:
        if not isinstance(result.get(field), list):
            structural.append(f"{field} must be a list")
    if creation_mode == "adaptation":
        for field in ["source_content_task_preserved", "source_hook_mechanism_preserved", "source_evidence_path_preserved", "speaker_translation_valid"]:
            if result.get(field) is not True:
                gates.append(f"adaptation requires {field}=true")
    _validate_professional_claims(result.get("new_claims"), packet, creation_mode, structural, gates)

    revision = packet.get("script_revision_context") or {}
    if writing_mode == "initial_draft":
        if packet.get("current_script"):
            gates.append("initial_draft is allowed only when no confirmed script version exists")
        if revision:
            gates.append("a pending review revision request must be handled instead of creating another initial_draft")
        if any(str(result.get(field) or "").strip() for field in ["base_script_run_id", "base_body_hash", "revision_request_stage_run_id"]):
            gates.append("initial_draft must not bind to a base script or revision request")
        if result.get("changed_spans"):
            gates.append("initial_draft must use an empty changed_spans list")
        return

    if not revision:
        gates.append("revision writing_mode requires a pending confirmed review request")
        return
    for field in ["base_script_run_id", "base_body_hash", "revision_request_stage_run_id"]:
        if result.get(field) != revision.get(field):
            gates.append(f"{field} does not match the pending review request")
    request = revision.get("revision_request") or {}
    if writing_mode != request.get("revision_scope"):
        gates.append("writing_mode must equal revision_request.revision_scope")
    base_body = str(revision.get("base_body") or "")
    changes = result.get("changed_spans")
    if not isinstance(changes, list) or not changes:
        gates.append("a revision requires at least one declared changed span")
        return
    reconstructed = base_body
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            structural.append(f"changed_spans[{index}] must be an object")
            continue
        before = str(change.get("before") or "")
        after = str(change.get("after") or "")
        if not before or before not in reconstructed:
            gates.append(f"changed_spans[{index}].before must occur in the current base body")
            continue
        reconstructed = reconstructed.replace(before, after, 1)
    if reconstructed != body:
        gates.append("declared changed_spans do not reconstruct the submitted body exactly")
    boundary = 240 if writing_mode == "opening_only" else (500 if writing_mode == "opening_and_bridge" else None)
    if boundary is not None:
        for index, change in enumerate(changes):
            if base_body.find(str((change or {}).get("before") or "")) >= boundary:
                gates.append(f"changed_spans[{index}] exceeds the {writing_mode} boundary")
    for span in request.get("protected_spans") or []:
        if str(span) and str(span) not in body:
            gates.append(f"protected span was removed: {span}")


def _validate_professional_claims(claims: Any, packet: dict[str, Any], creation_mode: str, structural: list[str], gates: list[str]) -> None:
    if not isinstance(claims, list):
        return
    valid_card_ids = {str(item.get("id") or "") for item in packet.get("professional_knowledge_cards") or []}
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not str((claim or {}).get("claim") or "").strip():
            structural.append(f"new_claims[{index}] requires claim")
            continue
        card_id = str(claim.get("knowledge_card_id") or "")
        if creation_mode == "adaptation" and not card_id:
            gates.append(f"new_claims[{index}] requires knowledge_card_id in adaptation mode")
        if card_id and card_id not in valid_card_ids:
            gates.append(f"new_claims[{index}] cites unknown knowledge_card_id: {card_id}")


def _validate_quality_review(result: dict[str, Any], packet: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    _validate_read_only_review(result, structural)
    script = packet.get("current_script") or {}
    _validate_review_binding(result, script, structural, gates)
    verdict = result.get("verdict")
    if verdict not in REVIEW_VERDICTS:
        structural.append("verdict is invalid")
    for field in ["quality_dimensions", "opening_scope_review", "five_affliction_review", "source_mechanism_review", "body_contract_review"]:
        if not isinstance(result.get(field), dict):
            structural.append(f"{field} must be an object")
    for field in ["protected_elements", "failed_dimensions"]:
        if not isinstance(result.get(field), list):
            structural.append(f"{field} must be a list")
    review = result.get("five_affliction_review") or {}
    opening = str(script.get("opening") or "")
    body = str(script.get("body") or "")
    sentences = [part.strip() for part in re.findall(r".+?(?:[。！？?!]+|$)", opening) if part.strip()]
    sentence_1 = sentences[0] if sentences else ""
    sentence_2 = sentences[1] if len(sentences) > 1 else ""
    opening_evidence_scope = sentence_1 + sentence_2
    scope_review = result.get("opening_scope_review") or {}
    if scope_review.get("opening_sentence_1") != sentence_1:
        gates.append("opening_scope_review.opening_sentence_1 must equal spoken sentence one")
    if scope_review.get("opening_sentence_2") != sentence_2:
        gates.append("opening_scope_review.opening_sentence_2 must equal spoken sentence two")
    if scope_review.get("bridge_starts_at_sentence") != 3:
        gates.append("opening_scope_review.bridge_starts_at_sentence must equal 3")
    for field in ["sentence_1_hook_task", "sentence_2_hook_task"]:
        if not str(scope_review.get(field) or "").strip():
            structural.append(f"opening_scope_review.{field} must not be empty")
    for field in ["sentence_1_strength", "sentence_2_strength"]:
        if scope_review.get(field) not in {"strong", "weak", "absent"}:
            structural.append(f"opening_scope_review.{field} is invalid")
    keywords = scope_review.get("high_stimulus_keywords")
    if not isinstance(keywords, list):
        structural.append("opening_scope_review.high_stimulus_keywords must be a list")
        keywords = []
    normalized_keywords = {str(keyword).strip() for keyword in keywords if len(str(keyword).strip()) >= 2}
    for keyword in normalized_keywords:
        if keyword not in opening_evidence_scope:
            gates.append(f"opening high-stimulus keyword must quote sentence one or two: {keyword}")
    strong_count = 0
    sentence_1_strong_count = 0
    sentence_2_strong_count = 0
    artificial = []
    for driver in AFFLICTION_DRIVERS:
        item = review.get(driver)
        if not isinstance(item, dict):
            structural.append(f"five_affliction_review.{driver} is required")
            continue
        status = item.get("status")
        if status not in AFFLICTION_STATUSES:
            structural.append(f"five_affliction_review.{driver}.status is invalid")
            continue
        evidence = str(item.get("evidence_span") or "")
        if status in {"strong", "weak", "artificial"} and (not evidence or evidence not in opening_evidence_scope):
            gates.append(f"five_affliction_review.{driver}.evidence_span must quote opening sentence one or two")
        if status == "strong":
            strong_count += 1
            if evidence and evidence in sentence_1:
                sentence_1_strong_count += 1
            if evidence and evidence in sentence_2:
                sentence_2_strong_count += 1
            payoff = str(item.get("body_payoff_span") or "")
            if item.get("body_payoff") is not True or not payoff or payoff not in body:
                gates.append(f"five_affliction_review.{driver} strong status requires an exact body payoff")
        if status == "artificial":
            artificial.append(driver)
    review["derived_active_driver_count"] = strong_count
    if verdict == "pass":
        if len(sentences) < 2:
            gates.append("quality pass requires two spoken opening sentences")
        if scope_review.get("sentence_1_strength") != "strong" or scope_review.get("sentence_2_strength") != "strong":
            gates.append("quality pass requires both opening sentences to be strong")
        if sentence_1_strong_count < 1 or sentence_2_strong_count < 1:
            gates.append("quality pass requires at least one strong five-affliction evidence span in each opening sentence")
        if len(normalized_keywords) < 4:
            gates.append("quality pass requires at least four distinct high-stimulus keywords in the first two sentences")
        if strong_count < 3:
            gates.append("quality pass normally requires at least three strong five-affliction drivers")
        if artificial:
            gates.append("quality pass cannot contain artificial five-affliction drivers")
        if review.get("coherent_body_contract") is not True:
            gates.append("quality pass requires coherent_body_contract=true")
        if strong_count < 5 and not str(review.get("rationale_for_not_forcing_missing") or "").strip():
            gates.append("quality pass with fewer than five strong drivers requires rationale_for_not_forcing_missing")
        if result.get("failed_dimensions"):
            gates.append("quality pass must not contain failed_dimensions")
        if result.get("revision_request") not in (None, {}):
            gates.append("quality pass must not contain a revision_request")
    else:
        _validate_revision_request(result.get("revision_request"), structural, gates)


def _validate_risk_review(result: dict[str, Any], packet: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    _validate_read_only_review(result, structural)
    script = packet.get("current_script") or {}
    _validate_review_binding(result, script, structural, gates)
    verdict = result.get("verdict")
    if verdict not in RISK_REVIEW_VERDICTS:
        structural.append("verdict is invalid")
    issues = result.get("issues")
    if not isinstance(issues, list):
        structural.append("issues must be a list")
        return
    body = str(script.get("body") or "")
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            structural.append(f"issues[{index}] must be an object")
            continue
        _require_fields(issue, ["span", "risk_type", "severity", "reason", "repair_boundary", "protected_elements", "revision_direction"], structural, prefix=f"issues[{index}].")
        span = str(issue.get("span") or "")
        if not span or span not in body:
            gates.append(f"issues[{index}].span must quote the reviewed body")
    quality = packet.get("current_quality_review") or {}
    if quality.get("verdict") != "pass" or quality.get("reviewed_body_hash") != result.get("reviewed_body_hash"):
        gates.append("risk review requires a quality pass for the same script body")
    if verdict == "pass":
        if any((issue or {}).get("severity") == "hard_fail" for issue in issues if isinstance(issue, dict)):
            gates.append("risk pass cannot contain hard_fail issues")
        if result.get("revision_request") not in (None, {}):
            gates.append("risk pass must not contain a revision_request")
    else:
        if not issues:
            gates.append("a non-pass risk review requires at least one issue")
        _validate_revision_request(result.get("revision_request"), structural, gates)


def _validate_read_only_review(result: dict[str, Any], structural: list[str]) -> None:
    forbidden = sorted(REVIEW_COPY_KEYS & set(result))
    if forbidden:
        structural.append("review output must not contain viewer copy fields: " + ", ".join(forbidden))


def _validate_review_binding(result: dict[str, Any], script: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    if not script:
        gates.append("review requires a current confirmed script")
        return
    if result.get("reviewed_script_run_id") != script.get("stage_run_id"):
        gates.append("reviewed_script_run_id does not match the current script")
    if result.get("reviewed_body_hash") != script.get("body_hash"):
        gates.append("reviewed_body_hash does not match the current script")


def _validate_revision_request(value: Any, structural: list[str], gates: list[str]) -> None:
    if not isinstance(value, dict):
        structural.append("a non-pass review requires revision_request object")
        return
    _require_fields(value, ["revision_scope", "problems", "revision_directions", "protected_elements", "protected_spans", "max_edit_boundary"], structural, prefix="revision_request.")
    if value.get("revision_scope") not in WRITING_MODES - {"initial_draft"}:
        structural.append("revision_request.revision_scope is invalid")
    for field in ["problems", "revision_directions", "protected_elements", "protected_spans"]:
        if not isinstance(value.get(field), list):
            structural.append(f"revision_request.{field} must be a list")
    if not value.get("problems") or not value.get("revision_directions"):
        gates.append("revision_request requires concrete problems and revision_directions")


def _validate_publish(result: dict[str, Any], packet: dict[str, Any], structural: list[str], gates: list[str]) -> None:
    package = result.get("publish_package")
    if not isinstance(package, dict):
        structural.append("publish_package must be an object")
        return
    _require_fields(package, stage_contract("publish_format")["package_required"], structural, prefix="publish_package.")
    script = packet.get("current_script") or {}
    if script:
        expected = str(script.get("body") or "")
        quality = packet.get("current_quality_review") or {}
        risk = packet.get("current_risk_review") or {}
        if quality.get("verdict") != "pass" or risk.get("verdict") != "pass":
            gates.append("publish_format requires quality and risk pass")
        if quality.get("reviewed_body_hash") != script.get("body_hash") or risk.get("reviewed_body_hash") != script.get("body_hash"):
            gates.append("publish_format reviews must bind to the current script body")
    else:
        risk = packet.get("upstream_outputs", {}).get("risk_cleanup") or {}
        expected = str(risk.get("cleaned_body") or "")
    if expected and package.get("final_copy") != expected:
        gates.append("publish_package.final_copy must equal the approved current script")
