import type { Page } from "@playwright/test";

const sessionId = "session-live-fidelity";
const gatewaySessionId = "gateway-live-fidelity";
const playerId = "poucet";

export async function mockLiveFidelity(page: Page) {
  await page.route("**/api/sessions", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 1,
        players: [{ id: playerId, label: "poucet" }],
        sessions: [{
          id: sessionId,
          player_id: playerId,
          character: "poucet",
          gateway_session_id: gatewaySessionId,
          state: "running",
          control_state: "running",
          control_available: true,
          capture_status: "complete",
          created_at: "2026-07-30T08:00:00Z",
          updated_at: "2026-07-30T08:08:00Z",
          ended_at: null,
          event_count: 47,
          latest_seq: 47,
          legacy: false,
          live: true,
        }],
      }),
    });
  });
  await page.route("**/api/sessions/*/replay?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: events()
        .map((event) => `data: ${JSON.stringify(event)}\n\n`)
        .join(""),
    });
  });
  await page.route("**/api/sessions/*/events?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: "",
    });
  });
  await page.route("**/api/sessions/*/snapshot*", async (route) => {
    const requested = Number(new URL(route.request().url()).searchParams.get("through"));
    const through = Number.isInteger(requested) && requested > 0
      ? Math.min(requested, 47)
      : 47;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(snapshot(through)),
    });
  });
}

function events() {
  const notable = new Map<number, [string, Record<string, unknown>]>([
    [1, ["observation", {
      kind: "player_state",
      label: "Surveyed the Temple exits",
    }]],
    [6, ["agent_step", {
      label: "Reviewed the learned route",
    }]],
    [12, ["position", {
      place: 3001,
      title: "Temple Square",
      confidence: "high",
      method: "room-id",
    }]],
    [17, ["agent_step", {
      label: "Checked the objective route",
    }]],
    [23, ["level_up", {
      level: 4,
      label: "LEVEL UP: now level 4",
    }]],
    [28, ["agent_step", {
      label: "Moved toward the eastern alley",
    }]],
    [34, ["combat", {
      target: "a large kobold",
      label: "You hit the kobold hard. (14)",
    }]],
    [37, ["combat", {
      target: "a large kobold",
      label: "The kobold's claw rakes you. (-6)",
    }]],
    [38, ["combat", {
      target: "a large kobold",
      label: "You land a critical slash! (23)",
    }]],
    [44, ["combat", {
      target: "a large kobold",
      label: "You parry the kobold's lunge.",
    }]],
  ]);
  return Array.from({ length: 47 }, (_, index) => {
    const seq = index + 1;
    const [kind, data] = notable.get(seq) ?? ["wire", {
      direction: "inbound",
    }];
    return {
      seq,
      session: gatewaySessionId,
      at: 1_800_000_000 + seq,
      kind,
      trace_id: `trace-live-${seq}`,
      data,
    };
  });
}

