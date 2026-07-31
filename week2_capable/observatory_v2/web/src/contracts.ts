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
};

export type Catalog = {
  version: 1;
  players: Player[];
  sessions: Session[];
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
  phase: "reasoning" | "plan" | "tool_call";
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

export type Snapshot = {
  session_id: string;
  gateway_session_id: string;
  player_id: string;
  character: string;
  lifecycle: string;
  control_state: string | null;
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
    "capture_gaps",
  ] as const;
  const valid = requiredStrings.every((key) => typeof value[key] === "string")
    && requiredNumbers.every((key) => typeof value[key] === "number")
    && requiredArrays.every((key) => Array.isArray(value[key]))
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
