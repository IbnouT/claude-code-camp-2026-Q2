"""Typed public contracts for observatory sources and investigations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceStatus(BaseModel):
    """One evidence source and its current availability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Literal["gateway", "agent", "benchmark", "knowledge", "world"]
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
    world: WorldProjection
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
    source: Literal[
        "agent",
        "gateway",
        "benchmark",
        "runtime",
        "experiments",
        "knowledge",
    ]
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
    mobs: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()
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


class WorldCandidate(BaseModel):
    """One unresolved place candidate with its spatial evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    title: str
    supporting_exits: tuple[str, ...]
    conflicting_exits: tuple[str, ...]
    reason: str
    evidence: tuple[int, ...]


class WorldDuplicateTitle(BaseModel):
    """Distinct spatial identities that share one rendered title."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    node_ids: tuple[str, ...]


class WorldParseMiss(BaseModel):
    """One retained parser miss that weakens spatial certainty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    trace_id: str | None
    reason: str


class WorldObjectiveBeacon(BaseModel):
    """One objective location supported by a retained entity sighting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    label: str
    reason: str
    evidence: tuple[int, ...]


class WorldProjection(BaseModel):
    """The evidence-backed journey graph and its unresolved current state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[WorldNode, ...]
    edges: tuple[WorldEdge, ...]
    current_title: str | None
    current_confidence: str
    candidates: tuple[str, ...]
    candidate_details: tuple[WorldCandidate, ...] = ()
    duplicate_titles: tuple[WorldDuplicateTitle, ...] = ()
    objective_beacons: tuple[WorldObjectiveBeacon, ...] = ()
    parse_miss_rate: float
    parse_misses: tuple[WorldParseMiss, ...] = ()
    unknown_positions: int


class AtlasNode(BaseModel):
    """One observer-owned world room for a selected atlas zone."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    vnum: int
    title: str
    zone: int
    exits: dict[str, int]


class AtlasZone(BaseModel):
    """One level-of-detail cluster in the observer world atlas."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    zone: int
    room_count: int
    edge_count: int
    duplicate_title_count: int


class AtlasProjection(BaseModel):
    """A measured, observer-only world atlas response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    source_state: Literal["available", "unavailable"]
    source_label: str
    level: Literal["overview", "zone"]
    selected_zone: int | None
    room_count: int
    edge_count: int
    zone_count: int
    duplicate_title_count: int
    load_ms: float
    zones: tuple[AtlasZone, ...] = ()
    nodes: tuple[AtlasNode, ...] = ()
    memory_bytes: int
    detail: str


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


class ExperimentFeature(BaseModel):
    """One typed configuration dimension rendered by the workbench."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    group: Literal["model", "tools", "rendering", "memory", "context", "policy"]
    kind: Literal["boolean", "enum", "integer", "number", "text"]
    description: str
    default: bool | int | float | str
    options: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    source: str


class ExperimentArmDefinition(BaseModel):
    """One immutable arm and its effective registered configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    values: dict[str, bool | int | float | str]


class ExperimentStopCriteria(BaseModel):
    """The six independent boundaries that can stop experiment execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    success_target: int
    verified_predicate_required: bool
    max_iterations_per_sample: int
    max_wall_seconds_per_sample: int
    max_total_cost_usd: float
    operator_stop_enabled: bool


class ExperimentDefinition(BaseModel):
    """A versioned, reproducible controlled-test definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: int
    title: str
    objective: str
    success_predicate: str
    journey: str
    starting_state: str
    reset_strategy: str
    reset_identity: str
    arms: tuple[ExperimentArmDefinition, ...]
    repetitions_per_arm: int
    per_sample_spend_ceiling_usd: float
    stop: ExperimentStopCriteria
    effective_max_spend_usd: float
    source: Literal["imported_evidence", "executable_definition"]
    parent_definition_id: str | None = None
    changed_feature: str | None = None


class ExperimentValidation(BaseModel):
    """Evidence that a definition is safe and comparable before execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    comparable: bool
    execution_available: bool
    paid_confirmation_required: bool = True
    issues: tuple[str, ...]
    checks: tuple[str, ...]


class ExperimentRunRequest(BaseModel):
    """An explicit paid-execution confirmation for one validated definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1, max_length=160)
    definition: ExperimentDefinition
    player_profile: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    confirmed: bool
    confirmed_max_spend_usd: float = Field(gt=0)


