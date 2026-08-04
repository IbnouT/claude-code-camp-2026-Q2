"""Typed bounded response contracts shared by all read resources."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..json_types import JsonValue

Completeness = Literal["complete", "partial", "degraded"]
EntityKind = Literal[
    "session",
    "goal",
    "nudge",
    "turn",
    "iteration",
    "record",
    "trace",
    "experiment_sample",
]
LivePartition = Literal[
    "identity-lifecycle",
    "world-map",
    "position-path",
    "thought-activity",
    "vitals-combat",
    "economics",
    "controls",
    "diagnostics",
]


class ResourceContract(BaseModel):
    """Strict immutable base for bounded public resources."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ResourceMetadata(ResourceContract):
    """Evidence identity and completeness repeated on every resource."""

    resource_id: str = Field(min_length=1, max_length=512)
    resource_version: int = Field(ge=1)
    source_cursor: str = Field(min_length=1)
    completeness: Completeness
    capture_gaps: tuple[str, ...] = Field(max_length=32)
    source_refs: tuple[str, ...] = Field(max_length=16)


class MaterializationPendingResponse(ResourceMetadata):
    """Truthful selected-session state while the canonical projection advances."""

    session_id: str
    state: Literal["materialization_pending"]
    retry_after_ms: int = Field(ge=1, le=5_000)


class EntitySummary(ResourceContract):
    """One hierarchy node without its retained payload."""

    id: str
    kind: EntityKind
    parent_id: str | None
    goal_id: str | None
    turn_id: str | None
    iteration_id: str | None
    ordinal: int = Field(ge=0)
    occurred_at: str
    title: str
    source_ref: str
    duration_ms: float | None = Field(default=None, ge=0)
    tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class EntityPageResponse(ResourceMetadata):
    """One keyset page in the session hierarchy."""

    continuation_cursor: str | None
    items: tuple[EntitySummary, ...] = Field(max_length=100)


class GoalResource(ResourceContract):
    """One useful Goal row with bounded owned context."""

    goal: EntitySummary
    nudges: tuple[EntitySummary, ...] = Field(max_length=5)
    turns: tuple[EntitySummary, ...] = Field(max_length=5)
    outcome: str | None
    tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    duration_ms: float = Field(ge=0)
    child_continuation_cursor: str | None


class GoalPageResponse(ResourceMetadata):
    """One keyset page of Goals and bounded useful owned context."""

    continuation_cursor: str | None
    items: tuple[GoalResource, ...] = Field(max_length=20)


class TurnResource(ResourceContract):
    """One useful Turn row with bounded Iteration context."""

    turn: EntitySummary
    iterations: tuple[EntitySummary, ...] = Field(max_length=10)
    outcome: str | None
    tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    duration_ms: float = Field(ge=0)
    child_continuation_cursor: str | None


class TurnPageResponse(ResourceMetadata):
    """One keyset page of Turns and bounded useful Iteration context."""

    continuation_cursor: str | None
    items: tuple[TurnResource, ...] = Field(max_length=20)


class LifecycleSummary(ResourceContract):
    """One bounded lifecycle transition in a session summary."""

    sequence: int = Field(ge=1)
    at: str
    state: str
    detail: dict[str, JsonValue]


class SessionTotals(ResourceContract):
    """Materialized totals available without loading hierarchy pages."""

    goals: int = Field(ge=0)
    nudges: int = Field(ge=0)
    turns: int = Field(ge=0)
    iterations: int = Field(ge=0)
    records: int = Field(ge=0)
    tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    duration_ms: float = Field(ge=0)


