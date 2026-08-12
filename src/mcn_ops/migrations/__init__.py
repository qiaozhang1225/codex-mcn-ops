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
    "MATERIAL_INVENTORY_V1",
    "ensure_material_inventory_schema",
    "migrate_material_inventory_v1",
]
