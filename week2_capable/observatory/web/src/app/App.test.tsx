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
let recoveryRequests: unknown[] = [];
let snapshotOverrides: Record<string, Record<string, unknown>> = {};

describe("observatory product shell", () => {
  beforeEach(() => {
    controlRequests = [];
    recoveryRequests = [];
    snapshotOverrides = {};
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
      const knowledgeMatch = url.pathname.match(
        /^\/api\/players\/(alpha|beta)\/knowledge$/,
      );
      if (knowledgeMatch && (!init?.method || init.method === "GET")) {
        const knowledgePlayer = knowledgeMatch[1] ?? "alpha";
        return jsonResponse({
          version: 1,
          player_id: knowledgePlayer,
          state: "ready",
          source: "per-player durable knowledge",
          cdc_cursor: 1,
          metrics: [{
            id: "assertions",
            label: "Assertions",
            value: 1,
            detail: "One retained assertion",
          }],
          assertions: [{
            assertion_id: `${knowledgePlayer}-assertion`,
            fact_id: "room:shared:title",
            subject: "room:shared",
            predicate: "title",
            value: `${knowledgePlayer} Bakery`,
            layer: "learned",
            status: "active",
            confidence: "high",
            current: true,
            conflict_group: null,
            evidence: [{
              session_id: `gateway-${knowledgePlayer}`,
              source_seq: 1,
              wire_digest: `wire-${knowledgePlayer}`,
              parser_version: "rules-1",
              method: "room-frame",
              observed_at: 1,
            }],
          }],
          changes: [],
          snapshots: [],
          recoveries: [],
          capture_gaps: [],
        });
      }
      if (
        url.pathname === "/api/players/alpha/knowledge/recovery"
        && init?.method === "POST"
      ) {
        recoveryRequests.push(JSON.parse(String(init.body)));
        return jsonResponse({ ok: true, action: "reset" });
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
        return jsonResponse({
          ...snapshotFor(selected),
          ...snapshotOverrides[selected],
        });
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
    expect(screen.getByRole("button", { name: "Session" })).toBeVisible();
    expect(
      await screen.findByRole("region", { name: "Live cockpit" }),
    ).toBeVisible();
    expect((await screen.findAllByText("Alpha Temple")).length).toBeGreaterThan(0);
    expect(screen.getByRole("status")).toHaveTextContent("capture gaps 1");
    expect(screen.getByRole("status"))
      .toHaveAttribute("title", "agent_events_incomplete");
    expect(screen.queryByText("Benchmark deliberately unavailable"))
      .not.toBeInTheDocument();
  });

  it("separates leaving Live from stopping the running session", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("region", { name: "Live cockpit" });

    await user.click(screen.getByRole("button", { name: "Session" }));
    const menu = screen.getByRole("menu", { name: "Session menu" });
    expect(
      within(menu).getByRole("menuitem", { name: /Leave Live view/ }),
    ).toHaveTextContent("The agent keeps running");
    await user.click(
      within(menu).getByRole("menuitem", { name: /Stop session/ }),
    );

    const dialog = screen.getByRole("dialog", {
      name: "Stop this session?",
    });
    expect(
      within(dialog).getByRole("button", { name: "Cancel" }),
    ).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(
      screen.queryByRole("dialog", { name: "Stop this session?" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the full retained intent available behind a bounded display", async () => {
    render(<App />);

    expect(await screen.findByText("Agent intends")).toBeVisible();
    const intent = screen.getByTitle(
      "Moving east toward the retained objective through the learned route",
    );
    expect(intent).toHaveClass("intent-value");
    expect(intent).toHaveTextContent(
      "Moving east toward the retained objective through the learned route",
    );
  });

  it("keeps completed combat history separate from current observed state", async () => {
    snapshotOverrides.alpha = {
      combat: false,
      combat_episode: {
        active: false,
        opponent: "a large kobold",
        first_observed_turn: 3,
        observed_exchanges: 1,
        outcome: "victory",
        command_trace: "trace-combat",
        lines: [{
          text: "A large kobold is dead!",
          sequence: 2,
          observed_at: 2,
          confidence: "medium",
          method: "combat-colour-or-verb",
          evidence: "gateway observation seq 2",
        }],
        evidence: [1, 2],
      },
    };
    render(<App />);

    expect(
      await screen.findByText("Victory: a large kobold"),
    ).toBeVisible();
    const observed = screen.getByText("Observed").parentElement;
    expect(observed).not.toBeNull();
    expect(within(observed as HTMLElement).getByText("Alpha Temple"))
      .toBeVisible();
    expect(screen.queryByText("In combat")).not.toBeInTheDocument();
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
    expect(screen.queryByRole("button", { name: "Session" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load recorded evidence" }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Direct the agent/ }))
      .not.toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Search knowledge" }),
    ).toBeVisible();
    expect(screen.getByRole("region", { name: "Player knowledge" }))
      .toBeVisible();
    expect(screen.getByRole("button", { name: "Learned map" }))
      .toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("button", { name: "Sessions" }));
    expect(
      await screen.findByRole("button", { name: "Session" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Load recorded evidence" }))
      .toBeEnabled();
  });

  it("opens deterministic Ask from the scoped Live workspace action", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "Ask about this session" }),
    );
    const dialog = screen.getByRole("dialog", { name: "Ask or search evidence" });
    expect(dialog).toBeVisible();
    expect(
      within(dialog).getByText("Ask with evidence, even without a model"),
    ).toBeVisible();
    await user.keyboard("{Escape}");
    expect(
      screen.getByRole("button", { name: "Ask about this session" }),
    ).toHaveFocus();
  });

  it("confirms knowledge reset against the selected live sequence", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Knowledge" }));
    await user.click(
      await screen.findByRole("button", { name: "Snapshot & reset" }),
    );
    const dialog = screen.getByRole("dialog", {
      name: "Snapshot and reset knowledge?",
    });
    expect(within(dialog).getByText(/exact sequence/)).toHaveTextContent("2");
    await user.click(
      within(dialog).getByRole("button", {
        name: "Confirm snapshot and reset",
      }),
    );
    await waitFor(() => expect(recoveryRequests).toHaveLength(1));
    expect(recoveryRequests[0]).toMatchObject({
      action: "reset",
      session_id: "session-alpha",
      expected_sequence: 2,
      confirmed: true,
      snapshot_id: null,
    });
  });

  it("sends operator guidance only to the selected live session", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("textbox", {
        name: "Open the agent control dialog",
      }),
    );
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
    const evidenceLinks = await screen.findAllByRole("button", {
      name: /Open evidence:/,
    });
    await user.click(evidenceLinks[0]);
    const dialog = screen.getByRole("dialog", {
      name: "Ask or search evidence",
    });
    await user.click(within(dialog).getByRole("tab", { name: /Truth/ }));
    expect(
      within(dialog).getByText(
        "Observer truth is not configured for this live session.",
      ),
    ).toBeVisible();
    expect(within(dialog).getByText("missing")).toBeVisible();
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
    expect(screen.getByRole("button", { name: "Session" }))
      .toHaveTextContent("stopped · 2 events");
    expect(screen.getByRole("textbox", {
      name: "Open the agent control dialog",
    }))
      .toBeDisabled();
  });

  it("reopens a verified incident without polling live sources", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("region", { name: "Live cockpit" });
    await user.click(screen.getByRole("button", { name: "Sessions" }));
    const payload = offlineIncidentPayload();
    const file = new File([
      JSON.stringify({
        kind: "boukensha.observatory.incident",
        version: 2,
        digest: await digest(payload),
        payload,
      }),
    ], "incident.json", { type: "application/json" });
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;

    await user.upload(input, file);

    const offlineBadge = await screen.findByText("offline capsule");
    expect(offlineBadge).toBeVisible();
    expect(offlineBadge).toHaveAttribute(
      "title",
      "Sanitized incident capsule · integrity verified",
    );
    expect(screen.getByRole("combobox", { name: "Player" })).toHaveValue(
      "offline-player",
    );
    expect(screen.queryByRole("button", { name: "Ask why" }))
      .not.toBeInTheDocument();
    const callsAfterOpen = vi.mocked(fetch).mock.calls.length;
    await new Promise((resolve) => window.setTimeout(resolve, 2_100));
    expect(vi.mocked(fetch).mock.calls).toHaveLength(callsAfterOpen);
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
    objective_initial: {
      title: `Explore as ${player}`,
      clue: null,
      source_kind: "operator",
      revision: 1,
      evidence: "agent log line 1",
    },
    objective_context: {
      title: `Explore as ${player}`,
      clue: null,
      source_kind: "operator",
      revision: 1,
      evidence: "agent log line 1",
    },
    suggested_action: null,
    recent_path: null,
    agent_thought: null,
    agent_belief: live
      ? {
        text: "Moving east toward the retained objective through the learned route",
        phase: "tool_call",
        observed_at: "2026-07-30T08:01:00Z",
        line: 7,
        evidence: "agent log line 7",
      }
      : null,
    model: "test-model",
    tools: ["look", "move"],
    turn: 1,
    iteration: 1,
    context_limit: 200_000,
    current_room: title,
    zone: null,
    position_confidence: "high",
    position_method: "room-id",
    combat: false,
    combat_episode: null,
    vitals: { hit: 100, mana: 80, move: 90 },
    player_status: {
      fields: {},
      capture_gaps: [],
    },
    cost_usd: player === "alpha" ? 0.01 : 0.02,
    current_turn_cost_usd: player === "alpha" ? 0.01 : 0.02,
    spend_cap_usd: 0.5,
    spend_cap_scope: "session",
    economics: [],
    room_economics: [],
    unattributed_room_economics: null,
    usage: { fresh_input: 100, cache_read: 0, cache_write: 0, output: 10 },
    milestones: [],
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
    world: {
      nodes: [{
        id: `place-${player}`,
        place: player === "alpha" ? 3001 : 4001,
        title,
        exits: ["north"],
        mobs: [],
        objects: [],
        visits: 1,
        evidence: [2],
        first_seq: 2,
        last_seq: 2,
        state: "current",
        confidence: "high",
        method: "room-id",
      }],
      edges: [],
      current_title: title,
      current_confidence: "high",
      candidates: [],
      candidate_details: [],
      duplicate_titles: [],
      objective_beacons: [],
      frontier: [],
      parse_miss_rate: 0,
      parse_misses: [],
      unknown_positions: 0,
    },
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

async function digest(value: unknown): Promise<string> {
  const buffer = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(JSON.stringify(value)),
  );
  return [...new Uint8Array(buffer)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function offlineIncidentPayload() {
  return {
    generated_at: "2026-07-30T12:00:00Z",
    title: "Offline J2 incident",
    player_id: "offline-player",
    source_versions: { capsule: "2", repository: "test" },
    investigation: {
      version: 1,
      source_kind: "experiment_sample",
      correlation: "Portable recorded evidence.",
      run: {
        id: "offline-run",
        label: "J2 · offline",
        journey: "J2",
        attempt: "offline",
        success: false,
        stop_reason: "completed",
        iterations: 1,
        cost_usd: 0.01,
        result_mode: "full",
      },
      player_id: "offline-player",
      agent_session_id: "agent-offline",
      gateway_session_id: "gateway-offline",
      objective: "Find the minotaur",
      model: "recorded-model",
      records: [{
        id: "gateway:4",
        parent_id: null,
        source: "gateway",
        form: "parsed",
        kind: "observation",
        label: "Observed Temple",
        sequence: 4,
        at: "2026-07-30T12:00:00Z",
        trace_id: "trace-offline",
        iteration: 1,
        turn: 1,
        room_id: "place:1",
        duration_ms: 0,
        cost_usd: 0,
        tokens: 0,
        status: "complete",
        preview: "Temple",
        fields: { title: "Temple" },
        source_ref: "gateway event 4",
        capture_gaps: [],
      }],
      diagnostics: [],
      diagnostic_coverage: [],
      lens: Object.fromEntries(
        ["wire", "parsed", "rendered", "believed", "truth"].map((form) => [
          form,
          {
            state: form === "parsed" ? "available" : "missing",
            title: form,
            text: form === "parsed" ? "Temple" : "Not retained",
            citations: form === "parsed" ? ["gateway:4"] : [],
          },
        ]),
      ),
      world: {
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
      },
      cost: {
        total_usd: 0,
        response_total_usd: 0,
        raw_response_total_usd: 0,
        reconciliation_delta_usd: 0,
        complete: false,
        completeness_detail: "Complete through the selected prefix.",
        fresh_input_tokens: 0,
        cache_read_tokens: 0,
        cache_write_tokens: 0,
        output_tokens: 0,
        points: [],
      },
      capture_gaps: ["offline capsule is limited to its selected prefix"],
    },
    knowledge: {
      version: 1,
      player_id: "offline-player",
      state: "ready",
      source: "per-player durable knowledge",
      cdc_cursor: 0,
      metrics: [],
      assertions: [],
      changes: [],
      snapshots: [],
      recoveries: [],
      capture_gaps: [],
    },
    history: {
      player_id: "offline-player",
      total_runs: 1,
      successful_runs: 0,
      failed_runs: 1,
      items: [],
    },
    selection: {
      selected_record_id: "gateway:4",
      diagnostic_id: null,
      lens: "evidence",
    },
    annotations: [],
    redaction: {
      policy: "credentials and local paths removed at export",
      replacements: 0,
      local_paths_included: false,
      credentials_included: false,
    },
  };
}
