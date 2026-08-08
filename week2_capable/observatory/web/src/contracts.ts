export type Player = { id: string; label: string };

export type Session = {
  id: string;
  player_id: string;
  character: string;
  gateway_session_id: string;
  state: string;
  control_state: string | null;
  control_available: boolean;
  capture_status: string;
  created_at: string;
  updated_at: string;
  ended_at: string | null;
  stop_mode: string | null;
  event_count: number;
  latest_seq: number;
  legacy: boolean;
  live: boolean;
  objective?: string | null;
  goal_count?: number;
  nudge_count?: number;
};

export type Catalog = {
  version: 1;
  players: Player[];
  sessions: Session[];
};

export type SessionEvidenceForm =
  | "wire"
  | "parsed"
  | "rendered"
  | "believed"
  | "truth";

export type SessionEvidenceRecord = {
  id: string;
  parent_id: string | null;
  source: "agent" | "gateway" | "benchmark";
  form: SessionEvidenceForm;
  kind: string;
  label: string;
  sequence: number;
  at: string;
  trace_id: string | null;
  iteration: number | null;
  turn: number | null;
  room_id: string | null;
  duration_ms: number;
  cost_usd: number;
  tokens: number;
  status: "complete" | "partial" | "failed" | "unknown";
  preview: string;
  fields: Record<string, unknown>;
  source_ref: string;
  capture_gaps: string[];
};

export type SessionDiagnostic = {
  id: string;
  kind: string;
  severity: "critical" | "warning" | "notice";
  state: "open" | "acknowledged" | "resolved";
  title: string;
  consequence: string;
  rule_version: string;
  threshold: string;
  at_record: string;
  evidence: string[];
  alternatives: string[];
  affected_conclusions: string[];
  resolution: string | null;
  related_occurrences: string[];
};

export type SessionCostPoint = {
  record_id: string;
  iteration: number | null;
  cost_usd: number;
  raw_response_cost_usd: number;
  pricing_source: "attempt_cost_curve" | "agent_response";
  fresh_input_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  output_tokens: number;
  context_tokens: number;
  progress: string;
};

export type SessionWireEvidence = {
  version: 1;
  record_id: string;
  source_ref: string;
  timestamp: number;
  direction: string;
  digest: string;
  bytes: number;
  redacted: boolean;
  content_base64: string;
  content_text: string;
};

export type SessionChangeSignal = {
  version: 1;
  session_id: string;
  latest_seq: number;
  agent_log_size: number;
  live: boolean;
};

export type SessionRecordFields = {
  version: 1;
  record_id: string;
  source_ref: string;
  kind: string;
  fields: Record<string, unknown>;
};

export type SessionRun = {
  id: string;
  label: string;
  journey: string;
  attempt: string;
  success: boolean;
  stop_reason: string;
  iterations: number;
  cost_usd: number;
  result_mode: string;
  lifecycle?: string;
  capture_status?: string;
  created_at?: string;
  ended_at?: string | null;
  duration_ms?: number | null;
  turns?: number;
  responses?: number;
  goal_epochs?: number;
};

export type SessionInvestigation = {
  version: number;
  source_kind: "runtime_session" | "experiment_sample";
  correlation: string;
  run: SessionRun;
  player_id: string;
  agent_session_id: string | null;
  gateway_session_id: string | null;
  objective: string | null;
  model: string | null;
  records: SessionEvidenceRecord[];
  diagnostics: SessionDiagnostic[];
  diagnostic_coverage: string[];
  lens: Record<
    SessionEvidenceForm,
    {
      state: "available" | "missing";
      title: string;
      text: string;
      citations: string[];
    }
  >;
  world: WorldProjection;
  cost: {
    total_usd: number;
    response_total_usd: number;
    raw_response_total_usd: number;
    reconciliation_delta_usd: number;
    complete: boolean;
    completeness_detail: string;
    fresh_input_tokens: number;
    cache_read_tokens: number;
    cache_write_tokens: number;
    output_tokens: number;
    points: SessionCostPoint[];
  };
  capture_gaps: string[];
};

export type SessionsLens =
  | "overview"
  | "flow"
  | "map"
  | "evidence"
  | "cost"
  | "diagnostics";