function snapshot(through: number) {
  const visibleRooms = rooms.filter((room) => room.first_seq <= through);
  const current = visibleRooms.reduce(
    (latest, room) => room.first_seq > latest.first_seq ? room : latest,
    visibleRooms[0] ?? rooms[0],
  );
  const visibleEvents = events().filter((event) => event.seq <= through);
  const combatEvents = visibleEvents.filter((event) => event.kind === "combat");
  const quietCohorts = new Map<number, string>([
    [1, "quiet-1"],
    [6, "quiet-2"],
    [17, "quiet-3"],
    [28, "quiet-4"],
    [37, "quiet-5"],
    [38, "quiet-5"],
  ]);
  const timeline = visibleEvents
    .filter((event) => !["wire", "parse_metric", "unparsed"].includes(event.kind))
    .map((event) => ({
      id: `${gatewaySessionId}-${event.seq}`,
      sequence: event.seq,
      at: event.at,
      source: event.kind === "agent_step" ? "agent" : "gateway",
      kind: event.kind,
      label: String(event.data.label ?? event.data.title ?? `Agent iteration ${event.seq}`),
      cost_usd: event.kind === "agent_step" ? 0.0025 : 0,
      tokens: event.kind === "agent_step" ? 274 : 0,
      trace_id: event.trace_id,
      quiet_cohort: quietCohorts.get(event.seq) ?? null,
    }));
  return {
    session_id: sessionId,
    gateway_session_id: gatewaySessionId,
    player_id: playerId,
    character: "poucet",
    lifecycle: "running",
    control_state: "running",
    following_live: through === 47,
    through_sequence: through,
    latest_sequence: 47,
    selected_at: 1_800_000_000 + through,
    objective: "Find & kill the Massive Minotaur",
    objective_initial: {
      title: "Find & kill the Massive Minotaur",
      clue: "north of the Temple · newbie area",
      source_kind: "benchmark",
      revision: 1,
      evidence: "agent log line 1",
    },
    objective_context: {
      title: "Find & kill the Massive Minotaur",
      clue: "north of the Temple · newbie area",
      source_kind: "benchmark",
      revision: 1,
      evidence: "agent log line 1",
    },
    suggested_action: through < 47 ? null : {
      kind: "route",
      label: "Head to the lair",
      instruction: "Follow the learned route toward the lair: east.",
      reason: "A retained objective sighting is one learned transition away.",
      evidence: [
        "objective beacon seq 47",
        "gateway transition seq 47",
      ],
      expected_sequence: through,
    },
    recent_path: through < 47 ? null : {
      edge_ids: ["edge-8", "edge-11"],
      gateway_sequences: [26, 47],
    },
    agent_thought: through >= 43 ? {
      text: "A kobold blocks the alley east. I'll fight through: the minotaur lair should be past Back Street.",
      phase: "reasoning",
      observed_at: new Date(1_800_000_043 * 1_000).toISOString(),
      line: 43,
      evidence: "agent log line 43",
    } : null,
    agent_belief: through >= 43 ? {
      text: "Moving east",
      phase: "tool_call",
      observed_at: new Date(1_800_000_043 * 1_000).toISOString(),
      line: 44,
      evidence: "agent log line 44",
    } : null,
    model: "claude-haiku-4-5",
    tools: ["look", "move", "attack", "flee"],
    turn: through,
    iteration: through,
    context_limit: 200_000,
    current_room: current.title,
    zone: {
      zone_id: 30,
      label: "Midgaard",
      room_vnum: current.place,
      sector: "city",
      form: "truth",
      confidence: through <= 1 ? "high" : "medium",
      reset_sequence: 1,
      movement_sequences: timeline
        .filter((item) => item.kind === "position")
        .flatMap((item) => [item.sequence - 1, item.sequence]),
      atlas_digest: "fixture-atlas-midgaard",
      evidence: ["semantic fixture reset and movement chain"],
    },
    position_confidence: current.confidence,
    position_method: current.method,
    combat: through >= 34,
    combat_episode: through < 34 ? null : {
      active: true,
      opponent: "a large kobold",
      first_observed_turn: 46,
      observed_exchanges: Math.min(
        combatEvents.length,
        3,
      ),
      outcome: null,
      command_trace: "trace-live-44",
      lines: combatEvents
        .map((event) => ({
          text: String(event.data.label),
          sequence: event.seq,
          observed_at: event.at,
          confidence: "medium",
          method: "combat-colour-or-verb",
          evidence: `gateway observation seq ${event.seq}`,
        })),
      evidence: combatEvents.map((event) => event.seq),
    },
    vitals: {
      hit: through >= 46 ? 41 : 55,
      hit_max: 71,
      mana: 96,
      mana_max: 117,
      move: 58,
      move_max: 83,
      level: through >= 23 ? 4 : 3,
      gold: 127,
    },
    player_status: {
      fields: {
        hit: observedStatus(through >= 46 ? 41 : 55, through >= 46 ? 46 : 1),
        mana: observedStatus(96, 1),
        move: observedStatus(58, 1),
        level: observedStatus(through >= 23 ? 4 : 3, through >= 23 ? 23 : 1),
        gold: observedStatus(127, 1),
        posture: observedStatus("fighting", through >= 45 ? 45 : 1),
        hungry: observedStatus(false, 1),
        thirsty: observedStatus(false, 1),
        drunk: observedStatus(false, 1),
        poisoned: observedStatus(false, 1),
        encumbered: observedStatus(false, 1),
      },
      capture_gaps: [],
    },
    cost_usd: Number((0.118 * through / 47).toFixed(5)),
    current_turn_cost_usd: 0.0025,
    spend_cap_usd: 0.5,
    spend_cap_scope: "session",
    economics: Array.from(
      { length: Math.min(through, 20) },
      (_, index) => ({
        response: index + 1,
        at: new Date((1_800_000_001 + index) * 1_000).toISOString(),
        cost_usd: index === 19
          ? 0.0025
          : index === 18
            ? 0.002049
            : Number((0.0017 + index * 0.000019).toFixed(6)),
        cumulative_cost_usd: Number((0.118 * (index + 1) / 20).toFixed(6)),
        context_tokens: 2_300 + index * 116,
      }),
    ),
    room_economics: through >= 42 ? [{
      node_id: "room-back-street",
      response_count: 2,
      cost_usd: 0.014,
      first_response: 17,
      last_response: 18,
      evidence: [
        "agent log line 41; gateway position seq 42",
        "agent log line 43; gateway position seq 42",
      ],
    }] : [],
    unattributed_room_economics: {
      response_count: Math.max(0, Math.min(through, 20) - (through >= 42 ? 2 : 0)),
      cost_usd: Number(
        Math.max(0, 0.118 * through / 47 - (through >= 42 ? 0.014 : 0))
          .toFixed(6),
      ),
      evidence: ["fixture responses without a safe room correlation"],
    },
    usage: {
      fresh_input: Math.round(12_400 * through / 47),
      cache_read: Math.round(33_526 * through / 47),
      cache_write: 0,
      output: Math.round(480 * through / 47),
    },
    parse_miss_rate: 0.021,
    milestones: through >= 23 ? [{
      kind: "level_up",
      sequence: 23,
      at: 1_800_000_023,
      previous: 3,
      current: 4,
      evidence: "gateway observation seq 23",
    }] : [],
    rooms: visibleRooms.map((room) => ({
      id: room.id,
      place: room.place,
      title: room.title,
      exits: room.exits,
      first_sequence: room.first_seq,
      last_sequence: through,
      visits: room.visits,
      state: room.id === current.id ? "current" : "observed",
      confidence: room.confidence,
    })),
    world: {
      nodes: visibleRooms.map((room) => ({
        ...room,
        evidence: [room.first_seq],
        last_seq: through,
        state: room.id === current.id ? "current" : "observed",
      })),
      edges: edges.filter((edge) => (
        visibleRooms.some((room) => room.id === edge.source)
        && visibleRooms.some((room) => room.id === edge.target)
      )),
      current_title: current.title,
      current_confidence: current.confidence,
      candidates: through >= 30
        ? frontier.map((candidate) => candidate.id)
        : [],
      candidate_details: [],
      duplicate_titles: [],
      objective_beacons: [{
        node_id: "room-back-street",
        label: "Minotaur Lair",
        reason: "A retained observation links signs of the objective to this route.",
        evidence: [47],
      }],
      frontier: through >= 30 ? frontier : [],
      parse_miss_rate: 0.021,
      parse_misses: [],
      unknown_positions: 0,
    },
    timeline,
    capture_gaps: [],
  };
}

