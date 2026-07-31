// @vitest-environment jsdom

import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import type {
  Catalog,
  Session,
  Snapshot,
} from "../contracts";
import { LiveShell } from "./LiveShell";

const identity = {
  playerId: "poucet",
  sessionId: "57a5315b-f1c1-4e7e-b7d7-ee41de85c90f",
};

function runtimeSession(overrides: Partial<Session> = {}): Session {
  return {
    id: identity.sessionId,
    player_id: identity.playerId,
    character: identity.playerId,
    gateway_session_id: identity.sessionId,
    state: "running",
    control_state: "running",
    control_available: true,
    capture_status: "partial",
    created_at: "2026-07-31T01:00:00Z",
    updated_at: "2026-07-31T01:01:00Z",
    ended_at: null,
    stop_mode: null,
    event_count: 1,
    latest_seq: 1,
    legacy: false,
    live: true,
    ...overrides,
  };
}

function runtimeCatalog(sessions: Session[] = [runtimeSession()]): Catalog {
  const players = Array.from(new Set(
    sessions.map((session) => session.player_id),
  )).map((id) => ({ id, label: id }));
  return { version: 1, players, sessions };
}

function catalogResponse(catalog = runtimeCatalog()): Response {
  return {
    ok: true,
    json: async () => catalog,
  } as Response;
}

function runtimeSnapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    session_id: identity.sessionId,
    gateway_session_id: "gateway-session-1",
    player_id: identity.playerId,
    character: identity.playerId,
    lifecycle: "running",
    control_state: "running",
    following_live: true,
    through_sequence: 42,
    selected_at: null,
    objective: "Explore the learned world",
    objective_initial: {
      title: "Explore the learned world",
      clue: null,
      source_kind: "benchmark",
      revision: 1,
      evidence: "agent log line 1",
    },
    objective_context: {
      title: "Explore the learned world",
      clue: null,
      source_kind: "benchmark",
      revision: 1,
      evidence: "agent log line 1",
    },
    suggested_action: null,
    recent_path: null,
    turn: 4,
    latest_sequence: 42,
    agent_thought: {
      text: "Return to the Temple and try another route.",
      phase: "plan",
      observed_at: "2026-07-31T04:01:26Z",
      line: 723,
      evidence: "agent log line 723",
    },
    agent_belief: null,
    model: "fixture-model",
    tools: ["move", "look"],
    iteration: 4,
    context_limit: 200_000,
    current_room: "A Nexus",
    zone: null,
    position_confidence: "tracked",
    position_method: "fixture",
    combat: false,
    combat_episode: null,
    friction: {
      kind: null,
      repeated_command: null,
      repeated_count: 0,
      distinct_places: 2,
      iterations: 4,
      new_places: 2,
      window_iterations: 4,
      iterations_since_new_place: 1,
      threshold: null,
      evidence: [],
    },
    vitals: {},
    player_status: { fields: {}, capture_gaps: [] },
    cost_usd: 0,
    current_turn_cost_usd: 0,
    spend_cap_usd: 0.5,
    spend_cap_scope: "session",
    economics: [],
    room_economics: [{
      node_id: "place:2",
      response_count: 1,
      cost_usd: 0.014,
      first_response: 2,
      last_response: 2,
      evidence: ["agent:response:2"],
    }],
    unattributed_room_economics: null,
    usage: {
      fresh_input: 0,
      cache_read: 0,
      cache_write: 0,
      output: 0,
    },
    milestones: [],
    parse_miss_rate: 0,
    rooms: [],
    timeline: [],
    capture_gaps: [],
    world: {
      current_title: "A Nexus",
      current_confidence: "tracked",
      nodes: [
        {
          id: "place:1",
          place: 1,
          title: "More Of The Hallway",
          description: null,
          exits: ["n"],
          mobs: [],
          objects: [],
          mob_sightings: [],
          object_sightings: [],
          visits: 1,
          evidence: [10],
          first_seq: 10,
          last_seq: 10,
          state: "observed",
          confidence: "tracked",
          method: "fixture",
        },
        {
          id: "place:2",
          place: 2,
          title: "A Nexus",
          description: {
            text: "A broad crossing.",
            evidence: [20],
          },
          atlas: {
            vnum: 3001,
            zone_id: 30,
            zone_label: "Midgaard",
            sector: "urban",
            atlas_digest: "fixture",
            confidence: "high",
            evidence: ["atlas:3001"],
          },
          exits: ["s"],
          mobs: ["a large kobold"],
          objects: ["a brass key"],
          mob_sightings: [{
            name: "a large kobold",
            count: 2,
            first_seq: 20,
            last_seq: 41,
            evidence: [20, 41],
          }],
          object_sightings: [{
            name: "a brass key",
            count: 1,
            first_seq: 23,
            last_seq: 23,
            evidence: [23],
          }],
          visits: 1,
          evidence: [20],
          first_seq: 20,
          last_seq: 20,
          state: "current",
          confidence: "tracked",
          method: "fixture",
        },
      ],
      edges: [
        {
          id: "1:2:north",
          source: "place:1",
          target: "place:2",
          direction: "north",
          traversals: 1,
          evidence: [20],
        },
      ],
      frontier: [],
      candidates: [],
      candidate_details: [],
      duplicate_titles: [],
      objective_beacons: [],
      parse_miss_rate: 0,
      parse_misses: [],
      unknown_positions: 0,
    },
    ...overrides,
  };
}

