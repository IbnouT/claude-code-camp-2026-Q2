"""Disposable Observatory index with deterministic retained identities."""

from .identity import EntityKind, stable_entity_id
from .projector import SessionIndexProjector
from .store import (
    CatalogPage,
    IndexCorruptionError,
    IndexProjectionConflict,
    IndexStore,
    IndexWriterUnavailableError,
    UnsupportedIndexSchemaError,
)

__all__ = [
    "CatalogPage",
    "EntityKind",
    "IndexCorruptionError",
    "IndexProjectionConflict",
    "IndexStore",
    "IndexWriterUnavailableError",
    "SessionIndexProjector",
    "UnsupportedIndexSchemaError",
    "stable_entity_id",
]
