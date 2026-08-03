"""Readable notification targets derived from one committed session."""

from __future__ import annotations

from pydantic import BaseModel

from ..api_v1.contracts import ResourceChangeTarget
from ..resources.contracts import LivePartition
from ..resources.repository import ResourceRepository

LIVE_PARTITIONS: tuple[LivePartition, ...] = (
    "identity-lifecycle",
    "world-map",
    "position-path",
    "thought-activity",
    "vitals-combat",
    "economics",
    "controls",
    "diagnostics",
)


class CommittedResourceTargets:
    """Read exact resource metadata before allowing its notification."""

    def __init__(self, resources: ResourceRepository) -> None:
        self._resources = resources

    def for_session(self, session_id: str) -> tuple[ResourceChangeTarget, ...]:
        """Return the bounded root resources affected by a session commit."""
        values: list[tuple[str, BaseModel]] = [
            ("session_summary", self._resources.session_summary(session_id)),
            (
                "lifecycle",
                self._resources.lifecycle_page(
                    session_id,
                    cursor=None,
                    limit=100,
                ),
            ),
            (
                "goals",
                self._resources.goal_page(
                    session_id,
                    cursor=None,
                    limit=20,
                ),
            ),
            (
                "map",
                self._resources.map_prefix(
                    session_id,
                    cursor=None,
                ),
            ),
            (
                "cost",
                self._resources.cost_range(
                    session_id,
                    scope_id=None,
                    cursor=None,
                    limit=100,
                ),
            ),
        ]
        values.extend(
            (
                "live_partition",
                self._resources.live_partition(session_id, partition),
            )
            for partition in LIVE_PARTITIONS
        )
        return tuple(_target(kind, value) for kind, value in values)


def _target(resource_kind: str, value: BaseModel) -> ResourceChangeTarget:
    resource_id = getattr(value, "resource_id", None)
    resource_version = getattr(value, "resource_version", None)
    source_cursor = getattr(value, "source_cursor", None)
    if (
        not isinstance(resource_id, str)
        or not isinstance(resource_version, int)
        or not isinstance(source_cursor, str)
    ):
        raise TypeError("notification target must expose typed resource metadata")
    return ResourceChangeTarget(
        resource_kind=resource_kind,
        resource_id=resource_id,
        resource_version=resource_version,
        source_cursor=source_cursor,
    )
