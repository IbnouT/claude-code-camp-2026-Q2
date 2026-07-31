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

function runtimeSnapshot(): Snapshot {
  return {
    player_id: identity.playerId,
    character: identity.playerId,
    turn: 4,
    latest_sequence: 42,
    cost_usd: 0,
    player_status: { fields: {} },
    world: {
      current_title: "A Nexus",
      current_confidence: "tracked",
      nodes: [
        {
          id: "place:1",
          place: 1,
          title: "More Of The Hallway",
          exits: ["n"],
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
          exits: ["s"],
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
    expect(await screen.findByRole("img", {
      name: "Learned world, 2 rooms",
    })).toBeInTheDocument();
    expect(screen.getByLabelText(
      "Agent in A Nexus, observed place 2",
    )).toBeInTheDocument();
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
