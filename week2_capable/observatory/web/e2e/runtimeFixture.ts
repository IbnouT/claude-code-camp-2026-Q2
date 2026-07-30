import type { Page } from "@playwright/test";

const sessions = [
  {
    id: "session-alpha",
    player_id: "alpha",
    character: "Alpha",
    gateway_session_id: "gateway-alpha",
    state: "running",
    control_state: "running",
    control_available: true,
    capture_status: "complete",
    created_at: "2026-07-30T08:00:00Z",
    updated_at: "2026-07-30T08:02:00Z",
    ended_at: null,
    event_count: 4,
    latest_seq: 4,
    legacy: false,
    live: true,
  },
  {
    id: "session-beta",
    player_id: "beta",
    character: "Beta",
    gateway_session_id: "gateway-beta",
    state: "stopped",
    control_state: null,
    control_available: false,
    capture_status: "partial",
    created_at: "2026-07-30T07:00:00Z",
    updated_at: "2026-07-30T07:05:00Z",
    ended_at: "2026-07-30T07:05:00Z",
    event_count: 2,
    latest_seq: 2,
    legacy: false,
    live: false,
  },
];

export async function mockRuntime(page: Page, catalogDelayMs = 0) {
  await page.route("**/api/world/atlas*", async (route) => {
    const url = new URL(route.request().url());
    const selectedZone = url.searchParams.get("zone");
    const nodes = selectedZone === null ? [] : Array.from(
      { length: 61 },
      (_, index) => ({
        id: `room:${3000 + index}`,
        vnum: 3000 + index,
        title: index % 10 === 0 ? "Duplicate Hall" : `Atlas room ${index + 1}`,
        zone: 30,
        exits: index < 60 ? { north: 3001 + index } : {},
      }),
    );
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        available: true,
        source_state: "available",
        source_label: "fixture world",
        level: selectedZone === null ? "overview" : "zone",
        selected_zone: selectedZone === null ? null : Number(selectedZone),
        room_count: 1878,
        edge_count: 4293,
        zone_count: 33,
        duplicate_title_count: 241,
        load_ms: 6.7,
        memory_bytes: 985531,
        detail: selectedZone === null
          ? "Observer truth is isolated from the selected journey."
          : "Zone 30 is not correlated to the selected journey without vnum evidence.",
        zones: selectedZone === null
          ? Array.from({ length: 33 }, (_, index) => ({
            id: `zone:${index + 1}`,
            zone: index + 1,
            room_count: 30 + index,
            edge_count: 60 + index * 2,
            duplicate_title_count: index % 8,
          }))
          : [],
        nodes,
      }),
    });
  });
  await page.route("**/api/sessions", async (route) => {
    if (catalogDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, catalogDelayMs));
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 1,
        players: [
          { id: "alpha", label: "Alpha" },
          { id: "beta", label: "Beta" },
        ],
        sessions,
      }),
    });
  });
  await page.route("**/api/contracts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        event: {
          required: ["seq", "session", "at", "kind", "data"],
          additionalProperties: false,
          properties: {
            seq: {},
            session: {},
            at: {},
            kind: {},
            trace_id: {},
            data: {},
          },
        },
      }),
    });
  });
  await page.route("**/api/sessions/*/replay?*", async (route) => {
    const player = route.request().url().includes("session-beta")
      ? "beta"
      : "alpha";
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: replay(player),
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
    const url = new URL(route.request().url());
    const player = url.pathname.includes("session-beta") ? "beta" : "alpha";
    const through = Number(url.searchParams.get("through")) || undefined;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(snapshot(player, through)),
    });
  });
  await page.route("**/api/sessions/*/control", async (route) => {
    const request = route.request().postDataJSON() as {
      request_id: string;
      action: string;
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        request_id: request.request_id,
        action: request.action,
        state: request.action === "pause" ? "paused" : "running",
        insertion: "next_iteration_boundary",
      }),
    });
  });
}

function replay(player: string): string {
  return events(player)
    .map((event) => `data: ${JSON.stringify(event)}\n\n`)
    .join("");
}

function events(player: string) {
  const session = `gateway-${player}`;
  if (player === "beta") {
    return [
      event(1, session, "observation", {
        kind: "room",
        title: "Beta Field",
        exits: ["east"],
      }),
      event(2, session, "position", {
        place: 4001,
        title: "Beta Field",
        confidence: "high",
        method: "room-id",
      }),
    ];
  }
  return [
    event(1, session, "observation", {
      kind: "room",
      title: "The Temple Of Midgaard",
      exits: ["north", "east", "south"],
    }),
    event(2, session, "position", {
      place: 3001,
      title: "The Temple Of Midgaard",
      confidence: "high",
      method: "room-id",
    }),
    event(3, session, "observation", {
      kind: "room",
      title: "Hidden Courtyard",
      exits: ["south", "down"],
    }),
    event(4, session, "position", {
      place: 3018,
      title: "Hidden Courtyard",
      confidence: "medium",
      method: "topology",
    }),
  ];
}