function snapshotResponse(snapshot = runtimeSnapshot()): Response {
  return {
    ok: true,
    json: async () => snapshot,
  } as Response;
}

function useCatalog(catalog: Catalog): void {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    return Promise.resolve(
      String(input).includes("/snapshot")
        ? snapshotResponse()
        : catalogResponse(catalog),
    );
  });
}

describe("Live shell", () => {
  beforeEach(() => {
    vi.stubGlobal("innerWidth", 1_280);
    window.history.replaceState(
      {},
      "",
      `/live?player=${identity.playerId}&session=${identity.sessionId}`,
    );
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: RequestInfo | URL) => {
      return Promise.resolve(
        String(input).includes("/snapshot")
          ? snapshotResponse()
          : catalogResponse(),
      );
    }));
    vi.stubGlobal("crypto", {
      randomUUID: () => "00000000-0000-4000-8000-000000000001",
    });
  });

  it("renders the phase-one evidence from its typed sources", async () => {
    const snapshot = runtimeSnapshot({
      objective_context: {
        title: "Find the Massive Minotaur",
        clue: "Search beyond the temple.",
        source_kind: "benchmark",
        revision: 2,
        evidence: "agent log line 2",
      },
      agent_belief: {
        text: "Attacking a large kobold",
        phase: "tool_call",
        observed_at: new Date().toISOString(),
        line: 724,
        evidence: "agent log line 724",
      },
      vitals: { hit: 30, mana: 22, move: 49 },
      player_status: {
        fields: {
          posture: { value: "standing", sequence: 30, observed_at: 1, confidence: "high", method: "score" },
          max_hit: { value: 41, sequence: 30, observed_at: 1, confidence: "high", method: "score" },
          max_mana: { value: 24, sequence: 30, observed_at: 1, confidence: "high", method: "score" },
          max_move: { value: 50, sequence: 30, observed_at: 1, confidence: "high", method: "score" },
          level: { value: 7, sequence: 30, observed_at: 1, confidence: "high", method: "score" },
          gold: { value: 128, sequence: 30, observed_at: 1, confidence: "high", method: "score" },
          hungry: { value: true, sequence: 30, observed_at: 1, confidence: "high", method: "score" },
          thirsty: { value: false, sequence: 30, observed_at: 1, confidence: "high", method: "score" },
        },
        capture_gaps: ["poisoned"],
      },
      cost_usd: 0.18,
      current_turn_cost_usd: 0.03,
      spend_cap_usd: 0.2,
      spend_cap_scope: "turn",
      economics: [
        { response: 1, at: "2026-07-31T04:00:00Z", cost_usd: 0.02, cumulative_cost_usd: 0.15, context_tokens: 50_000 },
        { response: 2, at: "2026-07-31T04:01:00Z", cost_usd: 0.03, cumulative_cost_usd: 0.18, context_tokens: 100_000 },
      ],
      usage: { fresh_input: 600, cache_read: 300, cache_write: 100, output: 200 },
      timeline: [{
        id: "gateway:41",
        sequence: 41,
        at: 1,
        source: "gateway",
        kind: "command",
        label: "Command: kill kobold",
        cost_usd: 0,
        tokens: 0,
        trace_id: "trace-1",
        quiet_cohort: null,
      }],
    });
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      return Promise.resolve(String(input).includes("/snapshot")
        ? snapshotResponse(snapshot)
        : catalogResponse());
    });
    render(<LiveShell identity={identity} />);

    expect(await screen.findByRole("region", { name: "Current objective" }))
      .toHaveTextContent("Find the Massive Minotaur");
    const rail = screen.getByRole("complementary", { name: "Live evidence rail" });
    expect(rail).toHaveTextContent("Latest tool action · now");
    expect(rail).toHaveTextContent("Attacking a large kobold");
    expect(rail).toHaveTextContent("kill kobold");
    expect(rail).toHaveTextContent("30 / 41");
    expect(screen.getByText("30 / 41").closest(".live-vital")).toHaveClass("is-hit");
    expect(screen.getByText("22 / 24").closest(".live-vital")).toHaveClass("is-mana");
    expect(screen.getByText("49 / 50").closest(".live-vital")).toHaveClass("is-move");
    expect(rail).toHaveTextContent("Hungry");
    expect(screen.getByText("Hungry").closest(".live-condition-list > span"))
      .toHaveClass("is-warn");
    expect(rail).not.toHaveTextContent("Not thirsty");
    expect(rail).not.toHaveTextContent("poisoned");
    expect(rail).toHaveTextContent("Turn spend");
    expect(rail).toHaveTextContent("$0.030 / $0.200");
    expect(rail).toHaveTextContent("Cost per response: last 20");
    expect(rail).toHaveTextContent("1,000");
    expect(rail).toHaveTextContent("30%");
    expect(rail).toHaveTextContent("Latest response context");
    expect(rail).toHaveTextContent("50%");
  });

  it("messages only the latest running agent sequence", async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/control")) {
        body = JSON.parse(String(init?.body));
        return Promise.resolve({
          ok: true,
          json: async () => ({
            request_id: "00000000-0000-4000-8000-000000000001",
            action: "guide",
            state: "running",
            insertion: "next iteration boundary",
          }),
        } as Response);
      }
      return Promise.resolve(url.includes("/snapshot")
        ? snapshotResponse()
        : catalogResponse());
    });
    render(<LiveShell identity={identity} />);

    await user.click(await screen.findByRole("button", { name: "Message agent" }));
    await user.type(screen.getByLabelText("Guidance for the next iteration boundary"), "Try the western exit");
    await user.click(screen.getByRole("button", { name: "Send guidance" }));

    expect(await screen.findByText("Guidance accepted")).toBeInTheDocument();
    expect(body).toEqual({
      request_id: "00000000-0000-4000-8000-000000000001",
      action: "guide",
      instruction: "Try the western exit",
      expected_sequence: 42,
    });
  });

  it("steps through typed causal landmarks and returns to live", async () => {
    const user = userEvent.setup();
    const latest = runtimeSnapshot({
      cost_usd: 0.042,
      economics: [
        {
          response: 1,
          at: "2026-07-31T04:00:00Z",
          cost_usd: 0.012,
          cumulative_cost_usd: 0.012,
          context_tokens: 1_200,
        },
        {
          response: 2,
          at: "2026-07-31T04:01:00Z",
          cost_usd: 0.03,
          cumulative_cost_usd: 0.042,
          context_tokens: 2_400,
        },
      ],
      milestones: [{
        kind: "level_up",
        sequence: 30,
        at: 1_753_937_310,
        previous: 1,
        current: 2,
        evidence: "gateway player_state seq 30",
      }],
      rooms: [
        {
          id: "place:1",
          place: 1,
          title: "The Temple",
          exits: ["south"],
          first_sequence: 10,
          last_sequence: 19,
          visits: 1,
          state: "observed",
          confidence: "tracked",
        },
        {
          id: "place:2",
          place: 2,
          title: "Market Square",
          exits: ["north"],
          first_sequence: 20,
          last_sequence: 42,
          visits: 1,
          state: "current",
          confidence: "tracked",
        },
      ],
      timeline: [
        {
          id: "gateway:10",
          sequence: 10,
          at: 1_753_937_300,
          source: "gateway",
          kind: "position",
          label: "The Temple",
          cost_usd: 0,
          tokens: 0,
          trace_id: "trace-10",
          quiet_cohort: null,
        },
        {
          id: "gateway:20",
          sequence: 20,
          at: 1_753_937_305,
          source: "gateway",
          kind: "position",
          label: "Market Square",
          cost_usd: 0,
          tokens: 0,
          trace_id: "trace-20",
          quiet_cohort: null,
        },
      ],
    });
    const historical = (through: number) => runtimeSnapshot({
      ...latest,
      following_live: false,
      through_sequence: through,
      selected_at: 1_753_937_300 + through,
      cost_usd: through === 30 ? 0.03 : 0.02,
    });
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      const through = new URL(url, window.location.origin)
        .searchParams.get("through");
      if (url.includes("/snapshot")) {
        return Promise.resolve(snapshotResponse(
          through === null ? latest : historical(Number(through)),
        ));
      }
      return Promise.resolve(catalogResponse());
    });
    render(<LiveShell identity={identity} />);

    const timeline = await screen.findByRole("region", {
      name: "Causal timeline",
    });
    expect(timeline).toHaveTextContent("following live");
    expect(screen.getByRole("button", {
      name: "Room: The Temple, sequence 10",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Room: Market Square, sequence 20",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Level up: Level 2, sequence 30",
    })).toBeInTheDocument();
    expect(screen.getByRole("img", {
      name: "Cumulative session cost",
    })).toBeInTheDocument();

    await user.click(screen.getByRole("button", {
      name: "Previous landmark",
    }));
    expect(await screen.findByRole("button", {
      name: "Return to live",
    })).toBeInTheDocument();
    expect(timeline).toHaveTextContent("seq 30 / 42");
    expect(timeline).toHaveTextContent("inspecting history");
    expect(new URL(window.location.href).searchParams.get("through")).toBe("30");
    expect(screen.getByRole("button", { name: "Message agent" }))
      .toBeDisabled();

    await user.click(screen.getByRole("button", {
      name: "Previous landmark",
    }));
    await waitFor(() => {
      expect(timeline).toHaveTextContent("seq 20 / 42");
    });
    await user.click(screen.getByRole("button", { name: "Next landmark" }));
    await waitFor(() => {
      expect(timeline).toHaveTextContent("seq 30 / 42");
    });

    await user.click(screen.getByRole("button", { name: "Return to live" }));
    await waitFor(() => {
      expect(timeline).toHaveTextContent("following live");
    });
    expect(new URL(window.location.href).searchParams.has("through")).toBe(false);
    expect(screen.getByRole("button", { name: "Message agent" }))
      .toBeEnabled();
  });

  it("shows only evidence-backed active combat detail", async () => {
    const snapshot = runtimeSnapshot({
      combat: true,
      combat_episode: {
        active: true,
        opponent: "a large kobold",
        first_observed_turn: 46,
        observed_exchanges: 4,
        outcome: null,
        command_trace: "trace-combat",
        lines: [],
        evidence: [40, 42],
      },
    });
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      return Promise.resolve(String(input).includes("/snapshot")
        ? snapshotResponse(snapshot)
        : catalogResponse());
    });
    render(<LiveShell identity={identity} />);

    const combat = await screen.findByRole("complementary", { name: "Active combat" });
    expect(combat).toHaveTextContent("a large kobold");
    expect(combat).toHaveTextContent("turn 46");
    expect(combat).toHaveTextContent("pending");
    expect(combat).not.toHaveTextContent(/HP|exchange|unresolved/i);
  });

  it("keeps the evidence rail reachable on a narrow viewport", async () => {
    vi.stubGlobal("innerWidth", 390);
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);

    const rail = screen.getByRole("complementary", { name: "Live evidence rail" });
    expect(rail).toHaveClass("is-closed");
    await user.click(screen.getByRole("button", { name: "Open Live evidence" }));
    expect(rail).toHaveClass("is-open");
    expect(rail).toHaveTextContent("Live economics");
  });

  it("keeps friction stable and names the retained rule when it fires", async () => {
    const user = userEvent.setup();
    const session = runtimeSession({ capture_status: "complete" });
    const snapshot = runtimeSnapshot({
      friction: {
        kind: "confusion_loop",
        repeated_command: "east",
        repeated_count: 5,
        distinct_places: 6,
        iterations: 12,
        new_places: 1,
        window_iterations: 10,
        iterations_since_new_place: 6,
        threshold: "same command recorded at least five times",
        evidence: [31, 33, 35, 37, 39],
      },
    });
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      return Promise.resolve(String(input).includes("/snapshot")
        ? snapshotResponse(snapshot)
        : catalogResponse(runtimeCatalog([session])));
    });
    render(<LiveShell identity={identity} />);

    expect(await screen.findByText("Possible navigation loop")).toBeInTheDocument();
    const progress = screen.getByRole("heading", { name: "Progress" }).parentElement;
    expect(progress).toHaveTextContent("1 new place · 10 iterations");
    expect(progress).toHaveTextContent("east repeated ×5 in the current room");
    await user.click(screen.getByRole("button", { name: "Inspect attempts" }));
    expect(screen.getByText("Evidence sequences 31, 33, 35, 37, 39"))
      .toBeInTheDocument();
  });

  it("keeps progress measurements visible during combat", async () => {
    const snapshot = runtimeSnapshot({ combat: true });
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      return Promise.resolve(String(input).includes("/snapshot")
        ? snapshotResponse(snapshot)
        : catalogResponse(runtimeCatalog([runtimeSession({ capture_status: "complete" })])));
    });
    render(<LiveShell identity={identity} />);

    expect(await screen.findByText("Combat in progress. Spatial progress may pause."))
      .toBeInTheDocument();
    expect(screen.getByText("2 new places · 4 iterations")).toBeInTheDocument();
  });

  it("renders one verified context chip and the learned-world map", async () => {
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(await screen.findByRole("button", {
      name: /View context, poucet, running, 57a5315b/,
    })).toHaveTextContent(/poucet.*running.*57a5315b/);
    expect(screen.queryByRole("combobox", {
      name: "Player",
    })).not.toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: /Ask about this session/,
    })).toBeInTheDocument();
    expect(screen.queryByRole("button", {
      name: "Load recorded session",
    })).not.toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Use light theme",
    })).toBeInTheDocument();
    expect(screen.getByRole("main", {
      name: "Live workspace",
    })).not.toBeEmptyDOMElement();
    expect(screen.getByRole("complementary", {
      name: "Live evidence rail",
    })).toBeInTheDocument();
    expect(screen.getByRole("region", {
      name: "Causal timeline",
    })).toBeInTheDocument();
    expect(await screen.findByRole("img", {
      name: "Learned world, 2 rooms",
    })).toBeInTheDocument();
    expect(screen.getByLabelText(
      /Agent in A Nexus, atlas-correlated vnum 3001/,
    )).toBeInTheDocument();
    expect(screen.getByRole("complementary", {
      name: "Agent thought",
    })).toHaveTextContent("Return to the Temple and try another route.");
    await user.click(screen.getByRole("button", {
      name: "Expand map legend",
    }));
    expect(screen.getByRole("complementary", {
      name: "Map evidence legend",
    })).toHaveTextContent("Learned room");
    expect(screen.getByRole("complementary", {
      name: "Map evidence legend",
    })).toHaveTextContent("Current room");
  });

  it("opens, retargets, and closes the evidence-backed room inspector", async () => {
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);
    const nexus = await screen.findByRole("button", {
      name: /Agent in A Nexus/,
    });
    const hallway = screen.getByRole("button", {
      name: /More Of The Hallway/,
    });

    await user.click(nexus);
    const inspector = screen.getByRole("complementary", {
      name: "Room inspector, A Nexus",
    });
    expect(inspector).toHaveTextContent("A broad crossing.");
    expect(inspector).toHaveTextContent("a large kobold");
    expect(inspector).toHaveTextContent("a brass key");
    expect(inspector).toHaveTextContent("$0.014");
    expect(new URL(window.location.href).searchParams.get("room"))
      .toBe("vnum:3001");

    await user.click(hallway);
    expect(screen.getByRole("complementary", {
      name: "Room inspector, More Of The Hallway",
    })).toBeInTheDocument();
    await user.click(hallway);
    expect(screen.queryByRole("complementary", {
      name: /Room inspector/,
    })).not.toBeInTheDocument();
    expect(new URL(window.location.href).searchParams.has("room")).toBe(false);

    hallway.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("complementary", {
      name: "Room inspector, More Of The Hallway",
    })).toBeInTheDocument();
    await user.click(screen.getByRole("button", {
      name: "Close room inspector",
    }));
    expect(screen.queryByRole("complementary", {
      name: /Room inspector/,
    })).not.toBeInTheDocument();

    await user.click(nexus);
    await user.click(screen.getByRole("button", {
      name: "Collapse agent thought",
    }));
    expect(screen.getByRole("complementary", {
      name: "Room inspector, A Nexus",
    })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Lantern" }));
    expect(screen.getByRole("complementary", {
      name: "Room inspector, A Nexus",
    })).toBeInTheDocument();
  });

  it("selects and retargets rooms in every map presentation", async () => {
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);
    const nexus = await screen.findByRole("button", {
      name: /Agent in A Nexus/,
    });
    const hallway = screen.getByRole("button", {
      name: /More Of The Hallway/,
    });

    await user.click(screen.getByRole("button", { name: "Focus" }));
    await user.click(nexus);
    expect(screen.getByRole("complementary", {
      name: "Room inspector, A Nexus",
    })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Lantern" }));
    await user.click(hallway);
    expect(screen.getByRole("complementary", {
      name: "Room inspector, More Of The Hallway",
    })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Grow" }));
    await user.click(nexus);
    expect(screen.getByRole("complementary", {
      name: "Room inspector, A Nexus",
    })).toBeInTheDocument();
  });

  it("closes the inspector before an open Ask dialog on Escape", async () => {
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);
    await user.click(await screen.findByRole("button", {
      name: /Agent in A Nexus/,
    }));
    await user.keyboard("{Control>}k{/Control}");

    expect(screen.getByRole("complementary", {
      name: "Room inspector, A Nexus",
    })).toBeInTheDocument();
    expect(screen.getByRole("dialog", {
      name: "Ask about this session",
    })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary", {
      name: /Room inspector/,
    })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", {
      name: "Ask about this session",
    })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", {
      name: "Ask about this session",
    })).not.toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Expand map legend",
    })).toBeInTheDocument();

    await user.click(screen.getByRole("button", {
      name: "Expand map legend",
    }));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", {
      name: "Expand map legend",
    })).toBeInTheDocument();
  });

  it("omits an unobserved thought and collapses overlays on narrow screens", async () => {
    vi.stubGlobal("innerWidth", 390);
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      return Promise.resolve(
        String(input).includes("/snapshot")
          ? snapshotResponse(runtimeSnapshot({ agent_thought: null }))
          : catalogResponse(),
      );
    });
    render(<LiveShell identity={identity} />);

    await screen.findByRole("img", {
      name: "Learned world, 2 rooms",
    });
    expect(screen.queryByRole("complementary", {
      name: "Agent thought",
    })).not.toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Expand map legend",
    })).toBeInTheDocument();
  });

  it("opens scoped Ask from the header and keyboard entry", async () => {
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);

    await screen.findByText("running");
    await user.click(screen.getByRole("button", {
      name: /Ask about this session/,
    }));
    expect(screen.getByRole("dialog", {
      name: "Ask about this session",
    })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close Ask" }));
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("dialog", {
      name: "Ask about this session",
    })).toBeInTheDocument();
  });

  it("mounts the map camera and presentation controls", async () => {
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);

    await screen.findByRole("img", {
      name: "Learned world, 2 rooms",
    });
    expect(screen.getByRole("button", {
      name: "Follow",
    })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", {
      name: "Grow",
    })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", {
      name: "Fit map",
    }));
    expect(screen.getByRole("button", {
      name: "Fit map",
    })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", {
      name: "Lantern",
    }));
    expect(screen.getByRole("button", {
      name: "Lantern",
    })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", {
      name: "Learned world map",
    })).toHaveClass("is-lantern");
  });

  it("fits and pans Focus while Lantern hands a drag to Grow", async () => {
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);

    const map = await screen.findByRole("img", {
      name: "Learned world, 2 rooms",
    });
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    const zoomed = viewBox(map);

    await user.click(screen.getByRole("button", { name: "Focus" }));
    const focused = viewBox(map);
    const currentRoom = screen.getByRole("button", {
      name: /Agent in A Nexus/,
    });
    const currentPoint = translatedPoint(currentRoom);

    expect(screen.getByRole("button", {
      name: "Follow",
    })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", {
      name: "Focus",
    })).toHaveAttribute("aria-pressed", "true");
    expect(focused.width).toBeCloseTo(zoomed.width);
    expect(focused.height).toBeCloseTo(zoomed.height);
    expect(currentPoint.x + 32).toBeGreaterThan(focused.x);
    expect(currentPoint.x + 32).toBeLessThan(focused.x + focused.width);
    expect(currentPoint.y + 32).toBeGreaterThan(focused.y);
    expect(currentPoint.y + 32).toBeLessThan(focused.y + focused.height);
    expect(screen.getByText("Drag to explore the learned world.")).toBeVisible();

    Object.defineProperties(map, {
      getBoundingClientRect: {
        value: () => ({
          bottom: 570,
          height: 570,
          left: 0,
          right: 960,
          top: 0,
          width: 960,
          x: 0,
          y: 0,
          toJSON: () => ({}),
        }),
      },
      hasPointerCapture: { value: () => true },
      releasePointerCapture: { value: vi.fn() },
      setPointerCapture: { value: vi.fn() },
    });
    fireEvent.pointerDown(map, {
      pointerId: 7,
      clientX: 400,
      clientY: 280,
    });
    fireEvent.pointerMove(map, {
      pointerId: 7,
      clientX: 420,
      clientY: 280,
    });
    const focusHandoff = viewBox(map);
    expect(focusHandoff).toEqual(focused);
    expect(screen.queryByText(
      "Drag to explore the learned world.",
    )).not.toBeInTheDocument();
    fireEvent.pointerMove(map, {
      pointerId: 7,
      clientX: 440,
      clientY: 280,
    });

    expect(screen.getByRole("button", {
      name: "Focus",
    })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", {
      name: "Manual",
    })).toHaveAttribute("aria-pressed", "true");
    const pannedFocus = viewBox(map);
    expect(pannedFocus.width).toBeCloseTo(focused.width);
    expect(pannedFocus.height).toBeCloseTo(focused.height);
    expect(pannedFocus.x).not.toBeCloseTo(focused.x);
    expect(pannedFocus.y).toBeCloseTo(focused.y);
    fireEvent.pointerUp(map, { pointerId: 7 });

    await user.click(screen.getByRole("button", { name: "Lantern" }));
    const lantern = viewBox(map);
    expect(lantern.width).toBeCloseTo(pannedFocus.width);
    expect(lantern.height).toBeCloseTo(pannedFocus.height);
    expect(lantern.x + lantern.width / 2).toBeCloseTo(currentPoint.x + 32);
    expect(lantern.y + lantern.height / 2).toBeCloseTo(currentPoint.y + 32);

    fireEvent.pointerDown(map, {
      pointerId: 8,
      clientX: 400,
      clientY: 280,
    });
    fireEvent.pointerMove(map, {
      pointerId: 8,
      clientX: 420,
      clientY: 280,
    });
    const lanternHandoff = viewBox(map);
    expect(lanternHandoff).toEqual(lantern);
    fireEvent.pointerMove(map, {
      pointerId: 8,
      clientX: 440,
      clientY: 280,
    });

    await waitFor(() => {
      expect(screen.getByRole("button", {
        name: "Grow",
      })).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getByRole("button", {
      name: "Manual",
    })).toHaveAttribute("aria-pressed", "true");
    const dragged = viewBox(map);
    expect(dragged.width).toBeCloseTo(lantern.width);
    expect(dragged.height).toBeCloseTo(lantern.height);
    expect(dragged.x + dragged.width / 2).toBeCloseTo(
      lantern.x + lantern.width / 2 - 20 * lantern.width / 960,
    );
  });

  it("re-centers panned Focus on agent movement without changing size", async () => {
    const initial = runtimeSnapshot();
    const moved: Snapshot = {
      ...initial,
      latest_sequence: initial.latest_sequence + 1,
      world: {
        ...initial.world,
        current_title: "More Of The Hallway",
        nodes: initial.world.nodes.map((node) => ({
          ...node,
          state: node.id === "place:1" ? "current" : "observed",
        })),
      },
    };
    let snapshots = 0;
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (!String(input).includes("/snapshot")) {
        return Promise.resolve(catalogResponse());
      }
      const response = snapshots === 0
        ? snapshotResponse(initial)
        : snapshotResponse(moved);
      snapshots += 1;
      return Promise.resolve(response);
    });
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);

    const map = await screen.findByRole("img", {
      name: "Learned world, 2 rooms",
    });
    await user.click(screen.getByRole("button", { name: "Focus" }));
    Object.defineProperties(map, {
      getBoundingClientRect: {
        value: () => ({
          bottom: 570,
          height: 570,
          left: 0,
          right: 960,
          top: 0,
          width: 960,
          x: 0,
          y: 0,
          toJSON: () => ({}),
        }),
      },
      hasPointerCapture: { value: () => true },
      releasePointerCapture: { value: vi.fn() },
      setPointerCapture: { value: vi.fn() },
    });
    fireEvent.pointerDown(map, {
      pointerId: 9,
      clientX: 400,
      clientY: 280,
    });
    fireEvent.pointerMove(map, {
      pointerId: 9,
      clientX: 420,
      clientY: 280,
    });
    fireEvent.pointerMove(map, {
      pointerId: 9,
      clientX: 460,
      clientY: 280,
    });
    fireEvent.pointerUp(map, { pointerId: 9 });
    const panned = viewBox(map);
    expect(screen.getByRole("button", {
      name: "Manual",
    })).toHaveAttribute("aria-pressed", "true");

    const movedRoom = await screen.findByRole("button", {
      name: /Agent in More Of The Hallway/,
    }, { timeout: 4_000 });
    await waitFor(() => {
      expect(screen.getByRole("button", {
        name: "Follow",
      })).toHaveAttribute("aria-pressed", "true");
    }, { timeout: 4_000 });
    const movedPoint = translatedPoint(movedRoom);
    await waitFor(() => {
      const followed = viewBox(map);
      expect(followed.width).toBe(panned.width);
      expect(followed.height).toBe(panned.height);
      expect(followed.x + followed.width / 2).toBeCloseTo(movedPoint.x + 32);
      expect(followed.y + followed.height / 2).toBeCloseTo(movedPoint.y + 32);
    }, { timeout: 4_000 });
  }, 5_000);

  it("offers recent sessions and one destination for each other player", async () => {
    const recorded = runtimeSession({
      id: "poucet-recording",
      state: "stopped",
      control_state: null,
      control_available: false,
      capture_status: "complete",
      ended_at: "2026-07-31T00:31:00Z",
      updated_at: "2026-07-31T00:31:00Z",
      stop_mode: "cooperative",
      event_count: 12,
      live: false,
    });
    const lancelot = runtimeSession({
      id: "lancelot-live",
      player_id: "lancelot",
      character: "lancelot",
      event_count: 8,
    });
    useCatalog(runtimeCatalog([
      runtimeSession(),
      recorded,
      lancelot,
    ]));
    const navigate = vi.fn();
    const user = userEvent.setup();
    render(<LiveShell identity={identity} navigate={navigate} />);

    await user.click(await screen.findByRole("button", {
      name: /View context/,
    }));
    expect(screen.getByText("Recent poucet sessions")).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: /stopped, poucet-r.*12 events/,
    })).toBeInTheDocument();
    expect(screen.getByText("Other players")).toBeInTheDocument();

    await user.click(screen.getByRole("button", {
      name: /lancelot, running, 8 events/,
    }));
    expect(navigate).toHaveBeenCalledWith(
      "/live?player=lancelot&session=lancelot-live",
    );
  });

  it("offers distinct leave and stop lifecycle actions", async () => {
    const navigate = vi.fn();
    const user = userEvent.setup();
    render(<LiveShell identity={identity} navigate={navigate} />);

    await user.click(await screen.findByRole("button", {
      name: /View context/,
    }));
    expect(screen.getByRole("button", {
      name: "Leave Live view",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Stop session…",
    })).toBeInTheDocument();

    await user.click(screen.getByRole("button", {
      name: "Leave Live view",
    }));
    expect(navigate).toHaveBeenCalledWith("/");
  });

  it("opens a confirmation before stopping", async () => {
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);

    await user.click(await screen.findByRole("button", {
      name: /View context/,
    }));
    await user.click(screen.getByRole("button", { name: "Stop session…" }));

    expect(screen.getByRole("dialog", {
      name: "Stop this session?",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Stop session",
    })).toBeInTheDocument();
  });

  it("offers the recording instead of Stop for an ended deep link", async () => {
    useCatalog(runtimeCatalog([
      runtimeSession({
        state: "stopped",
        control_state: null,
        control_available: false,
        capture_status: "complete",
        ended_at: "2026-07-31T01:01:00Z",
        stop_mode: "cooperative",
        live: false,
      }),
    ]));
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);

    await user.click(await screen.findByRole("button", {
      name: /View context/,
    }));
    expect(screen.queryByRole("button", {
      name: "Stop session…",
    })).not.toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "View recording",
    })).toBeInTheDocument();
  });

  it("keeps identity and removes Stop while reconnecting", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      return String(input).includes("/snapshot")
        ? Promise.resolve(snapshotResponse())
        : Promise.reject(new Error("offline"));
    });
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);

    expect(await screen.findByRole("button", {
      name: /View context, poucet, reconnecting, 57a5315b/,
    })).toHaveTextContent(/poucet.*reconnecting.*57a5315b/);
    await user.click(screen.getByRole("button", { name: /View context/ }));
    expect(screen.queryByRole("button", {
      name: "Stop session…",
    })).not.toBeInTheDocument();
  });

  it("redirects a verified missing session to the launcher", async () => {
    useCatalog(runtimeCatalog([]));
    const navigate = vi.fn();
    render(<LiveShell identity={identity} navigate={navigate} />);

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/"));
  });

  it("supports arrow navigation and restores chip focus on Escape", async () => {
    const user = userEvent.setup();
    render(<LiveShell identity={identity} />);
    const chip = await screen.findByRole("button", { name: /View context/ });

    await user.click(chip);
    const leave = screen.getByRole("button", { name: "Leave Live view" });
    await waitFor(() => expect(leave).toHaveFocus());
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("button", { name: "Stop session…" })).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(chip).toHaveFocus());
    expect(screen.queryByRole("dialog", { name: "View context" }))
      .not.toBeInTheDocument();
  });
});

function viewBox(element: HTMLElement): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  const values = element.getAttribute("viewBox")?.split(" ").map(Number);
  if (values === undefined || values.length !== 4) {
    throw new Error("Expected a four-value map viewBox");
  }
  return {
    x: values[0],
    y: values[1],
    width: values[2],
    height: values[3],
  };
}

function translatedPoint(element: HTMLElement): { x: number; y: number } {
  const match = element.getAttribute("transform")?.match(
    /^translate\(([-\d.]+) ([-\d.]+)\)$/,
  );
  if (match === undefined || match === null) {
    throw new Error("Expected a translated map room");
  }
  return {
    x: Number(match[1]),
    y: Number(match[2]),
  };
}
