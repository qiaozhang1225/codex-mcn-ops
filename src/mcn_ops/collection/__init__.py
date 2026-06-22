"""Material collection primitives for Codex MCN Ops."""

from .runner import CollectionConfig, CollectionResult, TopicCollectionRunner
from .understanding import build_material_understanding, evaluate_role_match

__all__ = [
    "CollectionConfig",
    "CollectionResult",
    "TopicCollectionRunner",
    "build_material_understanding",
    "evaluate_role_match",
]
