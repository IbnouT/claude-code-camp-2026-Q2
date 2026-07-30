"""Typed public contracts for observatory sources and investigations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceStatus(BaseModel):
    """One evidence source and its current availability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Literal["gateway", "agent", "benchmark", "knowledge"]
    label: str
    state: Literal["ready", "unavailable", "disabled"]
    detail: str
    contract_digest: str | None = None


class ObservatoryCapabilities(BaseModel):
    """The exact sources and features available to this installation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = 1
    sources: tuple[SourceStatus, ...]
    features: tuple[str, ...]


class LiveTimelineItem(BaseModel):
    """One causal item placed on the selected gateway clock."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    sequence: int
    at: float
    source: Literal["agent", "gateway"]
    kind: str
    label: str
    cost_usd: float = 0
    tokens: int = 0
    trace_id: str | None = None


class LiveRoom(BaseModel):
    """One observed spatial identity in the selected evidence prefix."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    place: int
    title: str
    exits: tuple[str, ...]
    first_sequence: int
    last_sequence: int
    visits: int
    state: Literal["observed", "current"]
    confidence: str


class LiveJourneySnapshot(BaseModel):
    """One deterministic Live projection at an exact gateway sequence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    gateway_session_id: str
    player_id: str
    character: str
    lifecycle: str
    control_state: str | None
    following_live: bool
    through_sequence: int
    latest_sequence: int
    selected_at: float | None
    objective: str | None
    model: str | None
    tools: tuple[str, ...]
    iteration: int
    current_room: str | None
    position_confidence: str
    position_method: str | None
    combat: bool
    vitals: dict[str, int]
    cost_usd: float
    usage: dict[str, int]
    parse_miss_rate: float | None
    rooms: tuple[LiveRoom, ...]
    timeline: tuple[LiveTimelineItem, ...]
    capture_gaps: tuple[str, ...]


class LiveControlRequest(BaseModel):
    """One optimistic authenticated control request for a live session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=8, max_length=128)
    action: Literal["guide", "revise", "pause", "resume", "stop"]
    instruction: str | None = Field(default=None, max_length=4_000)
    expected_sequence: int = Field(ge=0)


class RunSummary(BaseModel):
    """One recorded benchmark attempt available for investigation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    journey: str
    attempt: str
    success: bool
    stop_reason: str
    iterations: int
    cost_usd: float
    result_mode: str


class EvidenceCitation(BaseModel):
    """One exact piece of evidence behind a diagnostic or lens value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source: Literal["agent", "gateway", "benchmark"]
    label: str
    sequence: int | None = None
    trace_id: str | None = None
    excerpt: str


class InvestigationEvent(BaseModel):
    """One sanitized causal event from a recorded run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int
    at: str
    phase: str
    label: str
    cost_usd: float = 0
    duration_ms: float = 0
    parent: int | None = None
    citation: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class DiagnosticRecord(BaseModel):
    """A deterministic finding with its trigger and evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: Literal[
        "false_completion",
        "position_ambiguity",
        "confusion_loop",
        "stall",
        "parse_degradation",
    ]
    severity: Literal["critical", "warning", "notice"]
    title: str
    detail: str
    mechanism: str
    at: int
    evidence: tuple[str, ...]


class EvidenceForm(BaseModel):
    """One layer in the wire-to-truth evidence lens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["available", "missing"]
    title: str
    text: str
    citations: tuple[str, ...] = ()


class EvidenceLens(BaseModel):
    """Five non-interchangeable forms of one selected run outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    wire: EvidenceForm
    parsed: EvidenceForm
    rendered: EvidenceForm
    believed: EvidenceForm
    truth: EvidenceForm


class WorldNode(BaseModel):
    """One distinct inferred place, never just a room title."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    place: int
    title: str
    exits: tuple[str, ...]
    visits: int
    evidence: tuple[int, ...] = ()
    first_seq: int
    last_seq: int
    state: Literal["observed", "candidate", "current"]
    confidence: str
    method: str


class WorldEdge(BaseModel):
    """One observed transition between distinct inferred places."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source: str
    target: str
    direction: str
    traversals: int
    evidence: tuple[int, ...]


class WorldProjection(BaseModel):
    """The evidence-backed journey graph and its unresolved current state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[WorldNode, ...]
    edges: tuple[WorldEdge, ...]
    current_title: str | None
    current_confidence: str
    candidates: tuple[str, ...]
    parse_miss_rate: float
    unknown_positions: int