class SessionSummaryResponse(ResourceMetadata):
    """Fixed useful summary for one selected materialized session."""

    session_id: str = Field(max_length=512)
    player_id: str = Field(max_length=512)
    character: str = Field(max_length=512)
    state: str = Field(max_length=128)
    created_at: str = Field(max_length=128)
    updated_at: str = Field(max_length=128)
    ended_at: str | None = Field(max_length=128)
    capture_status: str = Field(max_length=128)
    latest_goal_id: str | None = Field(max_length=512)
    latest_goal: str | None = Field(max_length=512)
    totals: SessionTotals
    lifecycle: tuple[LifecycleSummary, ...] = Field(max_length=32)
    lifecycle_cursor: str | None
    goal_cursor: str | None
    search_cursor: str | None


class LifecyclePageResponse(ResourceMetadata):
    """One keyset page of retained lifecycle transitions."""

    continuation_cursor: str | None
    items: tuple[LifecycleSummary, ...] = Field(max_length=100)


class EvidenceRecordResponse(ResourceMetadata):
    """One retained record with ancestry, provenance, and sanitized fields."""

    record: EntitySummary
    evidence_kind: str
    trace_id: str | None
    integrity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    fields: dict[str, JsonValue]
    ancestry: tuple[str, ...] = Field(max_length=8)
    related_ids: tuple[str, ...] = Field(max_length=100)


class TraceRecord(ResourceContract):
    """One bounded subsystem record inside a correlated trace."""

    record: EntitySummary
    evidence_kind: str


class TracePageResponse(ResourceMetadata):
    """One keyset page across a correlated trace."""

    trace_id: str
    continuation_cursor: str | None
    items: tuple[TraceRecord, ...] = Field(max_length=100)


class WireBodyResponse(ResourceMetadata):
    """One verified sanitized wire body with a strict request limit."""

    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: Literal["text/plain; charset=utf-8"]
    byte_length: int = Field(ge=0, le=65_536)
    truncated: bool
    body: str
    redacted: bool


class ValueChunkResponse(ResourceMetadata):
    """One bounded base64 chunk of canonical sanitized retained content."""

    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    offset: int = Field(ge=0)
    next_offset: int | None = Field(default=None, ge=1)
    total_bytes: int = Field(ge=0)
    encoding: Literal["base64"]
    chunk: str


class MapNode(ResourceContract):
    """One observed place in a bounded graph prefix."""

    id: str
    title: str
    x: float | None = None
    y: float | None = None
    exits: tuple[str, ...] = Field(max_length=32)
    last_sequence: int = Field(ge=0)
    source_ref: str


class MapEdge(ResourceContract):
    """One observed directed transition."""

    source: str
    target: str
    direction: str
    sequence: int = Field(ge=0)


class MapPrefixResponse(ResourceMetadata):
    """Bounded graph, selected position, and recent path."""

    current_room_id: str | None
    nodes: tuple[MapNode, ...] = Field(max_length=200)
    edges: tuple[MapEdge, ...] = Field(max_length=400)
    recent_path: tuple[str, ...] = Field(max_length=100)
    continuation_cursor: str | None


class CostContributor(ResourceContract):
    """One response-owned token or cost contribution."""

    record_id: str
    occurred_at: str
    model: str | None
    tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    duration_ms: float = Field(ge=0)
    source_ref: str


class CostRangeResponse(ResourceMetadata):
    """Explicit bounded cost scope with its exact contributors."""

    scope_id: str
    total_tokens: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0)
    total_duration_ms: float = Field(ge=0)
    continuation_cursor: str | None
    contributors: tuple[CostContributor, ...] = Field(max_length=100)


class SearchMatch(ResourceContract):
    """One stable search result and navigation target."""

    record_id: str
    kind: EntityKind
    occurred_at: str
    title: str
    excerpt: str


class SearchPageResponse(ResourceMetadata):
    """One stable keyset page of sanitized evidence matches."""

    query: str
    continuation_cursor: str | None
    matches: tuple[SearchMatch, ...] = Field(max_length=50)


class LivePartitionResponse(ResourceMetadata):
    """One independently replaceable Live projection partition."""

    session_id: str
    partition: LivePartition
    stable_node_ids: tuple[str, ...] = Field(max_length=512)
    values: dict[str, JsonValue]


