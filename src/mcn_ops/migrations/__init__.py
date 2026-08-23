"""Explicit, offline database migrations for mcn-ops."""

from .collection_schema_v3 import (
    COLLECTION_SCHEMA_V3,
    CollectionSchemaV3Migrator,
    MigrationError,
    migrate_collection_schema_v3,
)
from .material_inventory_v1 import (
    MATERIAL_INVENTORY_V1,
    ensure_material_inventory_schema,
    migrate_material_inventory_v1,
)

__all__ = [
    "COLLECTION_SCHEMA_V3",
    "CollectionSchemaV3Migrator",
    "MigrationError",
    "migrate_collection_schema_v3",
    "COLLECTION_TASK_ORCHESTRATION_V1",
    "ensure_collection_task_orchestration_schema",
    "migrate_collection_task_orchestration_v1",
    "MATERIAL_INVENTORY_V1",
    "ensure_material_inventory_schema",
    "migrate_material_inventory_v1",
]


def __getattr__(name: str):
    if name in {
        "COLLECTION_TASK_ORCHESTRATION_V1",
        "ensure_collection_task_orchestration_schema",
        "migrate_collection_task_orchestration_v1",
    }:
        from . import collection_task_orchestration_v1

        return getattr(collection_task_orchestration_v1, name)
    raise AttributeError(name)
