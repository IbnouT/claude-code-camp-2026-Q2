"""Pydantic-owned envelopes used by the version 1 public API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..contracts import (
    ExperimentDefinition,
    ExperimentFeature,
    ExperimentScenario,
    ExperimentValidation,
    RecordedSessionCatalogItem,
    RunSummary,
)


class PublicContract(BaseModel):
    """Strict immutable base for authored public envelopes."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ApiError(PublicContract):
    """One stable machine-readable API failure."""

    contract_version: Literal["v1"] = "v1"
    error: str = Field(min_length=1)
    detail: str | None = None


class HealthResponse(PublicContract):
    """Current API health and authority split."""

    status: Literal["ok"]
    evidence_plane: Literal["read_only"]
    control_plane: Literal["authenticated_local"]


class PlayerOption(PublicContract):
    """One player represented in the session catalog."""

    id: str = Field(max_length=512)
    label: str = Field(max_length=512)


class SessionCatalogItem(PublicContract):
    """One launcher session without loading its retained evidence."""

    id: str = Field(max_length=512)
    player_id: str = Field(max_length=512)
    character: str = Field(max_length=512)
    gateway_session_id: str = Field(max_length=512)
    state: str = Field(max_length=128)
    control_state: str | None
    control_available: bool
    capture_status: str = Field(max_length=128)
    created_at: str = Field(max_length=128)
    updated_at: str = Field(max_length=128)
    ended_at: str | None = Field(default=None, max_length=128)
    stop_mode: str | None = Field(default=None, max_length=128)
    projection_status: Literal["available", "pending", "fault"]
    projection_gaps: tuple[str, ...] = Field(max_length=16)
    event_count: int | None = Field(default=None, ge=0)
    latest_seq: int | None = Field(default=None, ge=0)
    legacy: bool
    live: bool
    objective: str | None = Field(default=None, max_length=512)
    goal_count: int | None = Field(default=None, ge=0)
    nudge_count: int | None = Field(default=None, ge=0)


class SessionCatalogResponse(PublicContract):
    """Future bounded session discovery page."""

    resource_id: Literal["session-catalog"] = "session-catalog"
    resource_version: int = Field(ge=1)
    source_cursor: str = Field(min_length=1)
    completeness: Literal["complete", "partial", "degraded"]
    continuation_cursor: str | None
    capture_gaps: tuple[str, ...] = Field(max_length=32)
    source_refs: tuple[str, ...] = Field(max_length=16)
    players: tuple[PlayerOption, ...] = Field(max_length=50)
    sessions: tuple[SessionCatalogItem, ...] = Field(max_length=50)


class RunCatalogResponse(PublicContract):
    """Available benchmark runs."""

    runs: tuple[RunSummary, ...]


class RecordedSessionCatalogResponse(PublicContract):
    """Available retained experiment-backed session bundles."""

    sessions: tuple[RecordedSessionCatalogItem, ...]


class ComparisonSummary(PublicContract):
    """One available comparison without its full evidence."""

    id: str
    title: str
    journey: str


class ComparisonCatalogResponse(PublicContract):
    """Available evidence-backed comparisons."""

    comparisons: tuple[ComparisonSummary, ...]


class ExperimentExecutionCapability(PublicContract):
    """Local experiment execution policy without credentials."""

    available: bool
    state_store_available: bool
    max_spend_usd: float = Field(ge=0)
    paid_confirmation_required: bool


class ExperimentCatalogResponse(PublicContract):
    """Features, scenarios, and local execution policy."""

    registry: tuple[ExperimentFeature, ...]
    scenarios: tuple[ExperimentScenario, ...]
    execution: ExperimentExecutionCapability


class ExperimentSampleState(PublicContract):
    """One sample in a persisted experiment job."""

    id: str
    arm_id: str
    ordinal: int = Field(ge=1)
    state: str
    run_id: str | None
    cost_usd: float | None
    turns: int | None
    calls: int | None
    detail: str
    effective_config: dict[str, bool | int | float | str]


class ExperimentJobResponse(PublicContract):
    """One persisted and resumable experiment job."""

    id: str
    request_id: str
    player_profile: str
    definition_id: str
    definition: ExperimentDefinition
    state: str
    confirmed_max_spend_usd: float = Field(ge=0)
    spent_usd: float = Field(ge=0)
    current_sample: str | None
    samples: tuple[ExperimentSampleState, ...]


class ExperimentJobsResponse(PublicContract):
    """All locally persisted experiment jobs."""

    jobs: tuple[ExperimentJobResponse, ...]


class ExperimentControlRequest(PublicContract):
    """A reversible experiment lifecycle command."""

    action: Literal["stop", "resume"]


class ExperimentValidationResponse(PublicContract):
    """Validation result and deterministic sample queue."""

    validation: ExperimentValidation
    queue: tuple[str, ...]


class KnowledgeRecoveryReceipt(PublicContract):
    """Public-safe receipt for a selected knowledge action."""

    ok: bool
    action: Literal["reset", "restore"]
    player_id: str
    session_id: str


class LiveControlReceipt(PublicContract):
    """Public-safe agent control acknowledgement."""

    ok: bool
    request_id: str
    action: str
    state: str
    insertion: str


class ResourceChangedNotification(PublicContract):
    """One notification that identifies a bounded resource to refetch."""

    contract_version: Literal["v1"] = "v1"
    event: Literal["resource_changed"] = "resource_changed"
    resource_kind: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    resource_version: int = Field(ge=1)
    source_cursor: str = Field(min_length=1)
    at: float


class SessionCommandRequest(PublicContract):
    """Future optimistic command against one exact session cursor."""

    request_id: str = Field(min_length=8, max_length=128)
    action: Literal["guide", "revise", "pause", "resume", "stop"]
    instruction: str | None = Field(default=None, max_length=4_000)
    expected_cursor: str = Field(min_length=1)


class CommandAccepted(PublicContract):
    """Future durable acknowledgement for one accepted session command."""

    command_id: str = Field(min_length=1)
    request_id: str = Field(min_length=8, max_length=128)
    resource_id: str = Field(min_length=1)
    state: Literal["queued"] = "queued"
    submitted_at: str = Field(min_length=1)


PUBLIC_COMPONENT_MODELS: tuple[type[BaseModel], ...] = (
    ApiError,
    CommandAccepted,
    HealthResponse,
    ResourceChangedNotification,
    SessionCommandRequest,
    SessionCatalogResponse,
)
