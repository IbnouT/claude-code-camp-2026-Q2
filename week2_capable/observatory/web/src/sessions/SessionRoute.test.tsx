// @vitest-environment jsdom

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Catalog,
  SessionInvestigation,
} from "../contracts";
import { SessionRoute } from "./SessionRoute";

const catalog: Catalog = {
  version: 1,
  players: [{ id: "poucet", label: "poucet" }],
  sessions: [{
    id: "stopped-1",
    player_id: "poucet",
    character: "poucet",
    gateway_session_id: "gateway-1",
    state: "stopped",
    control_state: "stopped",
    control_available: false,
    capture_status: "complete",
    created_at: "2026-08-01T01:00:00Z",
    updated_at: "2026-08-01T01:01:00Z",
    ended_at: "2026-08-01T01:01:00Z",
    stop_mode: "operator",
    event_count: 1,
    latest_seq: 1,
    legacy: false,
    live: false,
    objective: "Inspect a completed run",
    goal_count: 1,
    nudge_count: 0,
  }],
};

const investigation: SessionInvestigation = {
  version: 1,
  source_kind: "runtime_session",
  correlation: "runtime:stopped-1",
  run: {
    id: "stopped-1",
    label: "Inspect a completed run",
    journey: "",
    attempt: "stopped-",
    success: false,
    stop_reason: "operator",
    iterations: 0,
    cost_usd: 0,
    result_mode: "",
    lifecycle: "stopped",
    capture_status: "complete",
    created_at: "2026-08-01T01:00:00Z",
    ended_at: "2026-08-01T01:01:00Z",
    duration_ms: 60_000,
    turns: 0,
    responses: 0,
    goal_epochs: 1,
  },
  player_id: "poucet",
  agent_session_id: "stopped-1",
  gateway_session_id: "gateway-1",
  objective: "Inspect a completed run",
  model: null,
  records: [],
  diagnostics: [],
  diagnostic_coverage: ["instrumentation_gap"],
  lens: {
    wire: { state: "missing", title: "Wire", text: "Missing", citations: [] },
    parsed: { state: "missing", title: "Parsed", text: "Missing", citations: [] },
    rendered: {
      state: "missing",
      title: "Rendered",
      text: "Missing",
      citations: [],
    },
    believed: {
      state: "missing",
      title: "Believed",
      text: "Missing",
      citations: [],
    },
    truth: { state: "missing", title: "Truth", text: "Missing", citations: [] },
  },
  world: {
    nodes: [],
    edges: [],
    current_title: null,
    current_confidence: "unknown",
    candidates: [],
    candidate_details: [],
    duplicate_titles: [],
    objective_beacons: [],
    frontier: [],
    parse_miss_rate: 0,
    parse_misses: [],
    unknown_positions: 0,
  },
  cost: {
    total_usd: 0,
    response_total_usd: 0,
    raw_response_total_usd: 0,
    reconciliation_delta_usd: 0,
    complete: false,
    completeness_detail: "No agent response ledger was retained.",
    fresh_input_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    output_tokens: 0,
    points: [],
  },
  capture_gaps: [],
};

