export type WorldNodeData = {
  id: string;
  place: number;
  title: string;
  exits: string[];
  mobs: string[];
  objects: string[];
  visits: number;
  evidence: number[];
  first_seq: number;
  last_seq: number;
  state: "observed" | "candidate" | "current";
  confidence: string;
  method: string;
};

export type WorldEdgeData = {
  id: string;
  source: string;
  target: string;
  direction: string;
  traversals: number;
  evidence: number[];
};

export type WorldCandidateData = {
  node_id: string;
  title: string;
  supporting_exits: string[];
  conflicting_exits: string[];
  reason: string;
  evidence: number[];
};

export type WorldProjectionData = {
  nodes: WorldNodeData[];
  edges: WorldEdgeData[];
  current_title: string | null;
  current_confidence: string;
  candidates: string[];
  candidate_details: WorldCandidateData[];
  duplicate_titles: {
    title: string;
    node_ids: string[];
  }[];
  objective_beacons: {
    node_id: string;
    label: string;
    reason: string;
    evidence: number[];
  }[];
  parse_miss_rate: number;
  parse_misses: {
    sequence: number;
    trace_id: string | null;
    reason: string;
  }[];
  unknown_positions: number;
};

export const emptyWorld: WorldProjectionData = {
  nodes: [],
  edges: [],
  current_title: null,
  current_confidence: "unknown",
  candidates: [],
  candidate_details: [],
  duplicate_titles: [],
  objective_beacons: [],
  parse_miss_rate: 0,
  parse_misses: [],
  unknown_positions: 0,
};

export type AtlasProjectionData = {
  available: boolean;
  source_state: "available" | "unavailable";
  source_label: string;
  level: "overview" | "zone";
  selected_zone: number | null;
  room_count: number;
  edge_count: number;
  zone_count: number;
  duplicate_title_count: number;
  load_ms: number;
  memory_bytes: number;
  detail: string;
  zones: {
    id: string;
    zone: number;
    room_count: number;
    edge_count: number;
    duplicate_title_count: number;
  }[];
  nodes: {
    id: string;
    vnum: number;
    title: string;
    zone: number;
    exits: Record<string, number>;
  }[];
};