class Investigation(BaseModel):
    """A reproducible diagnosis of one benchmark attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run: RunSummary
    events: tuple[InvestigationEvent, ...]
    diagnostics: tuple[DiagnosticRecord, ...]
    citations: tuple[EvidenceCitation, ...]
    lens: EvidenceLens
    world: WorldProjection


class SessionEvidenceRecord(BaseModel):
    """One sanitized record in a navigable session evidence hierarchy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    parent_id: str | None = None
    source: Literal["agent", "gateway", "benchmark"]
    form: Literal["wire", "parsed", "rendered", "believed", "truth"]
    kind: str
    label: str
    sequence: int
    at: str
    trace_id: str | None = None
    iteration: int | None = None
    turn: int | None = None
    room_id: str | None = None
    duration_ms: float = 0
    cost_usd: float = 0
    tokens: int = 0
    status: Literal["complete", "partial", "failed", "unknown"] = "unknown"
    preview: str
    fields: dict[str, Any] = Field(default_factory=dict)
    source_ref: str
    capture_gaps: tuple[str, ...] = ()


class SessionDiagnostic(BaseModel):
    """One versioned diagnostic that explains its own evidence boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: Literal[
        "false_completion",
        "belief_divergence",
        "position_ambiguity",
        "confusion_loop",
        "progress_stall",
        "parse_degradation",
        "corrective_call_cluster",
        "stale_action",
        "context_churn",
        "instrumentation_gap",
    ]
    severity: Literal["critical", "warning", "notice"]
    state: Literal["open", "acknowledged", "resolved"]
    title: str
    consequence: str
    rule_version: str
    threshold: str
    at_record: str
    evidence: tuple[str, ...]
    alternatives: tuple[str, ...]
    affected_conclusions: tuple[str, ...]
    resolution: str | None = None
    related_occurrences: tuple[str, ...] = ()


class SessionCostPoint(BaseModel):
    """One billed response linked to its exact session record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    iteration: int | None = None
    cost_usd: float
    raw_response_cost_usd: float
    pricing_source: Literal["attempt_cost_curve", "agent_response"]
    fresh_input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
    context_tokens: int
    progress: str


class SessionCostLedger(BaseModel):
    """Reconciled run economics with explicit completeness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_usd: float
    response_total_usd: float
    raw_response_total_usd: float
    reconciliation_delta_usd: float
    complete: bool
    completeness_detail: str
    fresh_input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
    points: tuple[SessionCostPoint, ...]


class RecordedSessionInvestigation(BaseModel):
    """One explicitly correlated recorded session and all retained evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = 1
    source_kind: Literal["experiment_sample"]
    correlation: str
    run: RunSummary
    player_id: str
    agent_session_id: str | None
    gateway_session_id: str | None
    objective: str | None
    model: str | None
    records: tuple[SessionEvidenceRecord, ...]
    diagnostics: tuple[SessionDiagnostic, ...]
    diagnostic_coverage: tuple[
        Literal[
            "false_completion",
            "belief_divergence",
            "position_ambiguity",
            "confusion_loop",
            "progress_stall",
            "parse_degradation",
            "corrective_call_cluster",
            "stale_action",
            "context_churn",
            "instrumentation_gap",
        ],
        ...,
    ]
    lens: EvidenceLens
    world: WorldProjection
    cost: SessionCostLedger
    capture_gaps: tuple[str, ...]


class RecordedSessionCatalogItem(BaseModel):
    """One recorded session with its evidence relationship made explicit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source_kind: Literal["experiment_sample"]
    player_id: str
    label: str
    journey: str
    attempt: str
    success: bool
    stop_reason: str
    iterations: int
    cost_usd: float
    result_mode: str


class KnowledgeMetric(BaseModel):
    """One evidence-backed measure in the current knowledge view."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    value: int | float | str
    detail: str


class FrontierItem(BaseModel):
    """One unresolved or unexplored edge backed by recorded evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    kind: Literal["unresolved_position", "untraversed_exit", "missing_source"]
    detail: str
    citations: tuple[str, ...] = ()


class KnowledgeOverview(BaseModel):
    """Honest knowledge coverage without filling absent layers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["ready", "partial", "unavailable"]
    source: str
    metrics: tuple[KnowledgeMetric, ...]
    frontier: tuple[FrontierItem, ...]
    entities: tuple[str, ...]
    player: dict[str, str | int | float]
    progression: tuple[str, ...]
    missing_layers: tuple[str, ...]


class DiagnosticHistoryItem(BaseModel):
    """Cross-session prevalence for one deterministic diagnostic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    runs: int
    critical: int
    warning: int
    notice: int
    latest_run: str


class DiagnosticHistory(BaseModel):
    """Diagnostic prevalence across every readable benchmark run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_runs: int
    successful_runs: int
    failed_runs: int
    items: tuple[DiagnosticHistoryItem, ...]


