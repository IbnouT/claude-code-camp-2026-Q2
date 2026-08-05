"""Pydantic-owned envelopes used by the version 1 public API."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from ..contracts import (
    ExperimentDefinition,
    ExperimentFeature,
    ExperimentScenario,
    ExperimentValidation,
    LiveJourneySnapshot,
    RecordedSessionCatalogItem,
    RunSummary,
    RuntimeSessionInvestigation,
)
from ..experiment_jobs.models import (
    ExperimentJobState,
)
from ..experiment_jobs.models import (
    ExperimentSampleState as DurableExperimentSampleState,
)


class PublicContract(BaseModel):
    """Strict immutable base for authored public envelopes."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )


class ApiError(PublicContract):
    """One stable machine-readable API failure."""

    contract_version: Literal["v1"] = "v1"
    error: str = Field(min_length=1)
    detail: str | None = None


class RetiredEndpointResponse(PublicContract):
    """One bounded terminal response for a replaced legacy route."""

    contract_version: Literal["v1"] = "v1"
    error: Literal["endpoint_retired"] = "endpoint_retired"
    method: Literal["GET", "POST"]
    legacy_path: str = Field(min_length=1, max_length=256)
    replacements: tuple[
        Annotated[str, Field(min_length=1, max_length=256)],
        ...,
    ] = Field(min_length=1, max_length=4)


class HealthResponse(PublicContract):
    """Current API health and authority split."""

    status: Literal["ok"]
    evidence_plane: Literal["read_only"]
    control_plane: Literal["authenticated_local"]


class PlayerOption(PublicContract):
    """One player represented in the session catalog."""

    id: str = Field(max_length=512)
    label: str = Field(max_length=512)
    start_available: bool = False


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
    turn_count: int | None = Field(default=None, ge=0)
    iteration_count: int | None = Field(default=None, ge=0)
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
    queue_position: int = Field(ge=0)
    state: DurableExperimentSampleState
    run_id: str | None
    session_id: str | None
    cost_usd: float | None
    turns: int | None
    calls: int | None
    detail: str
    effective_config: dict[str, bool | int | float | str]


class ExperimentAggregates(PublicContract):
    """Exact derived counts and retained spend for one experiment job."""

    planned: int = Field(ge=0)
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    success: int = Field(ge=0)
    failed: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    excluded: int = Field(ge=0)
    spent_usd: float = Field(ge=0)


class ExperimentJobResponse(PublicContract):
    """One persisted and resumable experiment job."""

    id: str
    request_id: str
    player_profile: str
    definition_id: str
    definition_version: int = Field(ge=1)
    definition: ExperimentDefinition
    state: ExperimentJobState
    confirmed_max_spend_usd: float = Field(ge=0)
    spent_usd: float = Field(ge=0)
    current_sample: str | None
    concurrency: int = Field(ge=1)
    launch_blocked: bool
    terminal_reason: str | None
    created_at: str
    updated_at: str
    continuation_cursor: str | None = None
    samples: tuple[ExperimentSampleState, ...] = Field(max_length=100)
    aggregates: ExperimentAggregates


class ExperimentJobsResponse(PublicContract):
    """All locally persisted experiment jobs."""

    continuation_cursor: str | None = None
    jobs: tuple[ExperimentJobResponse, ...] = Field(max_length=50)


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


class LiveViewResponse(PublicContract):
    """One derived Live view of a session, whole or through a prefix."""

    resource_id: str = Field(max_length=512)
    resource_version: int = Field(ge=1)
    source_cursor: str = Field(min_length=1, max_length=256)
    completeness: Literal["complete", "partial", "degraded"]
    capture_gaps: tuple[str, ...] = Field(max_length=32)
    source_refs: tuple[str, ...] = Field(max_length=16)
    session_id: str = Field(max_length=512)
    view: LiveJourneySnapshot


class SessionInvestigationResponse(PublicContract):
    """The complete recorded story of one retained session."""

    resource_id: str = Field(max_length=512)
    resource_version: int = Field(ge=1)
    source_cursor: str = Field(min_length=1, max_length=256)
    completeness: Literal["complete", "partial", "degraded"]
    capture_gaps: tuple[str, ...] = Field(max_length=32)
    source_refs: tuple[str, ...] = Field(max_length=16)
    session_id: str = Field(max_length=512)
    investigation: RuntimeSessionInvestigation


