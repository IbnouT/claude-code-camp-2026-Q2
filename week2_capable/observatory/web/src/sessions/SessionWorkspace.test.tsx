// @vitest-environment jsdom

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  SessionEvidenceRecord,
  SessionInvestigation,
} from "../contracts";
import { SessionsWorkspace } from "./SessionWorkspace";

function record(
  overrides: Partial<SessionEvidenceRecord>,
): SessionEvidenceRecord {
  return {
    id: "agent:1",
    parent_id: null,
    source: "agent",
    form: "rendered",
    kind: "session_start",
    label: "Session started",
    sequence: 1,
    at: "2026-08-01T01:00:00Z",
    trace_id: null,
    iteration: null,
    turn: null,
    room_id: null,
    duration_ms: 0,
    cost_usd: 0,
    tokens: 0,
    status: "complete",
    preview: "A retained event",
    fields: {},
    source_ref: "agent.jsonl line 1",
    capture_gaps: [],
    ...overrides,
  };
}

function investigation(): SessionInvestigation {
  const records = [
    record({}),
    record({
      id: "agent:2",
      kind: "surface_profile",
      label: "Capability surface",
      sequence: 2,
      fields: { advertised_tools: 7 },
    }),
    record({
      id: "agent:3",
      kind: "iteration",
      label: "Iteration 1",
      sequence: 3,
      at: "2026-08-01T01:00:01Z",
      iteration: 1,
      turn: 1,
    }),
    record({
      id: "agent:4",
      parent_id: "agent:3",
      kind: "prompt",
      label: "Model prompt",
      sequence: 4,
      at: "2026-08-01T01:00:01.100Z",
      iteration: 1,
      turn: 1,
      fields: {
        last_message: { role: "user", content: "Find the north gate." },
        message_count: 1,
        tool_count: 1,
      },
    }),
    record({
      id: "agent:5",
      parent_id: "agent:4",
      form: "believed",
      kind: "plan",
      label: "Agent plan",
      sequence: 5,
      at: "2026-08-01T01:00:01.200Z",
      iteration: 1,
      turn: 1,
      preview: "Orient in the world, then move north.",
      fields: { text: "Orient in the world, then move north." },
    }),
    record({
      id: "agent:6",
      parent_id: "agent:5",
      kind: "response",
      label: "Model response 1",
      sequence: 6,
      at: "2026-08-01T01:00:01.400Z",
      iteration: 1,
      turn: 1,
      duration_ms: 400,
      cost_usd: 0.007,
      tokens: 120,
      fields: {
        model: "claude-sonnet",
        stop_reason: "tool_use",
        usage: { input_tokens: 100, output_tokens: 20 },
      },
      preview: "(tool use: 1 call)",
    }),
    record({
      id: "agent:7",
      parent_id: "agent:6",
      kind: "tool_call",
      label: "Tool call · tbamud__command",
      sequence: 7,
      at: "2026-08-01T01:00:01.500Z",
      trace_id: "trace-1",
      iteration: 1,
      turn: 1,
      fields: { name: "tbamud__command", args: { command: "north" } },
    }),
    record({
      id: "gateway:8",
      parent_id: "agent:7",
      source: "gateway",
      form: "rendered",
      kind: "tool_call",
      label: "Gateway tool call",
      sequence: 8,
      at: "2026-08-01T01:00:01.510Z",
      trace_id: "trace-1",
      iteration: 1,
      turn: 1,
      source_ref: "gateway.db event 8",
    }),
    record({
      id: "gateway:9",
      parent_id: "gateway:8",
      source: "gateway",
      form: "wire",
      kind: "command",
      label: "MUD command",
      sequence: 9,
      at: "2026-08-01T01:00:01.520Z",
      trace_id: "trace-1",
      iteration: 1,
      turn: 1,
      preview: "north",
      fields: { text: "north" },
      source_ref: "gateway.db event 9",
    }),
    record({
      id: "gateway:10",
      parent_id: "gateway:9",
      source: "gateway",
      form: "wire",
      kind: "wire",
      label: "Wire in",
      sequence: 10,
      at: "2026-08-01T01:00:01.600Z",
      trace_id: "trace-1",
      iteration: 1,
      turn: 1,
      preview: "12 bytes received",
      fields: {
        bytes: 12,
        direction: "in",
        digest: "fixture-digest",
      },
      source_ref: "gateway.db event 10",
    }),
    record({
      id: "gateway:11",
      parent_id: "gateway:10",
      source: "gateway",
      form: "wire",
      kind: "wire_text",
      label: "Decoded wire text · in",
      sequence: 11,
      at: "2026-08-01T01:00:01.610Z",
      trace_id: "trace-1",
      iteration: 1,
      turn: 1,
      preview: "\u001b[33mA North Gate\u001b[0m",
      fields: {
        direction: "in",
        wire_seq: 10,
        encoding: "latin-1",
        ansi: "preserved",
        text: "\u001b[33mA North Gate\u001b[0m",
      },
      source_ref: "gateway.db event 11",
    }),
    record({
      id: "gateway:12",
      parent_id: "gateway:11",
      source: "gateway",
      form: "parsed",
      kind: "parser_input",
      label: "Normalized parser input",
      sequence: 12,
      at: "2026-08-01T01:00:01.620Z",
      trace_id: "trace-1",
      iteration: 1,
      turn: 1,
      preview: "A North Gate",
      fields: {
        encoding: "latin-1",
        parser_version: "rules-2",
        text: "A North Gate",
        transformations: ["remove_ansi_sgr", "trim_lines"],
      },
      source_ref: "gateway.db event 12",
    }),
    record({
      id: "gateway:13",
      parent_id: "gateway:12",
      source: "gateway",
      form: "parsed",
      kind: "observation",
      label: "Room observation",
      sequence: 13,
      at: "2026-08-01T01:00:01.630Z",
      trace_id: "trace-1",
      iteration: 1,
      turn: 1,
      room_id: "place:1",
      fields: { kind: "room", title: "A North Gate" },
      source_ref: "gateway.db event 13",
    }),
    record({
      id: "gateway:14",
      parent_id: "gateway:13",
      source: "gateway",
      form: "parsed",
      kind: "position",
      label: "Position observed",
      sequence: 14,
      at: "2026-08-01T01:00:01.640Z",
      trace_id: "trace-1",
      iteration: 1,
      turn: 1,
      room_id: "place:1",
      preview: "A North Gate",
      source_ref: "gateway.db event 14",
    }),
    record({
      id: "agent:15",
      parent_id: "agent:7",
      kind: "tool_result",
      label: "Tool result",
      sequence: 15,
      at: "2026-08-01T01:00:01.700Z",
      trace_id: "trace-1",
      iteration: 1,
      turn: 1,
      fields: {
        result: "A North Gate",
        stages: {
          mcp_result: "A North Gate",
          rendered_result: "A North Gate",
          model_input: "A North Gate",
        },
      },
    }),
    record({
      id: "agent:16",
      kind: "iteration",
      label: "Iteration 2",
      sequence: 16,
      at: "2026-08-01T01:00:02Z",
      iteration: 2,
      turn: 1,
    }),
    record({
      id: "agent:17",
      parent_id: "agent:16",
      form: "believed",
      kind: "plan",
      label: "Agent plan",
      sequence: 17,
      at: "2026-08-01T01:00:02.100Z",
      iteration: 2,
      turn: 1,
      preview: "Continue through the gate.",
      fields: { text: "Continue through the gate." },
    }),
    record({
      id: "agent:18",
      parent_id: "agent:17",
      kind: "response",
      label: "Model response 2",
      sequence: 18,
      at: "2026-08-01T01:00:02.400Z",
      iteration: 2,
      turn: 1,
      duration_ms: 300,
      cost_usd: 0.005,
      tokens: 90,
      fields: {
        model: "claude-sonnet",
        stop_reason: "end_turn",
        usage: { input_tokens: 80, output_tokens: 10 },
      },
      preview: "Reached the gate.",
    }),
    record({
      id: "gateway:19",
      parent_id: "agent:18",
      source: "gateway",
      form: "parsed",
      kind: "position",
      label: "Position observed",
      sequence: 19,
      at: "2026-08-01T01:00:02.500Z",
      iteration: 2,
      turn: 1,
      room_id: "place:2",
      preview: "Inside the Gate",
      source_ref: "gateway.db event 19",
    }),
  ];
  return {
    version: 1,
    source_kind: "runtime_session",
    correlation: "runtime:session-1",
    run: {
      id: "session-1",
      label: "Find the north gate",
      journey: "",
      attempt: "session-",
      success: true,
      stop_reason: "completed",
      iterations: 2,
      cost_usd: 0.012,
      result_mode: "",
      lifecycle: "completed",
      capture_status: "complete",
      created_at: "2026-08-01T01:00:00Z",
      ended_at: "2026-08-01T01:00:03Z",
      duration_ms: 3_000,
      turns: 1,
      responses: 2,
      goal_epochs: 1,
    },
    player_id: "poucet",
    agent_session_id: "session-1",
    gateway_session_id: "gateway-1",
    objective: "Find the north gate",
    model: "claude-sonnet",
    records,
    diagnostics: [],
    diagnostic_coverage: ["instrumentation_gap"],
    lens: {
      wire: { state: "available", title: "Wire", text: "Retained", citations: ["gateway:10"] },
      parsed: { state: "available", title: "Parsed", text: "Retained", citations: ["gateway:12"] },
      rendered: { state: "available", title: "Rendered", text: "Retained", citations: ["agent:4"] },
      believed: { state: "available", title: "Believed", text: "Retained", citations: ["agent:5"] },
      truth: { state: "missing", title: "Truth", text: "Missing", citations: [] },
    },
    world: {
      nodes: [
        {
          id: "place:1",
          place: 1,
          title: "A North Gate",
          description: null,
          exits: ["north"],
          mobs: [],
          objects: [],
          mob_sightings: [],
          object_sightings: [],
          visits: 1,
          evidence: [14],
          first_seq: 14,
          last_seq: 14,
          state: "observed",
          confidence: "tracked",
          method: "fixture",
        },
        {
          id: "place:2",
          place: 2,
          title: "Inside the Gate",
          description: null,
          exits: ["south"],
          mobs: [],
          objects: [],
          mob_sightings: [],
          object_sightings: [],
          visits: 1,
          evidence: [19],
          first_seq: 19,
          last_seq: 19,
          state: "current",
          confidence: "tracked",
          method: "fixture",
        },
      ],
      edges: [{
        id: "place:1:north:place:2",
        source: "place:1",
        target: "place:2",
        direction: "north",
        traversals: 1,
        evidence: [19],
      }],
      current_title: "Inside the Gate",
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
    cost: {
      total_usd: 0.012,
      response_total_usd: 0.012,
      raw_response_total_usd: 0.012,
      reconciliation_delta_usd: 0,
      complete: true,
      completeness_detail: "Sum of retained agent response costs.",
      fresh_input_tokens: 180,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
      output_tokens: 30,
      points: [
        {
          record_id: "agent:6",
          iteration: 1,
          cost_usd: 0.007,
          raw_response_cost_usd: 0.007,
          pricing_source: "agent_response",
          fresh_input_tokens: 100,
          cache_read_tokens: 0,
          cache_write_tokens: 0,
          output_tokens: 20,
          context_tokens: 100,
          progress: "response 1",
        },
        {
          record_id: "agent:18",
          iteration: 2,
          cost_usd: 0.005,
          raw_response_cost_usd: 0.005,
          pricing_source: "agent_response",
          fresh_input_tokens: 80,
          cache_read_tokens: 0,
          cache_write_tokens: 0,
          output_tokens: 10,
          context_tokens: 80,
          progress: "response 2",
        },
      ],
    },
    capture_gaps: [],
  };
}

function renderWorkspace(
  payload = investigation(),
  onSelectionChange = vi.fn(),
) {
  return render(
    <SessionsWorkspace
      error={null}
      incident={{
        annotations: [],
        sourceVersions: {},
        redactionPolicy: null,
        history: null,
      }}
      investigation={payload}
      loading={false}
      sourceState="recorded"
      onOpenRun={vi.fn()}
      onOpenSearch={vi.fn()}
      onSelectionChange={onSelectionChange}
    />,
  );
}

describe("SessionsWorkspace", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/sessions");
  });

  it("starts collapsed and opens one readable Story by selected goal", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    expect(screen.getByRole("heading", {
      level: 1,
      name: "Find the north gate",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Story" }))
      .toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: "Overview" }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Flow" }))
      .not.toBeInTheDocument();
    expect(screen.queryByText("Input available to the model"))
      .not.toBeInTheDocument();

    await user.click(screen.getByRole("button", {
      name: "Select Goal 1: Find the north gate",
    }));
    await user.click(screen.getByRole("button", { name: /^Turn 1/ }));

    expect(screen.getByText("Input available to the model"))
      .toBeInTheDocument();
    expect(screen.getByText("Agent plan")).toBeInTheDocument();
    expect(screen.getByText("Tool call · tbamud__command"))
      .toBeInTheDocument();
    expect(screen.getByText("MUD response")).toBeInTheDocument();
    expect(screen.getByText("Transformation and structured observation"))
      .toBeInTheDocument();
  });

  it("filters Story evidence with visible feedback and hides the control elsewhere", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    const filter = screen.getByRole("searchbox", {
      name: "Filter Story evidence",
    });
    await user.type(filter, "North Gate");

    expect(screen.getByRole("status")).toHaveTextContent(
      /matching iteration.*North Gate/i,
    );
    expect(screen.getByText("MUD response")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Map" }));
    expect(screen.queryByRole("searchbox", {
      name: "Filter Story evidence",
    })).not.toBeInTheDocument();
  });

  it("keeps historical capture gaps explicit in the story", () => {
    const payload = investigation();
    payload.capture_gaps = [
      "model_request_body_not_retained",
      "provider_response_body_not_retained",
    ];
    renderWorkspace(payload);

    expect(screen.getByText(
      "The exact assembled model request body was not retained for this historical run.",
    )).toBeInTheDocument();
    expect(screen.queryByText(
      "All required evidence forms report complete capture.",
    )).not.toBeInTheDocument();
  });

  it("uses the Live camera and map controls with natural replay states", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    await user.click(screen.getByRole("button", { name: "Map" }));

    expect(screen.getByRole("group", { name: "Map camera" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Follow" }))
      .toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("group", { name: "Map presentation" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Grow" }))
      .toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Zoom in" }))
      .toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reflow map" }))
      .not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous iteration" }))
      .toBeDisabled();
    expect(screen.getByRole("button", { name: "Play replay" }))
      .toBeEnabled();
    expect(screen.getByRole("button", { name: "Next iteration" }))
      .toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Next iteration" }));

    expect(screen.getByText("Turn 1 · Iteration 2 (2 of 2)"))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous iteration" }))
      .toBeEnabled();
    expect(screen.getByRole("button", { name: "Play replay" }))
      .toBeDisabled();
    expect(screen.getByRole("complementary", { name: "Map evidence legend" }))
      .toBeInTheDocument();
  });

  it("keeps repeated iteration numbers separate across goal turns", async () => {
    const user = userEvent.setup();
    const payload = investigation();
    payload.run.turns = 2;
    payload.run.goal_epochs = 2;
    payload.objective = "Practice at the warrior guild";
    payload.records = payload.records.map((item) => (
      item.sequence >= 16
        ? { ...item, turn: 2, iteration: 1 }
        : item
    ));
    payload.records.push(
      record({
        id: "operator:goal-1",
        parent_id: "agent:3",
        kind: "goal_revision",
        label: "Goal",
        sequence: 20,
        at: "2026-08-01T01:00:00.900Z",
        turn: 1,
        iteration: 1,
        preview: "Find the north gate",
        fields: {
          action: "revise",
          instruction: "Find the north gate",
        },
        source_ref: "operator-messages.json",
      }),
      record({
        id: "operator:goal-2",
        parent_id: "agent:16",
        kind: "goal_revision",
        label: "Goal",
        sequence: 21,
        at: "2026-08-01T01:00:01.900Z",
        turn: 2,
        iteration: 1,
        preview: "Practice at the warrior guild",
        fields: {
          action: "revise",
          instruction: "Practice at the warrior guild",
        },
        source_ref: "operator-messages.json",
      }),
      record({
        id: "operator:nudge-1",
        parent_id: "agent:16",
        kind: "guidance",
        label: "Nudge",
        sequence: 22,
        at: "2026-08-01T01:00:01.950Z",
        turn: 2,
        iteration: 1,
        preview: "Return through the western gate",
        fields: {
          action: "guide",
          instruction: "Return through the western gate",
        },
        source_ref: "operator-messages.json",
      }),
    );
    renderWorkspace(payload);

    expect(screen.getByRole("heading", {
      level: 2,
      name: "2 objectives shaped this session",
    })).toBeInTheDocument();
    const goalOne = screen.getByRole("region", {
      name: "Goal 1: Find the north gate",
    });
    const goalTwo = screen.getByRole("region", {
      name: "Goal 2: Practice at the warrior guild",
    });
    expect(within(goalOne).queryByRole("region", { name: "Turn 1" }))
      .not.toBeInTheDocument();
    expect(within(goalTwo).queryByRole("region", { name: "Turn 2" }))
      .not.toBeInTheDocument();

    await user.click(within(goalOne).getByRole("button", {
      name: "Select Goal 1: Find the north gate",
    }));
    expect(screen.getByRole("heading", {
      level: 1,
      name: "Find the north gate",
    })).toBeInTheDocument();
    expect(within(goalOne).getByRole("region", { name: "Turn 1" }))
      .toBeInTheDocument();

    await user.click(within(goalTwo).getByRole("button", {
      name: "Select Goal 2: Practice at the warrior guild",
    }));
    expect(screen.getByRole("heading", {
      level: 1,
      name: "Practice at the warrior guild",
    })).toBeInTheDocument();
    const turnTwo = within(goalTwo).getByRole("region", { name: "Turn 2" });
    const turnTwoToggle = within(turnTwo).getByRole("button", {
      name: /^Turn 2/,
    });
    // The heading names what started the turn, not every instruction inside it.
    expect(turnTwoToggle).toHaveAccessibleName(
      /Turn 2GoalPractice at the warrior guild/,
    );
    expect(turnTwoToggle).toHaveAttribute("aria-expanded", "false");

    await user.click(turnTwoToggle);
    expect(turnTwoToggle).toHaveAttribute("aria-expanded", "true");

    await user.click(turnTwoToggle);
    expect(turnTwoToggle).toHaveAttribute("aria-expanded", "false");

    await user.click(within(goalOne).getByRole("button", {
      name: "Select Goal 1: Find the north gate",
    }));
    expect(within(goalOne).queryByRole("region", { name: "Turn 1" }))
      .not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Map" }));
    expect(screen.getAllByText("Goal 1")).toHaveLength(1);
    expect(screen.getAllByText("Goal 2")).toHaveLength(1);

    const mapGoalOne = screen.getByRole("button", {
      name: "Jump to Goal 1: Find the north gate",
    });
    await user.click(mapGoalOne);
    expect(screen.getByText("Turn 1 · Iteration 1 (1 of 2)"))
      .toBeInTheDocument();
    expect(mapGoalOne).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("heading", {
      level: 1,
      name: "Find the north gate",
    })).toBeInTheDocument();

    await user.click(mapGoalOne);
    expect(mapGoalOne).toHaveAttribute("aria-expanded", "false");

    await user.click(screen.getByRole("button", {
      name: "Jump to Goal 2: Practice at the warrior guild",
    }));
    expect(screen.getByText("Turn 2 · Iteration 1 (2 of 2)"))
      .toBeInTheDocument();
    expect(screen.getByText(
      "Goal 2 · Practice at the warrior guild · 1 nudge active",
    )).toBeInTheDocument();
  });

  it("opens Story at the document start instead of following map selection", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    window.history.replaceState(
      null,
      "",
      "/sessions?view=map&iteration=2",
    );
    const user = userEvent.setup();
    renderWorkspace();
    scrollIntoView.mockClear();

    await user.click(screen.getByRole("button", { name: "Story" }));

    expect(screen.getByRole("button", { name: "Story" }))
      .toHaveAttribute("aria-current", "page");
    expect(scrollIntoView).not.toHaveBeenCalled();
    Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  });

  it("returns from an attributed cost point to its response story", async () => {
    const onSelectionChange = vi.fn();
    const user = userEvent.setup();
    renderWorkspace(investigation(), onSelectionChange);

    await user.click(screen.getByRole("button", { name: "Cost" }));
    expect(screen.getByRole("heading", {
      name: "$0.012000 across 2 model responses",
    })).toBeInTheDocument();
    const expensive = screen.getByRole("heading", {
      name: "Most expensive responses",
    }).closest("article");
    expect(expensive).not.toBeNull();
    await user.click(within(expensive as HTMLElement).getByRole("button", {
      name: /Iteration 1 · Model response/,
    }));

    expect(screen.getByRole("button", { name: "Story" }))
      .toHaveAttribute("aria-current", "page");
    expect(onSelectionChange).toHaveBeenLastCalledWith("agent:6");
    expect(screen.getByText("Model response")).toBeInTheDocument();
  });

  it("loads exact wire content only when requested", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        version: 1,
        record_id: "gateway:10",
        source_ref: "gateway.db event 10",
        timestamp: 0,
        direction: "in",
        digest: "fixture-digest",
        bytes: 12,
        redacted: false,
        content_base64: "QSBOb3J0aCBHYXRl",
        content_text: "A North Gate",
      }),
    } as Response));
    renderWorkspace();

    expect(fetch).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", {
      name: "Select Goal 1: Find the north gate",
    }));
    await user.click(screen.getByRole("button", { name: /^Turn 1/ }));
    await user.click(screen.getByText("Transport path and timing"));
    await user.click(screen.getByText(/Wire in · 12 bytes/));
    await user.click(screen.getByRole("button", {
      name: "Open exact socket content",
    }));

    expect((await screen.findAllByText("A North Gate")).length)
      .toBeGreaterThan(1);
    expect(fetch).toHaveBeenCalledWith(
      "/api/sessions/session-1/wire/10",
      { cache: "no-store" },
    );
  });

  it("reads the collapsed prompt preview from the last message", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    await user.click(screen.getByRole("button", {
      name: "Select Goal 1: Find the north gate",
    }));
    await user.click(screen.getByRole("button", { name: /^Turn 1/ }));

    expect(screen.getByText("Find the north gate.")).toBeInTheDocument();
    expect(screen.getByText("User")).toBeInTheDocument();
  });

  it("loads the withheld request body only when it is asked for", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        version: 1,
        record_id: "agent:4",
        source_ref: "agent.jsonl line 4",
        kind: "prompt",
        fields: {
          messages: [{ role: "user", content: "Find the north gate." }],
          tools: ["tbamud__command"],
        },
      }),
    } as Response));
    renderWorkspace();

    await user.click(screen.getByRole("button", {
      name: "Select Goal 1: Find the north gate",
    }));
    await user.click(screen.getByRole("button", { name: /^Turn 1/ }));
    await user.click(screen.getByText(
      "Exact model request, system prompt, messages, and tool schemas",
    ));

    expect(fetch).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", {
      name: "Open the exact body",
    }));

    expect(await screen.findByText("1 available tool")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/sessions/session-1/records/agent%3A4/fields",
      { cache: "no-store" },
    );
  });

  it("shows raw MUD, parser input, and delivered result as connected stages", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    await user.click(screen.getByRole("button", {
      name: "Select Goal 1: Find the north gate",
    }));
    await user.click(screen.getByRole("button", { name: /^Turn 1/ }));
    expect(screen.getByText("\u001b[33mA North Gate\u001b[0m"))
      .toBeInTheDocument();
    expect(screen.getByText("Parser input")).toBeInTheDocument();
    expect(screen.getByText("Typed observations and state"))
      .toBeInTheDocument();
    expect(screen.getByText("Result delivered upstream"))
      .toBeInTheDocument();
  });
});