class ObservedPlayerValue(ResourceContract):
    """One observed player-state value and its supporting observation."""

    value: bool | int | str
    sequence: int = Field(ge=0)
    observed_at: float
    confidence: str = Field(max_length=64)
    method: str = Field(max_length=64)


class LiveVitalsResponse(ResourceMetadata):
    """The selected session's observed player state for roster vitals."""

    session_id: str
    player_id: str = Field(max_length=512)
    fields: dict[str, ObservedPlayerValue]


class ExperimentSummary(ResourceContract):
    """One immutable experiment identity and its bounded sample totals."""

    experiment_id: str
    sample_count: int = Field(ge=0)
    session_count: int = Field(ge=0)
    latest_session_at: str


class ExperimentDefinitionSummary(ResourceContract):
    """One bounded immutable definition when a retained source is available."""

    id: str
    values: dict[str, JsonValue]


class ExperimentJobSummary(ResourceContract):
    """One bounded retained job summary when a source is available."""

    id: str
    state: str
    values: dict[str, JsonValue]


class ExperimentCatalogPage(ResourceMetadata):
    """One bounded experiment catalog page."""

    continuation_cursor: str | None
    experiments: tuple[ExperimentSummary, ...] = Field(max_length=50)
    definitions: tuple[ExperimentDefinitionSummary, ...] = Field(max_length=50)
    jobs: tuple[ExperimentJobSummary, ...] = Field(max_length=50)


class ExperimentSampleSummary(ResourceContract):
    """One experiment sample and its canonical session when retained."""

    run_id: str
    session_id: str | None
    player_id: str
    state: str
    updated_at: str
    cost_usd: float = Field(ge=0)
    turns: int = Field(ge=0)


class ExperimentDetailResponse(ResourceMetadata):
    """One experiment identity with a paginated sample page."""

    experiment_id: str
    continuation_cursor: str | None
    definition: ExperimentDefinitionSummary | None
    arms: tuple[dict[str, JsonValue], ...] = Field(max_length=50)
    queue: tuple[dict[str, JsonValue], ...] = Field(max_length=100)
    aggregates: dict[str, int | float]
    session_links: tuple[str, ...] = Field(max_length=100)
    samples: tuple[ExperimentSampleSummary, ...] = Field(max_length=100)


class KnowledgeMetric(ResourceContract):
    """One stable summary count from the durable knowledge store."""

    id: str
    value: int | float


class KnowledgeSummaryResponse(ResourceMetadata):
    """Fixed player knowledge totals, conflicts, and freshness."""

    player_id: str
    cdc_cursor: int = Field(ge=0)
    metrics: tuple[KnowledgeMetric, ...] = Field(max_length=16)


class KnowledgeItem(ResourceContract):
    """One bounded durable knowledge record with provenance."""

    id: str
    kind: Literal["assertion", "change", "snapshot", "recovery"]
    values: dict[str, JsonValue]
    source_refs: tuple[str, ...] = Field(max_length=32)
    evidence_continuation_cursor: str | None = None


class KnowledgeDetailPage(ResourceMetadata):
    """One keyset page from a selected durable knowledge layer."""

    player_id: str
    kind: Literal["assertion", "change", "snapshot", "recovery"]
    continuation_cursor: str | None
    items: tuple[KnowledgeItem, ...] = Field(max_length=100)


class KnowledgeEvidenceRef(ResourceContract):
    """One retained assertion evidence reference."""

    id: int = Field(ge=1)
    values: dict[str, JsonValue]


class KnowledgeEvidencePage(ResourceMetadata):
    """One keyset page of retained assertion evidence references."""

    player_id: str
    assertion_id: str
    continuation_cursor: str | None
    items: tuple[KnowledgeEvidenceRef, ...] = Field(max_length=100)


PageLimit = Annotated[int, Field(ge=1, le=100)]
