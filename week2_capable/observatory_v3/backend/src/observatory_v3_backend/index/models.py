"""Typed logical rows written to the disposable index."""

from __future__ import annotations

from dataclasses import dataclass

from .identity import EntityKind


@dataclass(frozen=True, slots=True)
class SourceWatermark:
    """Source-native coordinates captured by one explicit rebuild."""

    registry_updated_at: str
    lifecycle_sequence: int
    gateway_session_id: str
    gateway_sequence: int
    agent_source_id: str
    agent_offset: int
    agent_next_line: int
    operator_source_id: str
    operator_revision: str
    experiment_revision: str | None


@dataclass(frozen=True, slots=True)
class IndexedEntity:
    """One stable hierarchy or evidence target."""

    id: str
    session_id: str
    player_id: str
    kind: EntityKind
    source_anchor: str
    parent_id: str | None
    goal_id: str | None
    turn_id: str | None
    iteration_id: str | None
    ordinal: int
    occurred_at: str
    title: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class SearchDocument:
    """Sanitized search text attached to one stable entity."""

    entity_id: str
    session_id: str
    player_id: str
    kind: EntityKind
    occurred_at: str
    title: str
    body: str


@dataclass(frozen=True, slots=True)
class ExperimentCorrelation:
    """One authoritative experiment and run link to a canonical session."""

    id: str
    experiment_id: str
    run_id: str
    session_id: str


@dataclass(frozen=True, slots=True)
class SessionProjection:
    """A complete selected-session replacement prepared before the write."""

    session_id: str
    player_id: str
    character: str
    state: str
    created_at: str
    updated_at: str
    ended_at: str | None
    capture_status: str
    latest_goal_id: str | None
    latest_goal: str | None
    goal_count: int
    nudge_count: int
    turn_count: int
    iteration_count: int
    record_count: int
    watermark: SourceWatermark
    entities: tuple[IndexedEntity, ...]
    search_documents: tuple[SearchDocument, ...]
    experiment: ExperimentCorrelation | None
    capture_gaps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One bounded catalog summary from the derived store."""

    session_id: str
    player_id: str
    character: str
    state: str
    created_at: str
    updated_at: str
    ended_at: str | None
    capture_status: str
    latest_goal: str | None
    goal_count: int
    nudge_count: int
    turn_count: int
    iteration_count: int
    generation: int


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One deterministic full-text result and stable navigation target."""

    entity_id: str
    session_id: str
    player_id: str
    kind: str
    title: str
    body: str
    occurred_at: str
    rank: float
