"""Facade over focused bounded read repositories."""

from __future__ import annotations

from ..experiment_jobs import ExperimentStore
from ..index import IndexStore
from ..repositories import RegistryDatabase
from .base import ResourceNotFoundError, ResourceUnavailableError
from .evidence import EvidenceResources
from .experiments import ExperimentResources
from .live import LiveResources
from .sessions import SessionResources


class ResourceRepository(
    SessionResources,
    EvidenceResources,
    LiveResources,
    ExperimentResources,
):
    """Expose the bounded resource surface through one application dependency."""

    def __init__(
        self,
        index: IndexStore,
        registry: RegistryDatabase,
        experiment_store: ExperimentStore | None = None,
    ) -> None:
        super().__init__(index, registry)
        self.experiment_store = experiment_store


__all__ = [
    "ResourceNotFoundError",
    "ResourceRepository",
    "ResourceUnavailableError",
]