function observedStatus(value: boolean | number | string, sequence: number) {
  return {
    value,
    sequence,
    observed_at: 1_800_000_000 + sequence,
    confidence: "high",
    method: "fixture retained observation",
  };
}

const rooms = [
  room("room-temple", 3000, "The Temple Of Midgaard", ["east"], 1, 18),
  room(
    "room-temple-square",
    3001,
    "Temple Square",
    ["west", "north", "east"],
    8,
    12,
  ),
  room(
    "room-market",
    3011,
    "Market Square",
    ["south", "north", "east"],
    14,
    9,
  ),
  room("room-north-market", 3012, "N Market", ["south"], 16, 2),
  room(
    "room-common",
    3020,
    "Common Square",
    ["west", "south", "northeast"],
    22,
    7,
  ),
  room("room-grocer", 3031, "Grocer", ["north", "south", "west"], 30, 3),
  room("room-bakery", 3010, "Bakery", ["north"], 32, 2),
  room(
    "room-nexus",
    3040,
    "A Nexus",
    ["southwest", "east", "north"],
    24,
    5,
  ),
  room(
    "room-white-square",
    3041,
    "White Sq",
    ["west", "northeast", "southeast", "south", "north"],
    26,
    4,
  ),
  room(
    "room-back-street",
    3050,
    "Back Street",
    ["southwest", "north", "east"],
    42,
    4,
  ),
  room("room-north-back-street", 3051, "N Back St", ["south", "east"], 43, 2),
  room(
    "room-dark-alley",
    3048,
    "A Dark Alley",
    ["northwest", "south"],
    47,
    2,
  ),
  room("room-deep-alley", 3049, "Deep Alley", ["north"], 40, 1),
  room("room-city-gate", 3060, "City Gate", ["south", "north", "east"], 34, 3),
  room("room-gatehouse", 3061, "Gatehouse", ["south"], 35, 1),
  room("room-armorer", 3021, "Armorer", ["west"], 18, 2),
  room("room-baker-road", 3032, "Baker Rd", ["north", "east"], 20, 2),
  room("room-south-white", 3042, "S White", ["north", "west"], 36, 2),
  room("room-southwest-path", 3043, "SW Path", ["east", "north"], 37, 1),
  room("room-northeast-path", 3044, "NE Path", ["south", "west"], 38, 1),
  room("room-east-road", 3052, "E Road", ["west", "north"], 44, 1),
  room("room-northeast-road", 3053, "NE Road", ["south", "west"], 45, 1),
];

