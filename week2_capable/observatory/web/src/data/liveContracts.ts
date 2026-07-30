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
  model: string | null;
  tools: string[];
  iteration: number;
  current_room: string | null;
  position_confidence: string;
  position_method: string | null;
  combat: boolean;
  vitals: Record<string, number>;
  cost_usd: number;
  usage: Record<string, number>;
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
