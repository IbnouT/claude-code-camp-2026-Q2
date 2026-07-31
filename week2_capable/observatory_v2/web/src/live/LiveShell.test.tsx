// @vitest-environment jsdom

import {
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
    player_id: identity.playerId,
    character: identity.playerId,
    turn: 4,
    latest_sequence: 42,
    cost_usd: 0,
    agent_thought: {
      text: "Return to the Temple and try another route.",
      phase: "plan",
      observed_at: "2026-07-31T04:01:26Z",
      line: 723,
      evidence: "agent log line 723",
    },
    room_economics: [{
      node_id: "place:2",
      response_count: 1,
      cost_usd: 0.014,
      first_response: 2,
      last_response: 2,
      evidence: ["agent:response:2"],
    }],
    player_status: { fields: {} },
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
  });

  it("renders one verified context chip and the learned-world map", async () => {
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
      name: "Collapse map legend",
    })).toBeInTheDocument();

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
