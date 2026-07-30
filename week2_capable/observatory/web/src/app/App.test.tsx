import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const sessions = [
  {
    id: "session-alpha",
    player_id: "alpha",
    character: "Alpha",
    gateway_session_id: "gateway-alpha",
    state: "running",
    control_state: "running",
    control_available: true,
    capture_status: "partial",
    created_at: "2026-07-30T08:00:00Z",
    updated_at: "2026-07-30T08:02:00Z",
    ended_at: null,
    event_count: 2,
    latest_seq: 2,
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
    capture_status: "complete",
    created_at: "2026-07-30T07:00:00Z",
    updated_at: "2026-07-30T07:05:00Z",
    ended_at: "2026-07-30T07:05:00Z",
    event_count: 2,
    latest_seq: 2,
    legacy: false,
    live: false,
  },
];

let controlRequests: unknown[] = [];

describe("observatory product shell", () => {
  beforeEach(() => {
    controlRequests = [];
    window.history.replaceState(null, "", "/?space=live");
    vi.stubGlobal("fetch", vi.fn(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = new URL(String(input), "http://observatory");
      if (url.pathname === "/api/capabilities") {
        return jsonResponse({
          sources: [
            { id: "gateway", label: "Gateway journal", state: "ready", detail: "ready" },
            { id: "agent", label: "Agent events", state: "ready", detail: "ready" },
            {
              id: "benchmark",
              label: "Benchmark evidence",
              state: "unavailable",
              detail: "Benchmark deliberately unavailable",
            },
            { id: "knowledge", label: "Knowledge store", state: "ready", detail: "ready" },
          ],
          features: ["live", "replay", "time-travel", "query"],
        });
      }
      if (url.pathname === "/api/sessions") {
        return jsonResponse({
          version: 1,
          players: [
            { id: "alpha", label: "Alpha" },
            { id: "beta", label: "Beta" },
          ],
          sessions,
        });
      }
      if (url.pathname === "/api/contracts") {
        return jsonResponse({
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
        });
      }
      const selected = url.pathname.includes("session-beta") ? "beta" : "alpha";
      if (url.pathname.endsWith("/replay")) {
        return new Response(replayFor(selected), {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      }
      if (url.pathname.endsWith("/events")) {
        return new Response("", {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      }
      if (url.pathname.endsWith("/snapshot")) {
        return jsonResponse(snapshotFor(selected));
      }
      if (url.pathname.endsWith("/control") && init?.method === "POST") {
        const request = JSON.parse(String(init.body)) as {
          request_id: string;
          action: string;
        };
        controlRequests.push(request);
        return jsonResponse({
          request_id: request.request_id,
          action: request.action,
          state: "running",
          insertion: "next_iteration_boundary",
        });
      }
      return new Response("not found", { status: 404 });
    }));
  });

  it("renders one coherent header and real selected session", async () => {
    render(<App />);
    expect(
      screen.getByRole("link", { name: "Boukensha Observatory home" }),
    ).toBeVisible();
    expect(
      screen.getByRole("navigation", { name: "Observatory spaces" }),
    ).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Player" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Session" })).toBeVisible();
    expect(await screen.findByRole("heading", { name: "Living world" })).toBeVisible();
    expect((await screen.findAllByText("Alpha Temple")).length).toBeGreaterThan(0);
    expect(screen.getByText("Agent event stream is incomplete")).toBeVisible();
    expect(screen.queryByText("Benchmark deliberately unavailable"))
      .not.toBeInTheDocument();
  });

  it("keeps global context while moving between spaces", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Player" }),
      "beta",
    );
    await user.click(screen.getByRole("button", { name: "Knowledge" }));
    expect(screen.getByRole("combobox", { name: "Player" })).toHaveValue("beta");
    expect(screen.queryByRole("combobox", { name: "Session" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load recorded evidence" }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Direct the agent/ }))
      .not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Search knowledge" })).toBeVisible();
    expect(screen.getByText(/Separate what the player learned/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Sessions" }));
    expect(screen.getByRole("combobox", { name: "Session" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Load recorded evidence" }))
      .toBeDisabled();
  });

  it("opens deterministic Ask from the scoped Live workspace action", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Ask about this run" }));
    const dialog = screen.getByRole("dialog", { name: "Ask or search evidence" });
    expect(dialog).toBeVisible();
    expect(
      within(dialog).getByText("Ask with evidence, even without a model"),
    ).toBeVisible();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Ask about this run" })).toHaveFocus();
  });

  it("sends operator guidance only to the selected live session", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /Direct the agent/ }));
    const dialog = screen.getByRole("dialog", { name: "Direct the selected agent" });
    expect(dialog).toBeVisible();
    expect(within(dialog).getByText("Authenticated live session")).toBeVisible();
    expect(within(dialog).getByText("Maximum additional spend")).toBeVisible();
    await user.type(
      within(dialog).getByRole("textbox", { name: "Operator guidance" }),
      "Inspect the west exit before choosing another route.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Confirm guide" }));
    expect(await within(dialog).findByText("guide accepted")).toBeVisible();
    expect(within(dialog).getByText(/next iteration boundary/)).toBeVisible();
    expect(controlRequests).toHaveLength(1);
    expect(controlRequests[0]).toMatchObject({
      action: "guide",
      instruction: "Inspect the west exit before choosing another route.",
      expected_sequence: 2,
    });
  });

  it("makes every evidence form explicit, including a missing truth form", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("tab", { name: /Truth/ }));
    expect(
      screen.getByText("Observer truth is not configured for this live session."),
    ).toBeVisible();
    expect(screen.getByText("missing")).toBeVisible();
  });

  it("changes player and session evidence without leaking the prior player", async () => {
    const user = userEvent.setup();
    render(<App />);
    const player = await screen.findByRole("combobox", { name: "Player" });
    expect((await screen.findAllByText("Alpha Temple")).length).toBeGreaterThan(0);

    await user.selectOptions(player, "beta");

    await waitFor(() => {
      expect(screen.getAllByText("Beta Field").length).toBeGreaterThan(0);
    });
    expect(screen.queryAllByText("Alpha Temple")).toHaveLength(0);
    expect(screen.getByRole("combobox", { name: "Session" }))
      .toHaveValue("session-beta");
    expect(screen.getByRole("button", { name: "Control unavailable" }))
      .toBeDisabled();
  });
});

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function replayFor(player: string): string {
  const session = `gateway-${player}`;
  const title = player === "alpha" ? "Alpha Temple" : "Beta Field";
  return [
    {
      seq: 1,
      session,
      at: 1,
      kind: "observation",
      trace_id: `trace-${player}`,
      data: { kind: "room", title, exits: ["north"] },
    },
    {
      seq: 2,
      session,
      at: 2,
      kind: "position",
      trace_id: `trace-${player}`,
      data: { place: player === "alpha" ? 3001 : 4001, title, confidence: "high" },
    },
  ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
}

function snapshotFor(player: string) {
  const title = player === "alpha" ? "Alpha Temple" : "Beta Field";
  const live = player === "alpha";
  return {
    session_id: `session-${player}`,
    gateway_session_id: `gateway-${player}`,
    player_id: player,
    character: player === "alpha" ? "Alpha" : "Beta",
    lifecycle: live ? "running" : "stopped",
    control_state: live ? "running" : null,
    following_live: true,
    through_sequence: 2,
    latest_sequence: 2,
    selected_at: 2,
    objective: `Explore as ${player}`,
    model: "test-model",
    tools: ["look", "move"],
    iteration: 1,
    current_room: title,
    position_confidence: "high",
    position_method: "room-id",
    combat: false,
    vitals: { hit: 100, mana: 80, move: 90 },
    cost_usd: player === "alpha" ? 0.01 : 0.02,
    usage: { fresh_input: 100, cache_read: 0, cache_write: 0, output: 10 },
    parse_miss_rate: 0,
    rooms: [{
      id: `place-${player}`,
      place: player === "alpha" ? 3001 : 4001,
      title,
      exits: ["north"],
      first_sequence: 2,
      last_sequence: 2,
      visits: 1,
      state: "current",
      confidence: "high",
    }],
    timeline: [{
      id: `gateway-${player}-2`,
      sequence: 2,
      at: 2,
      source: "gateway",
      kind: "position",
      label: `Position: ${title}`,
      cost_usd: 0,
      tokens: 0,
      trace_id: `trace-${player}`,
    }],
    capture_gaps: player === "alpha" ? ["agent_events_incomplete"] : [],
  };
}
