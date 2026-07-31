import type { EventEnvelope } from "./contracts";
import type { WorldProjectionData } from "./worldContracts";

export type RuntimePlayer = {
  id: string;
  label: string;
};

export type RuntimeSession = {
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

export type RuntimeCatalog = {
  version: 1;
  players: RuntimePlayer[];
  sessions: RuntimeSession[];
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

export type LiveObservedValue = {
  value: number | boolean | string;
  sequence: number;
  observed_at: number;
  confidence: string;
  method: string;
};

export type LivePlayerStatus = {
  fields: Record<string, LiveObservedValue>;
  capture_gaps: string[];
};

export type LiveEconomicsPoint = {
  response: number;
  at: string;
  cost_usd: number;
  cumulative_cost_usd: number;
  context_tokens: number;
};

export type LiveRoomEconomics = {
  node_id: string;
  response_count: number;
  cost_usd: number;
  first_response: number;
  last_response: number;
  evidence: string[];
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

export type LiveSnapshot = {
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
  vitals: Record<string, number>;
  player_status: LivePlayerStatus;
  cost_usd: number;
  current_turn_cost_usd: number;
  spend_cap_usd: number | null;
  spend_cap_scope: "session" | "turn" | null;
  economics: LiveEconomicsPoint[];
  room_economics: LiveRoomEconomics[];
  unattributed_room_economics: LiveUnattributedEconomics | null;
  usage: Record<string, number>;
  milestones: LiveMilestone[];
  parse_miss_rate: number | null;
  rooms: LiveRoom[];
  world: WorldProjectionData;
  timeline: LiveTimelineItem[];
  capture_gaps: string[];
};

export type LiveConnection =
  | "discovering"
  | "waiting"
  | "streaming"
  | "paused"
  | "replaying"
  | "ended"
  | "unavailable";

export type LiveSessionState = {
  connection: LiveConnection;
  error: string | null;
  events: EventEnvelope[];
  latestSequence: number;
  selectedSequence: number;
  followingLive: boolean;
  gaps: { first: number; last: number }[];
  unknownKinds: string[];
  snapshot: LiveSnapshot | null;
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function decodeCatalog(value: unknown): RuntimeCatalog {
  if (!isObject(value) || value.version !== 1) {
    throw new Error("session catalog has an unsupported version");
  }
  if (!Array.isArray(value.players) || !Array.isArray(value.sessions)) {
    throw new Error("session catalog is incomplete");
  }
  const players = value.players.map((item) => {
    if (!isObject(item) || typeof item.id !== "string" || typeof item.label !== "string") {
      throw new Error("session catalog contains an invalid player");
    }
    return { id: item.id, label: item.label };
  });
  const sessions = value.sessions.map((item) => {
    if (
      !isObject(item)
      || typeof item.id !== "string"
      || typeof item.player_id !== "string"
      || typeof item.character !== "string"
      || typeof item.gateway_session_id !== "string"
      || typeof item.state !== "string"
      || typeof item.control_available !== "boolean"
      || typeof item.capture_status !== "string"
      || typeof item.event_count !== "number"
      || typeof item.latest_seq !== "number"
      || typeof item.legacy !== "boolean"
      || typeof item.live !== "boolean"
    ) {
      throw new Error("session catalog contains an invalid session");
    }
    return item as RuntimeSession;
  });
  return { version: 1, players, sessions };
}

export function decodeLiveSnapshot(value: unknown): LiveSnapshot {
  if (
    !isObject(value)
    || typeof value.session_id !== "string"
    || typeof value.gateway_session_id !== "string"
    || typeof value.player_id !== "string"
    || typeof value.latest_sequence !== "number"
    || typeof value.through_sequence !== "number"
    || !Array.isArray(value.timeline)
    || !Array.isArray(value.rooms)
    || !Array.isArray(value.capture_gaps)
  ) {
    throw new Error("live snapshot has an invalid shape");
  }
  return value as LiveSnapshot;
}