export type ExperimentFeature = {
  id: string;
  label: string;
  group:
    | "model"
    | "tools"
    | "rendering"
    | "memory"
    | "context"
    | "policy"
    | "capability";
  kind: "boolean" | "enum" | "integer" | "number" | "text";
  description: string;
  default: boolean | number | string;
  options: string[];
  minimum: number | null;
  maximum: number | null;
  source: string;
  execution_supported: boolean;
};

export type ExperimentScenario = {
  id: string;
  label: string;
  objective: string;
  success_predicate: string;
  starting_state: string;
  reset_strategy: string;
  reset_identity: string;
  execution_supported: boolean;
};

export type ExperimentCatalog = {
  registry: ExperimentFeature[];
  scenarios: ExperimentScenario[];
  execution: {
    available: boolean;
    state_store_available: boolean;
    max_spend_usd: number;
    paid_confirmation_required: boolean;
  };
};

export type ExperimentArm = {
  id: string;
  label: string;
  values: Record<string, boolean | number | string>;
};

export type ExperimentDefinition = {
  id: string;
  version: number;
  title: string;
  objective: string;
  success_predicate: string;
  journey: string;
  starting_state: string;
  reset_strategy: string;
  reset_identity: string;
  arms: ExperimentArm[];
  repetitions_per_arm: number;
  per_sample_spend_ceiling_usd: number;
  stop: {
    success_target: number;
    verified_predicate_required: boolean;
    max_iterations_per_sample: number;
    max_wall_seconds_per_sample: number;
    max_total_cost_usd: number;
    operator_stop_enabled: boolean;
  };
  effective_max_spend_usd: number;
  source: "imported_evidence" | "executable_definition";
  parent_definition_id: string | null;
  changed_feature: string | null;
};

export type ExperimentValidation = {
  valid: boolean;
  comparable: boolean;
  execution_available: boolean;
  paid_confirmation_required: boolean;
  issues: string[];
  checks: string[];
};

export type ExperimentCohort = {
  mode: string;
  samples: number;
  successes: number;
  cost_mean: number;
  cost_median: number;
  cost_stdev: number;
  calls_mean: number;
  calls_stdev: number;
  invalid_calls: number;
  corrective_calls: number;
  tools: Record<string, number>;
  attention: {
    fresh_tokens: number;
    cache_read_tokens: number;
    cache_write_tokens: number;
    output_tokens: number;
    result_chars: number;
    schema_tokens: number;
    movement_share: number;
  };
};

export type ExperimentSample = {
  run_id: string;
  mode: string;
  attempt: string;
  success: boolean;
  setup_failure: boolean;
  excluded: boolean;
  exclusion_reason: string | null;
  cost_usd: number;
  turns: number;
  calls: number;
};

export type ExperimentComparison = {
  id: string;
  title: string;
  journey: string;
  definition: ExperimentDefinition;
  registry: ExperimentFeature[];
  validation: ExperimentValidation;
  cohorts: ExperimentCohort[];
  samples: ExperimentSample[];
  lanes: Array<{
    mode: string;
    attempt: string;
    success: boolean;
    cost_usd: number;
    calls: number;
    milestones: Array<{
      index: number;
      kind: "observe" | "move" | "inspect" | "outcome" | "other";
      label: string;
      tool: string | null;
      argument: string | null;
    }>;
  }>;
  divergence: {
    index: number | null;
    summary: string;
    actions: Record<string, string>;
  };
  counterfactuals: Array<{
    mode: string;
    observations: number;
    bytes: number;
    estimated_tokens: number;
    delta_from_raw: number;
  }>;
  parser_counterfactuals: Array<{
    mode: string;
    frames: number;
    recorded_version: string;
    replayed_version: string;
    recorded_lines: number;
    recorded_typed: number;
    replayed_lines: number;
    replayed_typed: number;
    recorded_miss_rate: number;
    replayed_miss_rate: number;
    typed_delta: number;
  }>;
  findings: string[];
};