class ResourceChangeTarget(PublicContract):
    """One committed bounded resource identified for refetch."""

    resource_kind: str = Field(min_length=1, max_length=64)
    resource_id: str = Field(min_length=1, max_length=512)
    resource_version: int = Field(ge=1)
    source_cursor: str = Field(min_length=1, max_length=256)
    session_id: str | None = Field(default=None, min_length=1, max_length=200)
    player_id: str | None = Field(default=None, min_length=1, max_length=120)


class ResourceChangedNotification(PublicContract):
    """One notification that identifies a bounded resource to refetch."""

    contract_version: Literal["v1"] = "v1"
    event: Literal["resource_changed"] = "resource_changed"
    server_epoch: str = Field(pattern=r"^[0-9a-f]{32}$")
    change_counter: int = Field(ge=1)
    resource_kind: str = Field(min_length=1, max_length=64)
    resource_id: str = Field(min_length=1, max_length=512)
    resource_version: int = Field(ge=1)
    source_cursor: str = Field(min_length=1, max_length=256)
    session_id: str | None = Field(default=None, min_length=1, max_length=200)
    player_id: str | None = Field(default=None, min_length=1, max_length=120)
    at: float


class ResourceReconciliationNotification(PublicContract):
    """One bounded current-resource set after replay cannot continue."""

    contract_version: Literal["v1"] = "v1"
    event: Literal["reconcile"] = "reconcile"
    server_epoch: str = Field(pattern=r"^[0-9a-f]{32}$")
    change_counter: int = Field(ge=0)
    reason: Literal[
        "epoch_mismatch",
        "invalid_event_id",
        "replay_window_exhausted",
        "counter_ahead",
    ]
    resources: tuple[ResourceChangeTarget, ...] = Field(max_length=64)
    at: float


class ResourceNotification(
    RootModel[
        Annotated[
            ResourceChangedNotification | ResourceReconciliationNotification,
            Field(discriminator="event"),
        ]
    ]
):
    """Typed payload carried by the version 1 event stream."""


class SessionCommandRequest(PublicContract):
    """Durable optimistic command against one exact session cursor."""

    idempotency_key: str = Field(min_length=8, max_length=128)
    actor: str = Field(min_length=1, max_length=120)
    player_id: str = Field(min_length=1, max_length=120)
    action: Literal["guide", "revise", "pause", "resume", "stop"]
    instruction: str | None = Field(default=None, max_length=4_000)
    expected_cursor: str | None = Field(default=None, min_length=1, max_length=2_048)
    force: bool = False


class StartCommandRequest(PublicContract):
    """Durable asynchronous request for one player runtime."""

    idempotency_key: str = Field(min_length=8, max_length=128)
    actor: str = Field(min_length=1, max_length=120)
    player_id: str = Field(min_length=1, max_length=120)
    instruction: str | None = Field(default=None, max_length=4_000)
    reset: Literal["none", "temple", "baseline"] = "none"


class CommandResponse(PublicContract):
    """Bounded public-safe state for one durable command."""

    resource_id: str = Field(min_length=1)
    resource_version: Literal[1] = 1
    source_cursor: str = Field(min_length=1, max_length=256)
    command_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8, max_length=128)
    action: Literal["start", "guide", "revise", "pause", "resume", "stop"]
    actor: str = Field(min_length=1, max_length=120)
    player_id: str = Field(min_length=1, max_length=120)
    session_id: str | None
    expected_cursor: str | None
    state: Literal["queued", "running", "succeeded", "failed"]
    submitted_at: str = Field(min_length=1)
    started_at: str | None
    finished_at: str | None
    result_code: str | None
    result_detail: str | None = Field(default=None, max_length=500)
    result_session_id: str | None


PUBLIC_COMPONENT_MODELS: tuple[type[BaseModel], ...] = (
    ApiError,
    CommandResponse,
    HealthResponse,
    ResourceChangedNotification,
    ResourceNotification,
    ResourceReconciliationNotification,
    SessionCommandRequest,
    SessionCatalogResponse,
    StartCommandRequest,
)
