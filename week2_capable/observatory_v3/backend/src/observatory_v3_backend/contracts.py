"""Typed public contracts for observatory sources and investigations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .knowledge_contracts import PlayerKnowledge

SourceId = Literal["gateway", "agent", "benchmark", "knowledge", "world"]
QuerySpace = Literal["live", "sessions", "experiments", "knowledge"]
QueryOperation = Literal[
    "diagnose_stop",
    "summarize_live",
    "list_position_candidates",
    "compare_rendering",
    "list_experiment_samples",
    "search_evidence",
    "search_knowledge",
]
QueryStepOperation = Literal[
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
QuerySource = Literal[
    "agent",
    "benchmark",
    "gateway",
    "runtime",
    "experiments",
    "knowledge",
]
AnswerTier = Literal[
    "deterministic",
    "model_translated",
    "model_summarized",
    "model_disabled",
    "unsupported",
]
EvidenceFormKind = Literal["wire", "parsed", "rendered", "believed", "truth"]
EvidenceStatus = Literal["complete", "partial", "failed", "unknown"]
DiagnosticKind = Literal[
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
DiagnosticSeverity = Literal["critical", "warning", "notice"]
PricingSource = Literal["attempt_cost_curve", "agent_response"]


class SourceStatus(BaseModel):
    """One evidence source and its current availability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: SourceId
    label: str
    state: Literal["ready", "unavailable", "disabled"]
    detail: str
    contract_digest: str | None = None


class LiveVoiceCapability(BaseModel):
    """Availability of cost-bearing speech for the selected Live thought."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    detail: str
    endpoint_template: str | None = None
    max_characters: int = 400


class ObservatoryCapabilities(BaseModel):
    """The exact sources and features available to this installation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = 1
    sources: tuple[SourceStatus, ...]
    features: tuple[str, ...]
    voice: LiveVoiceCapability


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
    quiet_cohort: str | None = None


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


class LiveObservedValue(BaseModel):
    """One player-state value and the observation that supports it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: int | bool | str
    sequence: int
    observed_at: float
    confidence: str
    method: str


class LivePlayerStatus(BaseModel):
    """Observed player state at the selected prefix, without defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fields: dict[str, LiveObservedValue]
    capture_gaps: tuple[str, ...]


class LiveEconomicsPoint(BaseModel):
    """One retained model response in the selected Live prefix."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    response: int
    at: str
    cost_usd: float
    cumulative_cost_usd: float
    context_tokens: int


class LiveRoomEconomics(BaseModel):
    """Model-response cost attributed to one observed room."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    response_count: int
    cost_usd: float
    first_response: int
    last_response: int
    evidence: tuple[str, ...]


class LiveUnattributedEconomics(BaseModel):
    """Model-response cost without a safe room correlation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    response_count: int
    cost_usd: float
    evidence: tuple[str, ...]


class LiveMilestone(BaseModel):
    """One evidence-backed player progression transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["level_up"]
    sequence: int
    at: float
    previous: int
    current: int
    evidence: str


class LiveAgentExcerpt(BaseModel):
    """One retained agent statement with its exact log provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    phase: Literal["reasoning", "plan", "tool_call"]
    observed_at: str
    line: int
    evidence: str


class LiveObjectiveContext(BaseModel):
    """Structured authored objective metadata retained by the agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    clue: str | None
    source_kind: Literal["benchmark", "operator"]
    revision: int
    evidence: str


class LiveZoneContext(BaseModel):
    """Observer-truth zone correlation for the selected current room."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    zone_id: int
    label: str
    room_vnum: int
    sector: str
    form: Literal["truth"]
    confidence: Literal["high", "medium"]
    reset_sequence: int
    movement_sequences: tuple[int, ...]
    atlas_digest: str
    evidence: tuple[str, ...]


class LiveSuggestedAction(BaseModel):
    """One previewable control grounded in retained route or intent evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["route", "continue_plan"]
    label: str
    instruction: str
    reason: str
    evidence: tuple[str, ...]
    expected_sequence: int