export type ExperimentJob = {
  id: string;
  request_id: string;
  player_profile: string;
  definition_id: string;
  definition: ExperimentDefinition;
  state: string;
  confirmed_max_spend_usd: number;
  spent_usd: number;
  current_sample: string | null;
  samples: Array<{
    id: string;
    arm_id: string;
    ordinal: number;
    state: string;
    run_id: string | null;
    cost_usd: number | null;
    turns: number | null;
    calls: number | null;
    detail: string;
    effective_config: Record<string, boolean | number | string>;
  }>;
};

export type Observed = {
  value: number | boolean | string;
  sequence: number;
  observed_at: number;
  confidence: string;
  method: string;
};

export type WorldRoomDescription = {
  text: string;
  evidence: number[];
};

export type WorldSighting = {
  name: string;
  count: number;
  first_seq: number;
  last_seq: number;
  evidence: number[];
};

export type WorldNode = {
  id: string;
  place: number;
  title: string;
  description: WorldRoomDescription | null;
  atlas?: {
    vnum: number;
    zone_id: number;
    zone_label: string;
    sector: string;
    atlas_digest: string;
    confidence: "high" | "medium";
    evidence: string[];
  } | null;
  exits: string[];
  mobs: string[];
  objects: string[];
  mob_sightings: WorldSighting[];
  object_sightings: WorldSighting[];
  visits: number;
  evidence: number[];
  first_seq: number;
  last_seq: number;
  state: "observed" | "candidate" | "current";
  confidence: string;
  method: string;
};

export type WorldEdge = {
  id: string;
  source: string;
  target: string;
  direction: string;
  traversals: number;
  evidence: number[];
};

export type WorldFrontier = {
  id: string;
  source: string;
  direction: string;
  evidence: number[];
};

export type WorldCandidate = {
  node_id: string;
  title: string;
  supporting_exits: string[];
  conflicting_exits: string[];
  reason: string;
  evidence: number[];
};

export type WorldProjection = {
  nodes: WorldNode[];
  edges: WorldEdge[];
  current_title: string | null;
  current_confidence: string;
  candidates: string[];
  candidate_details: WorldCandidate[];
  duplicate_titles: Array<{
    title: string;
    node_ids: string[];
  }>;
  objective_beacons: Array<{
    node_id: string;
    label: string;
    reason: string;
    evidence: number[];
  }>;
  frontier: WorldFrontier[];
  parse_miss_rate: number;
  parse_misses: Array<{
    sequence: number;
    trace_id: string | null;
    reason: string;
  }>;
  unknown_positions: number;
};

export type RoomEconomics = {
  node_id: string;
  response_count: number;
  cost_usd: number;
  first_response: number;
  last_response: number;
  evidence: string[];
};

export type LiveTimelineItem = {
  id: string;
  sequence: number;
  at: number;
  source: "agent" | "gateway";
  kind: string;
  label: string;
  cost_usd: number;
  tokens: number;
  trace_id: string | null;
  quiet_cohort: string | null;
};

export type LiveRoom = {
  id: string;
  place: number;
  title: string;
  exits: string[];
  first_sequence: number;
  last_sequence: number;
  visits: number;
  state: "observed" | "current";
  confidence: string;
};

export type LiveEconomicsPoint = {
  response: number;
  at: string;
  cost_usd: number;
  cumulative_cost_usd: number;
  context_tokens: number;
};

export type LiveUnattributedEconomics = {
  response_count: number;
  cost_usd: number;
  evidence: string[];
};

export type LiveMilestone = {
  kind: "level_up";
  sequence: number;
  at: number;
  previous: number;
  current: number;
  evidence: string;
};

export type LiveAgentExcerpt = {
  text: string;
  phase: "reasoning" | "plan" | "tool_call" | "completion";
  observed_at: string;
  line: number;
  evidence: string;
};

export type LiveObjectiveContext = {
  title: string;
  clue: string | null;
  source_kind: "benchmark" | "operator";
  revision: number;
  evidence: string;
};

export type LiveZoneContext = {
  zone_id: number;
  label: string;
  room_vnum: number;
  sector: string;
  form: "truth";
  confidence: "high" | "medium";
  reset_sequence: number;
  movement_sequences: number[];
  atlas_digest: string;
  evidence: string[];
};