class ExperimentValidateRequest(BaseModel):
    """A candidate definition submitted for deterministic preflight."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    definition: ExperimentDefinition


class ExperimentForkRequest(BaseModel):
    """A one-variable fork of an immutable experiment definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    definition: ExperimentDefinition
    arm_id: str = Field(min_length=1, max_length=80)
    feature_id: str = Field(min_length=1, max_length=160)
    value: bool | int | float | str


class ComparisonSample(BaseModel):
    """One cohort member with a stable route back to Sessions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    mode: Literal["raw", "minimal", "full"]
    attempt: str
    success: bool
    setup_failure: bool
    excluded: bool
    exclusion_reason: str | None
    cost_usd: float
    turns: int
    calls: int


class RunComparison(BaseModel):
    """A complete J1 cohort, alignment, and deterministic replay comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    journey: str
    definition: ExperimentDefinition
    registry: tuple[ExperimentFeature, ...]
    validation: ExperimentValidation
    cohorts: tuple[ComparisonCohort, ...]
    samples: tuple[ComparisonSample, ...]
    lanes: tuple[ComparisonLane, ...]
    divergence: FirstDivergence
    counterfactuals: tuple[CounterfactualProjection, ...]
    parser_counterfactuals: tuple[ParserCounterfactual, ...]
    findings: tuple[str, ...]


class QueryScope(BaseModel):
    """The complete evidence boundary for one investigation query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    space: Literal["live", "sessions", "experiments", "knowledge"]
    player_id: str | None = None
    live_session_id: str | None = None
    run_id: str | None = None
    through_sequence: int | None = Field(default=None, ge=0)
    selected_record_id: str | None = None
    comparison_id: str | None = None
    subject_id: str | None = None
    lens: str | None = None


class QueryFilter(BaseModel):
    """One allowlisted field predicate in a typed Observatory query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal[
        "source",
        "kind",
        "room",
        "trace_id",
        "state",
        "arm_id",
        "cost_usd",
        "confidence",
    ]
    operator: Literal["eq", "contains", "gte", "lte"]
    value: str | int | float | bool


class ObservatoryQuery(BaseModel):
    """A versioned, read-only query accepted by the evidence engine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    operation: Literal[
        "diagnose_stop",
        "summarize_live",
        "list_position_candidates",
        "compare_rendering",
        "list_experiment_samples",
        "search_evidence",
        "search_knowledge",
    ]
    scope: QueryScope
    filters: tuple[QueryFilter, ...] = ()
    order: Literal["causal", "chronological", "cost_desc"] = "causal"
    limit: int = Field(default=25, ge=1, le=100)


class AskRequest(BaseModel):
    """One question or exact query constrained to an explicit evidence scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=3, max_length=500)
    scope: QueryScope
    query: ObservatoryQuery | None = None
    allow_model: bool = False
    allow_summary: bool = False


class QueryStep(BaseModel):
    """One visible step in a validated investigation plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal[
        "diagnose_stop",
        "summarize_live",
        "locate_final_claim",
        "verify_objective",
        "list_position_candidates",
        "compare_rendering",
        "list_experiment_samples",
        "search_evidence",
        "search_knowledge",
        "validate_scope",
    ]
    source: Literal[
        "agent",
        "benchmark",
        "gateway",
        "runtime",
        "experiments",
        "knowledge",
    ]
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
        "model_summarized",
        "model_disabled",
        "unsupported",
    ]
    question: str
    query: ObservatoryQuery | None = None
    scope_record_id: str | None = None
    plan: tuple[QueryStep, ...]
    answer: str
    claims: tuple[AnswerClaim, ...]
    citations: tuple[EvidenceCitation, ...]
    missing: tuple[str, ...] = ()
    hypotheses: tuple[str, ...] = ()
    model_cost_usd: float = 0
    model_input_tokens: int = 0
    model_output_tokens: int = 0
    model_summary: str | None = None
    model_summary_citations: tuple[str, ...] = ()