function room(
  id: string,
  place: number,
  title: string,
  exits: string[],
  firstSequence: number,
  visits: number,
) {
  const mobs = id === "room-dark-alley" ? ["a large kobold"] : [];
  const objects = id === "room-back-street" ? ["trail marker"] : [];
  return {
    id,
    place,
    title,
    description: id === "room-back-street" ? {
      text: "A narrow street bends between weathered stone buildings.",
      evidence: [firstSequence],
    } : null,
    atlas: {
      vnum: place,
      zone_id: 30,
      zone_label: "Midgaard",
      sector: "city",
      atlas_digest: "fixture-atlas-midgaard",
      confidence: "medium" as const,
      evidence: [`fixture verified position seq ${firstSequence}`],
    },
    exits,
    mobs,
    objects,
    mob_sightings: mobs.map((name) => ({
      name,
      count: 2,
      first_seq: firstSequence,
      last_seq: firstSequence,
      evidence: [firstSequence],
    })),
    object_sightings: objects.map((name) => ({
      name,
      count: 1,
      first_seq: firstSequence,
      last_seq: firstSequence,
      evidence: [firstSequence],
    })),
    visits,
    first_seq: firstSequence,
    last_seq: firstSequence,
    confidence: "high",
    method: "room-id",
  };
}

const edges = [
  edge("edge-1", "room-temple", "room-temple-square", "east", 12, 8),
  edge("edge-2", "room-temple-square", "room-market", "north", 9, 14),
  edge("edge-3", "room-market", "room-north-market", "north", 2, 16),
  edge("edge-4", "room-temple-square", "room-common", "east", 7, 22),
  edge("edge-5", "room-common", "room-grocer", "south", 3, 30),
  edge("edge-6", "room-grocer", "room-bakery", "south", 2, 32),
  edge("edge-7", "room-common", "room-nexus", "northeast", 5, 24),
  edge("edge-8", "room-nexus", "room-white-square", "east", 4, 26),
  edge(
    "edge-9",
    "room-white-square",
    "room-back-street",
    "northeast",
    4,
    42,
  ),
  edge(
    "edge-10",
    "room-back-street",
    "room-north-back-street",
    "north",
    2,
    43,
  ),
  edge(
    "edge-11",
    "room-white-square",
    "room-dark-alley",
    "southeast",
    2,
    47,
  ),
  edge("edge-12", "room-dark-alley", "room-deep-alley", "south", 1, 40),
  edge("edge-13", "room-nexus", "room-city-gate", "north", 3, 34),
  edge("edge-14", "room-city-gate", "room-gatehouse", "north", 1, 35),
  edge("edge-15", "room-market", "room-armorer", "east", 2, 18),
  edge("edge-16", "room-temple", "room-baker-road", "south", 2, 20),
  edge("edge-17", "room-grocer", "room-baker-road", "west", 2, 30),
  edge("edge-18", "room-white-square", "room-south-white", "south", 2, 36),
  edge(
    "edge-19",
    "room-south-white",
    "room-southwest-path",
    "west",
    1,
    37,
  ),
  edge("edge-20", "room-southwest-path", "room-nexus", "north", 1, 37),
  edge("edge-21", "room-white-square", "room-northeast-path", "north", 1, 38),
  edge("edge-22", "room-northeast-path", "room-city-gate", "west", 1, 38),
  edge("edge-23", "room-back-street", "room-east-road", "east", 1, 44),
  edge("edge-24", "room-east-road", "room-northeast-road", "north", 1, 45),
  edge(
    "edge-25",
    "room-northeast-road",
    "room-north-back-street",
    "west",
    1,
    45,
  ),
];

const frontier = [
  frontierExit("room-north-market", "north", 16),
  frontierExit("room-gatehouse", "north", 35),
  frontierExit("room-deep-alley", "south", 40),
  frontierExit("room-northeast-road", "northeast", 45),
  frontierExit("room-bakery", "south", 32),
];

function frontierExit(source: string, direction: string, sequence: number) {
  return {
    id: `frontier:${source}:${direction}`,
    source,
    direction,
    evidence: [sequence],
  };
}

function edge(
  id: string,
  source: string,
  target: string,
  direction: string,
  traversals: number,
  sequence: number,
) {
  return { id, source, target, direction, traversals, evidence: [sequence] };
}
