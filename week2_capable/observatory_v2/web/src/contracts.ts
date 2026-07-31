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

export type Observed = { value: number | boolean | string };

export type WorldNode = {
  id: string;
  place: number;
  title: string;
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

export type Snapshot = {
  player_id: string;
  character: string;
  turn: number | null;
  latest_sequence: number;
  cost_usd: number;
  combat?: boolean;
  player_status: { fields: Record<string, Observed> };
  world: {
    nodes: WorldNode[];
    edges: WorldEdge[];
    current_title: string | null;
    current_confidence: string;
    objective_beacons?: Array<{
      node_id: string;
      label: string;
      reason: string;
      evidence: number[];
    }>;
  };
};