class LiveRecentPath(BaseModel):
    """Latest contiguous retained transition chain ending at current room."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_ids: tuple[str, ...]
    gateway_sequences: tuple[int, ...]


class LiveCombatLine(BaseModel):
    """One parsed combat line linked to retained gateway evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    sequence: int
    observed_at: float
    confidence: str
    method: str
    evidence: str


class LiveCombatEpisode(BaseModel):
    """One command-and-response combat episode in the selected prefix."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    active: bool
    opponent: str | None
    first_observed_turn: int | None
    observed_exchanges: int
    outcome: (
        Literal[
            "victory",
            "defeated",
            "fled",
            "ended",
            "unresolved",
        ]
        | None
    )
    command_trace: str | None
    lines: tuple[LiveCombatLine, ...]
    evidence: tuple[int, ...]


class LiveFrictionDiagnostic(BaseModel):
    """Prefix-local navigation friction using the recorded-session rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["confusion_loop", "progress_stall"] | None
    repeated_command: str | None
    repeated_count: int
    distinct_places: int
    iterations: int
    new_places: int
    window_iterations: int
    iterations_since_new_place: int | None
    threshold: str | None
    evidence: tuple[int, ...]


class LiveOperatorMessage(BaseModel):
    """One retained operator message at the selected Live prefix."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["guide", "revise"]
    instruction: str
    sent_at: str
    applied_iteration: int | None


class LiveJourneySnapshot(BaseModel):
    """One deterministic Live projection at an exact gateway sequence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    gateway_session_id: str
    player_id: str
    character: str
    lifecycle: str
    control_state: str | None
    agent_turn_active: bool
    following_live: bool
    through_sequence: int
    latest_sequence: int
    selected_at: float | None
    objective: str | None
    objective_initial: LiveObjectiveContext | None
    objective_context: LiveObjectiveContext | None
    suggested_action: LiveSuggestedAction | None
    recent_path: LiveRecentPath | None
    agent_thought: LiveAgentExcerpt | None
    agent_belief: LiveAgentExcerpt | None
    model: str | None
    tools: tuple[str, ...]
    turn: int | None
    iteration: int
    context_limit: int | None
    current_room: str | None
    zone: LiveZoneContext | None
    position_confidence: str
    position_method: str | None
    combat: bool
    combat_episode: LiveCombatEpisode | None
    friction: LiveFrictionDiagnostic
    vitals: dict[str, int]
    player_status: LivePlayerStatus
    cost_usd: float
    current_turn_cost_usd: float
    spend_cap_usd: float | None
    spend_cap_scope: Literal["session", "turn"] | None
    economics: tuple[LiveEconomicsPoint, ...]
    room_economics: tuple[LiveRoomEconomics, ...]
    unattributed_room_economics: LiveUnattributedEconomics | None
    usage: dict[str, int]
    milestones: tuple[LiveMilestone, ...]
    parse_miss_rate: float | None
    rooms: tuple[LiveRoom, ...]
    world: WorldProjection
    timeline: tuple[LiveTimelineItem, ...]
    operator_messages: tuple[LiveOperatorMessage, ...]
    capture_gaps: tuple[str, ...]


class LiveControlRequest(BaseModel):
    """One optimistic authenticated control request for a live session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=8, max_length=128)
    action: Literal["guide", "revise", "pause", "resume", "stop"]
    instruction: str | None = Field(default=None, max_length=4_000)
    expected_sequence: int = Field(ge=0)


class LiveVoiceRequest(BaseModel):
    """One explicit request to voice the thought at an exact Live prefix."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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


class WorldRoomDescription(BaseModel):
    """Latest retained room description with its observation evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    evidence: tuple[int, ...]


class WorldSighting(BaseModel):
    """Repeated sightings of one named entity in one inferred place."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    count: int
    first_seq: int
    last_seq: int
    evidence: tuple[int, ...]


class WorldAtlasRoomContext(BaseModel):
    """Verified observer-truth correlation for one learned-world node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    vnum: int
    zone_id: int
    zone_label: str
    sector: str
    atlas_digest: str
    confidence: Literal["high", "medium"]
    evidence: tuple[str, ...]


class WorldNode(BaseModel):
    """One distinct inferred place, never just a room title."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    place: int
    title: str
    description: WorldRoomDescription | None = None
    atlas: WorldAtlasRoomContext | None = None
    exits: tuple[str, ...]
    mobs: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()
    mob_sightings: tuple[WorldSighting, ...] = ()
    object_sightings: tuple[WorldSighting, ...] = ()
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


