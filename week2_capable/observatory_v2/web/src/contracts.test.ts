import { describe, expect, it } from "vitest";
import {
  decodeSnapshot,
  type Snapshot,
} from "./contracts";

const snapshot = {
  session_id: "session-1",
  gateway_session_id: "gateway-1",
  player_id: "poucet",
  character: "Poucet",
  lifecycle: "running",
  control_state: "running",
  following_live: true,
  through_sequence: 12,
  latest_sequence: 12,
  selected_at: 1_753_990_000,
  objective: "Explore",
  objective_initial: null,
  objective_context: null,
  suggested_action: null,
  recent_path: null,
  agent_thought: null,
  agent_belief: null,
  model: "fixture-model",
  tools: ["move"],
  turn: 3,
  iteration: 3,
  context_limit: 200_000,
  current_room: "A Nexus",
  zone: null,
  position_confidence: "tracked",
  position_method: "room_observation",
  combat: false,
  combat_episode: null,
  friction: {
    kind: null,
    repeated_command: null,
    repeated_count: 0,
    distinct_places: 0,
    iterations: 0,
    new_places: 0,
    window_iterations: 0,
    iterations_since_new_place: null,
    threshold: null,
    evidence: [],
  },
  vitals: { hit: 41 },
  player_status: {
    fields: {
      hit: {
        value: 41,
        sequence: 12,
        observed_at: 1_753_990_000,
        confidence: "high",
        method: "score",
      },
    },
    capture_gaps: [],
  },
  cost_usd: 0.118,
  current_turn_cost_usd: 0.0025,
  spend_cap_usd: 0.5,
  spend_cap_scope: "session",
  economics: [],
  room_economics: [],
  unattributed_room_economics: null,
  usage: {
    fresh_input: 100,
    cache_read: 20,
    cache_write: 5,
    output: 10,
  },
  milestones: [],
  parse_miss_rate: 0,
  rooms: [],
  world: {
    nodes: [],
    edges: [],
    current_title: "A Nexus",
    current_confidence: "tracked",
    candidates: [],
    candidate_details: [],
    duplicate_titles: [],
    objective_beacons: [],
    frontier: [],
    parse_miss_rate: 0,
    parse_misses: [],
    unknown_positions: 0,
  },
  timeline: [],
  capture_gaps: [],
} satisfies Snapshot;

describe("decodeSnapshot", () => {
  it("accepts the complete retained LiveJourneySnapshot shape", () => {
    expect(decodeSnapshot(snapshot)).toEqual(snapshot);
  });

  it("rejects a snapshot that omits a newly carried collection", () => {
    const { economics: _economics, ...incomplete } = snapshot;
    expect(() => decodeSnapshot(incomplete)).toThrow(
      "live snapshot has an invalid shape",
    );
  });

  it("rejects player status without observation provenance", () => {
    const invalid = {
      ...snapshot,
      player_status: {
        fields: { hit: { value: 41 } },
        capture_gaps: [],
      },
    };
    expect(() => decodeSnapshot(invalid)).toThrow(
      "live snapshot has an invalid shape",
    );
  });
});
