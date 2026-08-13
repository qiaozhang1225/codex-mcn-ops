from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROFESSIONAL_CARD_REQUIRED_FIELDS = {
    "id",
    "claim",
    "functions",
    "applicable_scenes",
    "evidence_level",
    "sources",
}


def role_slug(role: dict[str, Any]) -> str:
    for source in (role.get("style_anchors") or {}, role.get("source_evidence") or {}, role.get("agent_suggestions") or {}):
        value = source.get("knowledge_slug") if isinstance(source, dict) else None
        if value:
            return _clean_slug(value)
    return _clean_slug(role.get("name") or role.get("id") or "unknown-role")


def load_role_knowledge_config(root: Path, role: dict[str, Any]) -> dict[str, Any]:
    slug = role_slug(role)
    profile_path = root / "ip" / slug / "role-profile.json"
    profile: dict[str, Any] = {}
    if profile_path.exists():
        value = json.loads(profile_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"role profile must be a JSON object: {profile_path}")
        profile = value
    return {
        "role_slug": slug,
        "domain_pack": str(profile.get("domain_pack") or "common"),
        "professional_alignment_enabled": bool(profile.get("professional_alignment_enabled", False)),
        "profile_path": str(profile_path),
        "profile": profile,
    }


def load_professional_knowledge(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValueError(f"{path} must use JSON-compatible YAML unless PyYAML is installed") from exc
        value = yaml.safe_load(text)
    if isinstance(value, dict) and "cards" in value:
        value = value["cards"]
    if not isinstance(value, list):
        raise ValueError(f"professional knowledge must contain a list of cards: {path}")
    return [dict(item) for item in value if isinstance(item, dict)]


def validate_role_knowledge(root: Path, role: dict[str, Any]) -> dict[str, Any]:
    config = load_role_knowledge_config(root, role)
    slug = config["role_slug"]
    domain_pack = config["domain_pack"]
    errors: list[str] = []
    warnings: list[str] = []
    common_path = root / "domains" / "common" / "playbook.md"
    domain_path = root / "domains" / domain_pack / "playbook.md"
    ip_root = root / "ip" / slug
    required_paths = [
        root / "creation" / "material-selection-playbook.md",
        root / "creation" / "global-rewrite-playbook.md",
        root / "creation" / "script-writer-playbook.md",
        root / "creation" / "quality-review-playbook.md",
        root / "creation" / "five-affliction-quality-review.md",
        root / "creation" / "risk-review-playbook.md",
        Path(config["profile_path"]),
        ip_root / "creation-playbook.md",
        common_path,
        domain_path,
    ]
    for path in required_paths:
        if not path.exists():
            errors.append(f"missing required knowledge file: {path}")

    professional_path = ip_root / "professional-knowledge.yaml"
    try:
        cards = load_professional_knowledge(professional_path)
    except ValueError as exc:
        cards = []
        errors.append(str(exc))
    card_ids: set[str] = set()
    for index, card in enumerate(cards):
        missing = sorted(PROFESSIONAL_CARD_REQUIRED_FIELDS - set(card))
        if missing:
            errors.append(f"professional card {index} missing: {', '.join(missing)}")
        card_id = str(card.get("id") or "")
        if card_id in card_ids:
            errors.append(f"duplicate professional card id: {card_id}")
        if card_id:
            card_ids.add(card_id)
        for list_field in ["functions", "applicable_scenes", "sources"]:
            if list_field in card and not isinstance(card[list_field], list):
                errors.append(f"professional card {card_id or index} field {list_field} must be a list")
        if not card.get("risk_note"):
            warnings.append(f"professional card {card_id or index} has no risk_note")
    if config["professional_alignment_enabled"] and not cards:
        errors.append("professional_alignment_enabled requires at least one professional knowledge card")
    return {
        "role_id": role.get("id"),
        "role_slug": slug,
        "domain_pack": domain_pack,
        "professional_alignment_enabled": config["professional_alignment_enabled"],
        "professional_card_count": len(cards),
        "errors": errors,
        "warnings": warnings,
        "valid": not errors,
    }


def _clean_slug(value: Any) -> str:
    raw = str(value or "unknown-role").strip().lower()
    slug = re.sub(r"\s+", "-", raw)
    slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", slug)
    return slug or "unknown-role"