class WorldFrontier(BaseModel):
    """One observed exit without a retained traversal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source: str
    direction: str
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
    frontier: tuple[WorldFrontier, ...] = ()
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
    sector: str
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
    form: EvidenceFormKind
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
    status: EvidenceStatus = "unknown"
    preview: str
    fields: dict[str, Any] = Field(default_factory=dict)
    source_ref: str
    capture_gaps: tuple[str, ...] = ()


class SessionDiagnostic(BaseModel):
    """One versioned diagnostic that explains its own evidence boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: DiagnosticKind
    severity: DiagnosticSeverity
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
    pricing_source: PricingSource
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
    diagnostic_coverage: tuple[DiagnosticKind, ...]
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
    gateway_session_id: str | None
    label: str
    journey: str
    attempt: str
    success: bool
    stop_reason: str
    iterations: int
    cost_usd: float
    result_mode: str


class RuntimeSessionSummary(BaseModel):
    """One launcher run summarized without experiment semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    journey: str = "Session"
    attempt: str
    success: bool
    stop_reason: str
    iterations: int
    cost_usd: float
    result_mode: str = "runtime"
    lifecycle: str
    capture_status: str
    created_at: str
    ended_at: str | None
    duration_ms: float | None
    turns: int
    responses: int
    goal_epochs: int


class RuntimeSessionInvestigation(BaseModel):
    """One universal launcher session projected into navigable evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = 2
    source_kind: Literal["runtime_session"] = "runtime_session"
    correlation: str
    run: RuntimeSessionSummary
    player_id: str
    agent_session_id: str
    gateway_session_id: str
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


class RuntimeSessionWireEvidence(BaseModel):
    """One exact integrity-checked wire body loaded by explicit drill-down."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = 1
    record_id: str
    source_ref: str
    timestamp: float
    direction: str
    digest: str
    bytes: int
    redacted: bool
    content_base64: str
    content_text: str


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
    run_ids: tuple[str, ...] = ()


class DiagnosticHistory(BaseModel):
    """Diagnostic prevalence across every readable benchmark run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    player_id: str | None = None
    total_runs: int
    successful_runs: int
    failed_runs: int
    items: tuple[DiagnosticHistoryItem, ...]


class InvestigatorAnnotation(BaseModel):
    """Investigator-authored context that never mutates source evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=120)
    target_id: str = Field(min_length=1, max_length=200)
    bookmark: bool = False
    text: str = Field(min_length=1, max_length=2_000)
    created_at: str


class IncidentExportRequest(BaseModel):
    """Selection and local annotations included in a portable capsule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=160)
    selected_record_id: str = Field(min_length=1, max_length=200)
    diagnostic_id: str | None = Field(default=None, max_length=160)
    lens: Literal["story", "sequence", "evidence", "cost", "diagnostics"]
    annotations: tuple[InvestigatorAnnotation, ...] = ()


class IncidentSelection(BaseModel):
    """The exact investigation focus restored when a capsule opens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_record_id: str
    diagnostic_id: str | None
    lens: Literal["story", "sequence", "evidence", "cost", "diagnostics"]


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
    player_id: str
    investigation: RecordedSessionInvestigation
    knowledge: PlayerKnowledge
    history: DiagnosticHistory
    selection: IncidentSelection
    annotations: tuple[InvestigatorAnnotation, ...]
    redaction: RedactionReport


class IncidentCapsule(BaseModel):
    """Versioned incident envelope with deterministic integrity digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["boukensha.observatory.incident"] = "boukensha.observatory.incident"
    version: Literal[2] = 2
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
    execution_supported: bool


class ExperimentScenario(BaseModel):
    """One resettable, independently judged experiment scenario."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    objective: str
    success_predicate: str
    starting_state: str
    reset_strategy: str
    reset_identity: str
    execution_supported: bool


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

    space: QuerySpace
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
    operation: QueryOperation
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

    operation: QueryStepOperation
    source: QuerySource
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

    tier: AnswerTier
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