class InvestigatorAnnotation(BaseModel):
    """Investigator-authored context that never mutates source evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=120)
    at: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=2_000)
    created_at: str


class IncidentExportRequest(BaseModel):
    """Selection and local annotations included in a portable capsule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=160)
    selected_sequence: int = Field(ge=0)
    diagnostic_id: str | None = Field(default=None, max_length=160)
    annotations: tuple[InvestigatorAnnotation, ...] = ()


class IncidentSelection(BaseModel):
    """The exact investigation focus restored when a capsule opens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_sequence: int
    diagnostic_id: str | None


class RedactionReport(BaseModel):
    """Visible proof of the export boundary applied to a capsule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: str
    replacements: int
    local_paths_included: bool = False
    credentials_included: bool = False


class IncidentPayload(BaseModel):
    """Portable evidence and derived views needed for offline investigation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: str
    title: str
    source_versions: dict[str, str]
    investigation: Investigation
    knowledge: KnowledgeOverview
    history: DiagnosticHistory
    selection: IncidentSelection
    annotations: tuple[InvestigatorAnnotation, ...]
    redaction: RedactionReport


class IncidentCapsule(BaseModel):
    """Versioned incident envelope with deterministic integrity digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["boukensha.observatory.incident"] = (
        "boukensha.observatory.incident"
    )
    version: int = 1
    digest: str
    payload: IncidentPayload


class AttentionEconomics(BaseModel):
    """Mean attention and payload cost for one comparable cohort."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fresh_tokens: float
    cache_read_tokens: float
    cache_write_tokens: float
    output_tokens: float
    result_chars: float
    schema_tokens: float
    movement_share: float


class ComparisonCohort(BaseModel):
    """Aggregate results for one model-facing rendering policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["raw", "minimal", "full"]
    samples: int
    successes: int
    cost_mean: float
    cost_median: float
    cost_stdev: float
    calls_mean: float
    calls_stdev: float
    invalid_calls: int
    corrective_calls: int
    tools: dict[str, int]
    attention: AttentionEconomics


class ComparisonMilestone(BaseModel):
    """One semantic action used to align representative runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int
    kind: Literal["observe", "move", "inspect", "outcome", "other"]
    label: str
    tool: str | None
    argument: str | None


class ComparisonLane(BaseModel):
    """One representative run aligned by semantic action ordinal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["raw", "minimal", "full"]
    attempt: str
    success: bool
    cost_usd: float
    calls: int
    milestones: tuple[ComparisonMilestone, ...]


class FirstDivergence(BaseModel):
    """The earliest semantic action where comparable runs disagree."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int | None
    summary: str
    actions: dict[str, str]


class CounterfactualProjection(BaseModel):
    """One rendering of identical recorded results, with no model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["raw", "minimal", "full"]
    observations: int
    bytes: int
    estimated_tokens: int
    delta_from_raw: float


class ParserCounterfactual(BaseModel):
    """A replay of recorded wire frames through the current canonical parser."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["raw", "minimal", "full"]
    frames: int
    recorded_version: str
    replayed_version: str
    recorded_lines: int
    recorded_typed: int
    replayed_lines: int
    replayed_typed: int
    recorded_miss_rate: float
    replayed_miss_rate: float
    typed_delta: int


class RunComparison(BaseModel):
    """A complete J1 cohort, alignment, and deterministic replay comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    journey: str
    cohorts: tuple[ComparisonCohort, ...]
    lanes: tuple[ComparisonLane, ...]
    divergence: FirstDivergence
    counterfactuals: tuple[CounterfactualProjection, ...]
    parser_counterfactuals: tuple[ParserCounterfactual, ...]
    findings: tuple[str, ...]


class AskRequest(BaseModel):
    """One natural-language investigation constrained to typed operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=3, max_length=500)
    run_id: str | None = None
    selected_record_id: str | None = None
    comparison_id: str | None = None
    allow_model: bool = False


class QueryStep(BaseModel):
    """One visible step in a validated investigation plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal[
        "diagnose_stop",
        "locate_final_claim",
        "verify_objective",
        "list_position_candidates",
        "compare_rendering",
    ]
    source: Literal["agent", "benchmark", "gateway"]
    detail: str


class AnswerClaim(BaseModel):
    """One answer claim with inspectable support."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    confidence: Literal["high", "medium", "low"]
    citations: tuple[str, ...]


class AskResponse(BaseModel):
    """A grounded answer whose plan and evidence remain inspectable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tier: Literal[
        "deterministic",
        "model_translated",
        "model_disabled",
        "unsupported",
    ]
    question: str
    scope_record_id: str | None = None
    plan: tuple[QueryStep, ...]
    answer: str
    claims: tuple[AnswerClaim, ...]
    citations: tuple[EvidenceCitation, ...]
    missing: tuple[str, ...] = ()
    model_cost_usd: float = 0