export type LiveSuggestedAction = {
  kind: "route" | "continue_plan";
  label: string;
  instruction: string;
  reason: string;
  evidence: string[];
  expected_sequence: number;
};

export type LiveRecentPath = {
  edge_ids: string[];
  gateway_sequences: number[];
};

export type LiveCombatLine = {
  text: string;
  sequence: number;
  observed_at: number;
  confidence: string;
  method: string;
  evidence: string;
};

export type LiveCombatEpisode = {
  active: boolean;
  opponent: string | null;
  first_observed_turn: number | null;
  observed_exchanges: number;
  outcome: "victory" | "defeated" | "fled" | "ended" | "unresolved" | null;
  command_trace: string | null;
  lines: LiveCombatLine[];
  evidence: number[];
};

export type LiveFrictionDiagnostic = {
  kind: "confusion_loop" | "progress_stall" | null;
  repeated_command: string | null;
  repeated_count: number;
  distinct_places: number;
  iterations: number;
  new_places: number;
  window_iterations: number;
  iterations_since_new_place: number | null;
  threshold: string | null;
  evidence: number[];
};

export type LiveOperatorMessage = {
  action: "guide" | "revise";
  instruction: string;
  sent_at: string;
  applied_iteration: number | null;
};

export type Snapshot = {
  session_id: string;
  gateway_session_id: string;
  player_id: string;
  character: string;
  lifecycle: string;
  control_state: string | null;
  agent_turn_active: boolean;
  following_live: boolean;
  through_sequence: number;
  latest_sequence: number;
  selected_at: number | null;
  objective: string | null;
  objective_initial: LiveObjectiveContext | null;
  objective_context: LiveObjectiveContext | null;
  suggested_action: LiveSuggestedAction | null;
  recent_path: LiveRecentPath | null;
  agent_thought: LiveAgentExcerpt | null;
  agent_belief: LiveAgentExcerpt | null;
  model: string | null;
  tools: string[];
  turn: number | null;
  iteration: number;
  context_limit: number | null;
  current_room: string | null;
  zone: LiveZoneContext | null;
  position_confidence: string;
  position_method: string | null;
  combat: boolean;
  combat_episode: LiveCombatEpisode | null;
  friction: LiveFrictionDiagnostic;
  vitals: Record<string, number>;
  player_status: {
    fields: Record<string, Observed>;
    capture_gaps: string[];
  };
  cost_usd: number;
  current_turn_cost_usd: number;
  spend_cap_usd: number | null;
  spend_cap_scope: "session" | "turn" | null;
  economics: LiveEconomicsPoint[];
  room_economics: RoomEconomics[];
  unattributed_room_economics: LiveUnattributedEconomics | null;
  usage: Record<string, number>;
  milestones: LiveMilestone[];
  parse_miss_rate: number | null;
  rooms: LiveRoom[];
  world: WorldProjection;
  timeline: LiveTimelineItem[];
  operator_messages: LiveOperatorMessage[];
  capture_gaps: string[];
};

export function decodeSnapshot(value: unknown): Snapshot {
  if (!isRecord(value)) {
    throw new Error("live snapshot has an invalid shape");
  }
  const requiredStrings = [
    "session_id",
    "gateway_session_id",
    "player_id",
    "character",
    "lifecycle",
    "position_confidence",
  ] as const;
  const requiredNumbers = [
    "through_sequence",
    "latest_sequence",
    "iteration",
    "cost_usd",
    "current_turn_cost_usd",
  ] as const;
  const requiredArrays = [
    "tools",
    "economics",
    "room_economics",
    "milestones",
    "rooms",
    "timeline",
    "operator_messages",
    "capture_gaps",
  ] as const;
  const valid = requiredStrings.every((key) => typeof value[key] === "string")
    && requiredNumbers.every((key) => typeof value[key] === "number")
    && requiredArrays.every((key) => Array.isArray(value[key]))
    && typeof value.agent_turn_active === "boolean"
    && typeof value.following_live === "boolean"
    && typeof value.combat === "boolean"
    && isNullableNumber(value.selected_at)
    && isNullableNumber(value.turn)
    && isNullableNumber(value.context_limit)
    && isNullableNumber(value.spend_cap_usd)
    && isNullableNumber(value.parse_miss_rate)
    && isNullableString(value.control_state)
    && isNullableString(value.objective)
    && isNullableString(value.model)
    && isNullableString(value.current_room)
    && isNullableString(value.position_method)
    && isOptionalScope(value.spend_cap_scope)
    && isNullableRecord(value.objective_initial)
    && isNullableRecord(value.objective_context)
    && isNullableRecord(value.suggested_action)
    && isNullableRecord(value.recent_path)
    && isNullableRecord(value.agent_thought)
    && isNullableRecord(value.agent_belief)
    && isNullableRecord(value.zone)
    && isNullableRecord(value.combat_episode)
    && isFrictionDiagnostic(value.friction)
    && isNullableRecord(value.unattributed_room_economics)
    && isNumberRecord(value.vitals)
    && isNumberRecord(value.usage)
    && isPlayerStatus(value.player_status)
    && isWorldProjection(value.world);
  if (!valid) {
    throw new Error("live snapshot has an invalid shape");
  }
  return value as Snapshot;
}