describe("SessionRoute", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    window.history.replaceState(
      null,
      "",
      "/sessions?player=poucet&session=stopped-1",
    );
    vi.stubGlobal("fetch", vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/sessions") {
          return Promise.resolve({
            ok: true,
            json: async () => catalog,
          } as Response);
        }
        if (url === "/api/sessions/stopped-1/investigation") {
          return Promise.resolve({
            ok: true,
            json: async () => investigation,
          } as Response);
        }
        return Promise.reject(new Error(`Unexpected request: ${url}`));
      },
    ));
  });

  it("loads any launcher session through the universal investigation contract", async () => {
    const view = render(<SessionRoute theme="dark" onThemeChange={vi.fn()} />);

    expect(await screen.findByRole("heading", {
      level: 1,
      name: "Inspect a completed run",
    })).toBeInTheDocument();
    expect(document.body).toHaveClass("sessions-document");
    expect(screen.getByRole("button", {
      name: "View context, poucet, stopped, stopped-1",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Live/ })).toBeDisabled();

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/sessions/stopped-1/investigation",
        expect.objectContaining({ cache: "no-store" }),
      );
    });

    view.unmount();
    expect(document.body).not.toHaveClass("sessions-document");
  });

  it("asks against the selected session run instead of a Live scope", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockImplementation(
      (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/sessions") {
          return Promise.resolve({
            ok: true,
            json: async () => catalog,
          } as Response);
        }
        if (url === "/api/sessions/stopped-1/investigation") {
          return Promise.resolve({
            ok: true,
            json: async () => investigation,
          } as Response);
        }
        if (url === "/api/ask" && init?.method === "POST") {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              tier: "deterministic",
              answer: "The session stopped cooperatively.",
              citations: [{
                id: "runtime:session:stopped-1",
                label: "poucet session lifecycle",
                excerpt: "state=stopped stop_mode=cooperative",
              }],
              missing: [],
            }),
          } as Response);
        }
        return Promise.reject(new Error(`Unexpected request: ${url}`));
      },
    ));
    render(<SessionRoute theme="dark" onThemeChange={vi.fn()} />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Inspect a completed run",
    });
    await user.click(screen.getByRole("button", {
      name: /Ask about this session/,
    }));
    await user.type(screen.getByRole("textbox", {
      name: "Question about this session",
    }), "Why did the session stop?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await screen.findByText("The session stopped cooperatively.");
    const askCall = vi.mocked(fetch).mock.calls.find(
      ([input]) => String(input) === "/api/ask",
    );
    expect(askCall).toBeDefined();
    const body = JSON.parse(String(askCall?.[1]?.body));
    expect(body.scope).toMatchObject({
      space: "sessions",
      player_id: "poucet",
      run_id: "stopped-1",
    });
    expect(body.scope).not.toHaveProperty("live_session_id");
    expect(screen.getByText("poucet session lifecycle")).toBeInTheDocument();
  });

  it("opens an experiment sample through the same Sessions workspace", async () => {
    const recording = {
      ...investigation,
      source_kind: "experiment_sample" as const,
      correlation: "benchmark:run-42",
      run: {
        ...investigation.run,
        id: "run-42",
        label: "J1 retained sample",
        success: true,
      },
    };
    window.history.replaceState(null, "", "/sessions?run=run-42");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/sessions") {
          return Promise.resolve({
            ok: true,
            json: async () => catalog,
          } as Response);
        }
        if (url === "/api/recorded-sessions/run-42") {
          return Promise.resolve({
            ok: true,
            json: async () => recording,
          } as Response);
        }
        return Promise.reject(new Error(`Unexpected request: ${url}`));
      },
    ));

    render(<SessionRoute theme="dark" onThemeChange={vi.fn()} />);

    expect(await screen.findByRole("heading", {
      level: 1,
      name: "Inspect a completed run",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "View context, poucet, ended, run-42",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Experiments/ })).toBeEnabled();
  });

  it("shows five recent goals and searches the complete session history", async () => {
    const user = userEvent.setup();
    const sessions = Array.from({ length: 7 }, (_, index) => ({
      ...catalog.sessions[0],
      id: `session-${index + 1}`,
      objective: `Goal ${index + 1}`,
      updated_at: `2026-08-01T0${index + 1}:01:00Z`,
    }));
    const expandedCatalog = { ...catalog, sessions };
    window.history.replaceState(
      null,
      "",
      "/sessions?player=poucet&session=session-7",
    );
    vi.stubGlobal("fetch", vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/sessions") {
          return Promise.resolve({
            ok: true,
            json: async () => expandedCatalog,
          } as Response);
        }
        if (url === "/api/sessions/session-7/investigation") {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ...investigation,
              objective: "Goal 7",
              run: { ...investigation.run, id: "session-7", label: "Goal 7" },
            }),
          } as Response);
        }
        return Promise.reject(new Error(`Unexpected request: ${url}`));
      },
    ));

    render(<SessionRoute theme="dark" onThemeChange={vi.fn()} />);

    await screen.findByRole("heading", { level: 1, name: "Goal 7" });
    await user.click(screen.getByRole("button", { name: /View context/ }));
    const panel = screen.getByRole("dialog", { name: "View context" });
    expect(within(panel).getByText("Recent poucet sessions"))
      .toBeInTheDocument();
    expect(within(panel).getAllByRole("button", { name: /stopped, Goal/ }))
      .toHaveLength(5);
    expect(within(panel).getByText("Goal 6")).toBeInTheDocument();
    expect(within(panel).queryByText("Goal 1")).not.toBeInTheDocument();

    await user.click(within(panel).getByRole("button", {
      name: /View all poucet sessions \(7\)/,
    }));
    const finder = screen.getByRole("dialog", { name: "Find a session" });
    await user.type(
      within(finder).getByRole("searchbox", { name: "Search sessions" }),
      "Goal 1",
    );
    expect(within(finder).getByText("Goal 1")).toBeInTheDocument();
    expect(within(finder).queryByText("Goal 7")).not.toBeInTheDocument();
  });

  it("refetches the story only when the change signal moves", async () => {
    vi.useFakeTimers();
    const liveCatalog: Catalog = {
      ...catalog,
      sessions: [{
        ...catalog.sessions[0],
        id: "live-1",
        state: "running",
        ended_at: null,
        live: true,
      }],
    };
    const liveInvestigation: SessionInvestigation = {
      ...investigation,
      run: { ...investigation.run, id: "live-1", lifecycle: "running" },
      agent_session_id: "live-1",
    };
    let signal = {
      version: 1 as const,
      session_id: "live-1",
      latest_seq: 4,
      agent_log_size: 1_024,
      live: true,
    };
    const requested: string[] = [];
    window.history.replaceState(
      null,
      "",
      "/sessions?player=poucet&session=live-1",
    );
    vi.stubGlobal("fetch", vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url = String(input);
        requested.push(url);
        if (url === "/api/sessions") {
          return Promise.resolve({
            ok: true,
            json: async () => liveCatalog,
          } as Response);
        }
        if (url === "/api/sessions/live-1/investigation") {
          return Promise.resolve({
            ok: true,
            json: async () => liveInvestigation,
          } as Response);
        }
        if (url === "/api/sessions/live-1/changed") {
          return Promise.resolve({
            ok: true,
            json: async () => signal,
          } as Response);
        }
        return Promise.reject(new Error(`Unexpected request: ${url}`));
      },
    ));

    const settle = async (ms = 0): Promise<void> => {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
      });
    };
    render(<SessionRoute theme="dark" onThemeChange={vi.fn()} />);
    await settle();
    await settle();
    const stories = (): number => requested.filter(
      (url) => url.endsWith("/investigation"),
    ).length;
    expect(stories()).toBe(1);

    await settle(2_000);
    expect(stories()).toBe(2);

    await settle(2_000);
    expect(stories()).toBe(2);

    signal = { ...signal, agent_log_size: 4_096 };
    await settle(2_000);
    expect(stories()).toBe(3);

    expect(requested.filter((url) => url === "/api/sessions")).toHaveLength(1);
    vi.useRealTimers();
  });

  it("stops polling once the change signal reports the session ended", async () => {
    vi.useFakeTimers();
    const liveCatalog: Catalog = {
      ...catalog,
      sessions: [{
        ...catalog.sessions[0],
        id: "live-1",
        state: "running",
        ended_at: null,
        live: true,
      }],
    };
    const liveInvestigation: SessionInvestigation = {
      ...investigation,
      run: { ...investigation.run, id: "live-1", lifecycle: "running" },
      agent_session_id: "live-1",
    };
    let signal = {
      version: 1 as const,
      session_id: "live-1",
      latest_seq: 4,
      agent_log_size: 1_024,
      live: true,
    };
    const requested: string[] = [];
    window.history.replaceState(
      null,
      "",
      "/sessions?player=poucet&session=live-1",
    );
    vi.stubGlobal("fetch", vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url = String(input);
        requested.push(url);
        if (url === "/api/sessions") {
          return Promise.resolve({
            ok: true,
            json: async () => liveCatalog,
          } as Response);
        }
        if (url === "/api/sessions/live-1/investigation") {
          return Promise.resolve({
            ok: true,
            json: async () => liveInvestigation,
          } as Response);
        }
        if (url === "/api/sessions/live-1/changed") {
          return Promise.resolve({
            ok: true,
            json: async () => signal,
          } as Response);
        }
        return Promise.reject(new Error(`Unexpected request: ${url}`));
      },
    ));

    const settle = async (ms = 0): Promise<void> => {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
      });
    };
    const polls = (): number => requested.filter(
      (url) => url.endsWith("/changed"),
    ).length;
    render(<SessionRoute theme="dark" onThemeChange={vi.fn()} />);
    await settle();
    await settle();

    await settle(2_000);
    expect(polls()).toBe(1);

    signal = { ...signal, latest_seq: 9, live: false };
    await settle(2_000);
    expect(polls()).toBe(2);
    const stories = requested.filter(
      (url) => url.endsWith("/investigation"),
    ).length;

    await settle(10_000);
    expect(polls()).toBe(2);
    expect(
      requested.filter((url) => url.endsWith("/investigation")).length,
    ).toBe(stories);
    vi.useRealTimers();
  });

  it("refreshes the selected session when the page becomes active", async () => {
    let current = investigation;
    vi.stubGlobal("fetch", vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/sessions") {
          return Promise.resolve({
            ok: true,
            json: async () => catalog,
          } as Response);
        }
        if (url === "/api/sessions/stopped-1/investigation") {
          return Promise.resolve({
            ok: true,
            json: async () => current,
          } as Response);
        }
        return Promise.reject(new Error(`Unexpected request: ${url}`));
      },
    ));
    render(<SessionRoute theme="dark" onThemeChange={vi.fn()} />);
    await screen.findByRole("heading", {
      level: 1,
      name: "Inspect a completed run",
    });

    current = {
      ...investigation,
      objective: "Practice at the warrior guild",
      run: {
        ...investigation.run,
        label: "Practice at the warrior guild",
        goal_epochs: 2,
      },
    };
    window.dispatchEvent(new Event("focus"));

    expect(await screen.findByRole("heading", {
      level: 1,
      name: "Practice at the warrior guild",
    })).toBeInTheDocument();
  });
});
