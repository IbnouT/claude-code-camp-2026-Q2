"""Facade over focused bounded read repositories."""

from __future__ import annotations

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


__all__ = [
    "ResourceNotFoundError",
    "ResourceRepository",
    "ResourceUnavailableError",
]