function event(
  seq: number,
  session: string,
  kind: string,
  data: Record<string, unknown>,
) {
  return {
    seq,
    session,
    at: 1_800_000_000 + seq,
    kind,
    trace_id: `trace-${session}-${seq}`,
    data,
  };
}

function snapshot(player: string, requested?: number) {
  const beta = player === "beta";
  const latest = beta ? 2 : 4;
  const through = Math.max(1, Math.min(requested ?? latest, latest));
  const firstPrefix = !beta && through < 3;
  const room = beta
    ? "Beta Field"
    : firstPrefix
      ? "The Temple Of Midgaard"
      : "Hidden Courtyard";
  const allRooms = beta
    ? [{
      id: "place-4001",
      place: 4001,
      title: "Beta Field",
      exits: ["east"],
      first_sequence: 2,
      last_sequence: 2,
      visits: 1,
      state: "current",
      confidence: "high",
    }]
    : [
      {
        id: "place-3001",
        place: 3001,
        title: "The Temple Of Midgaard",
        exits: ["north", "east", "south"],
        first_sequence: 2,
        last_sequence: 2,
        visits: 1,
        state: through < 3 ? "current" : "observed",
        confidence: "high",
      },
      {
        id: "place-3018",
        place: 3018,
        title: "Hidden Courtyard",
        exits: ["south", "down"],
        first_sequence: 4,
        last_sequence: 4,
        visits: 1,
        state: "current",
        confidence: "medium",
      },
    ].filter((candidate) => candidate.first_sequence <= through);
  const timeline = events(player)
    .filter((candidate) => candidate.seq <= through)
    .map((candidate) => ({
      id: `${candidate.session}-${candidate.seq}`,
      sequence: candidate.seq,
      at: candidate.at,
      source: "gateway",
      kind: candidate.kind,
      label: candidate.kind === "position"
        ? `Position: ${String(candidate.data.title)}`
        : String(candidate.data.title),
      cost_usd: 0,
      tokens: 0,
      trace_id: candidate.trace_id,
    }));
  return {
    session_id: `session-${player}`,
    gateway_session_id: `gateway-${player}`,
    player_id: player,
    character: beta ? "Beta" : "Alpha",
    lifecycle: beta ? "stopped" : "running",
    control_state: beta ? null : "running",
    following_live: requested === undefined || through === latest,
    through_sequence: through,
    latest_sequence: latest,
    selected_at: 1_800_000_000 + through,
    objective: beta ? "Map the eastern field" : "Find and fight the Minotaur",
    model: "claude-haiku-4-5",
    tools: ["look", "move", "attack", "flee"],
    iteration: beta ? 3 : 12,
    current_room: room,
    position_confidence: beta || firstPrefix ? "high" : "medium",
    position_method: beta || firstPrefix ? "room-id" : "topology",
    combat: !beta && through === 4,
    vitals: { hit: beta ? 100 : 72, mana: 61, move: 84 },
    cost_usd: beta ? 0.0184 : through < 3 ? 0.0321 : 0.0642,
    usage: {
      fresh_input: beta ? 2_200 : through < 3 ? 3_800 : 7_600,
      cache_read: beta ? 800 : through < 3 ? 1_900 : 4_200,
      cache_write: 0,
      output: beta ? 340 : through < 3 ? 520 : 1_040,
    },
    parse_miss_rate: 0.04,
    rooms: allRooms,
    world: {
      nodes: allRooms.map((candidate) => ({
        id: candidate.id,
        place: candidate.place,
        title: candidate.title,
        exits: candidate.exits,
        mobs: candidate.state === "current" && !beta
          ? ["Massive Minotaur"]
          : [],
        objects: candidate.state === "current" ? ["stone fountain"] : [],
        visits: candidate.visits,
        evidence: [candidate.last_sequence],
        first_seq: candidate.first_sequence,
        last_seq: candidate.last_sequence,
        state: candidate.state,
        confidence: candidate.confidence,
        method: candidate.confidence === "high" ? "room-id" : "topology",
      })),
      edges: allRooms.length > 1 ? [{
        id: `${allRooms[0].id}:${allRooms[1].id}:north`,
        source: allRooms[0].id,
        target: allRooms[1].id,
        direction: "north",
        traversals: 1,
        evidence: [allRooms[1].last_sequence],
      }] : [],
      current_title: room,
      current_confidence: beta || firstPrefix ? "high" : "medium",
      candidates: [],
      candidate_details: [],
      duplicate_titles: [],
      objective_beacons: beta || firstPrefix ? [] : [{
        node_id: allRooms.at(-1)?.id ?? "",
        label: "Massive Minotaur",
        reason: "A retained room observation places this objective entity here.",
        evidence: [through],
      }],
      parse_miss_rate: 0.04,
      parse_misses: [],
      unknown_positions: 0,
    },
    timeline,
    capture_gaps: [],
  };
}