function isFrictionDiagnostic(value: unknown): boolean {
  return isRecord(value)
    && (value.kind === null
      || value.kind === "confusion_loop"
      || value.kind === "progress_stall")
    && isNullableString(value.repeated_command)
    && typeof value.repeated_count === "number"
    && typeof value.distinct_places === "number"
    && typeof value.iterations === "number"
    && typeof value.new_places === "number"
    && typeof value.window_iterations === "number"
    && (value.iterations_since_new_place === null
      || typeof value.iterations_since_new_place === "number")
    && isNullableString(value.threshold)
    && Array.isArray(value.evidence);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableRecord(value: unknown): boolean {
  return value === null || isRecord(value);
}

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isNullableNumber(value: unknown): boolean {
  return value === null || typeof value === "number";
}

function isOptionalScope(value: unknown): boolean {
  return value === null || value === "session" || value === "turn";
}

function isNumberRecord(value: unknown): boolean {
  return isRecord(value)
    && Object.values(value).every((item) => typeof item === "number");
}

function isPlayerStatus(value: unknown): boolean {
  return isRecord(value)
    && isRecord(value.fields)
    && Array.isArray(value.capture_gaps)
    && Object.values(value.fields).every((item) => {
      return isRecord(item)
        && ["number", "boolean", "string"].includes(typeof item.value)
        && typeof item.sequence === "number"
        && typeof item.observed_at === "number"
        && typeof item.confidence === "string"
        && typeof item.method === "string";
    });
}

function isWorldProjection(value: unknown): boolean {
  return isRecord(value)
    && Array.isArray(value.nodes)
    && Array.isArray(value.edges)
    && Array.isArray(value.candidates)
    && Array.isArray(value.candidate_details)
    && Array.isArray(value.duplicate_titles)
    && Array.isArray(value.objective_beacons)
    && Array.isArray(value.frontier)
    && Array.isArray(value.parse_misses)
    && isNullableString(value.current_title)
    && typeof value.current_confidence === "string"
    && typeof value.parse_miss_rate === "number"
    && typeof value.unknown_positions === "number";
}

export type KnowledgeEvidence = {
  session_id: string;
  source_seq: number;
  wire_digest: string;
  parser_version: string;
  method: string;
  observed_at: number;
};

export type KnowledgeAssertion = {
  assertion_id: string;
  fact_id: string;
  subject: string;
  predicate: string;
  value: unknown;
  layer: "belief" | "parsed" | "learned" | "observer_truth";
  status: string;
  confidence: string;
  current: boolean;
  conflict_group: string | null;
  evidence: KnowledgeEvidence[];
};

export type KnowledgeMetric = {
  id: string;
  label: string;
  value: number;
  detail: string;
};

export type PlayerKnowledge = {
  version: 1;
  player_id: string;
  state: "ready" | "unavailable" | "incomplete";
  source: string;
  cdc_cursor: number;
  metrics: KnowledgeMetric[];
  assertions: KnowledgeAssertion[];
  capture_gaps: string[];
};
