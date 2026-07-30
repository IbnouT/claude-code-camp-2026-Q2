import type { Page } from "@playwright/test";

const runId = "recorded-j2";

const records = [
  evidence("agent:1", null, "agent", "parsed", "session_start", 1, "Session start"),
  {
    ...evidence("agent:2", null, "agent", "rendered", "prompt", 2, "Objective prompt"),
    at: "2026-07-29T08:00:01Z",
    preview: "Find the Massive Minotaur.",
    fields: { task: "Find the Massive Minotaur." },
  },
  {
    ...evidence("agent:3", null, "agent", "believed", "response", 3, "Model response"),
    at: "2026-07-29T08:00:02Z",
    iteration: 1,
    turn: 1,
    cost_usd: 0.004,
    preview: "I found the entrance, but not the Massive Minotaur.",
  },
  {
    ...evidence("agent:4", "agent:3", "agent", "believed", "tool_call", 4, "Tool call: move"),
    at: "2026-07-29T08:00:03Z",
    trace_id: "trace-1",
    iteration: 1,
    turn: 1,
  },
  {
    ...evidence("gateway:1", "agent:4", "gateway", "wire", "wire", 1, "Wire"),
    at: "2026-07-29T08:00:04Z",
    trace_id: "trace-1",
    fields: { direction: "in", bytes: 84, digest: "evidence-digest" },
  },
  {
    ...evidence("gateway:2", "gateway:1", "gateway", "parsed", "position", 2, "Position: Newbie Entrance"),
    at: "2026-07-29T08:00:05Z",
    trace_id: "trace-1",
    room_id: "place:10",
    fields: { place: 10, title: "Newbie Entrance", confidence: "tracked" },
  },
  {
    ...evidence("agent:5", "agent:4", "agent", "parsed", "tool_result", 5, "Tool result"),
    at: "2026-07-29T08:00:06Z",
    trace_id: "trace-1",
    iteration: 1,
    turn: 1,
  },
  {
    ...evidence("agent:6", null, "agent", "believed", "response", 6, "Model response, end_turn"),
    at: "2026-07-29T08:00:07Z",
    iteration: 2,
    turn: 2,
    cost_usd: 0.006,
    preview: "The journey is complete.",
  },
  {
    ...evidence("benchmark:outcome", null, "benchmark", "truth", "outcome", 1, "Verified objective not satisfied"),
    at: "",
    status: "failed",
    preview: "The Massive Minotaur was never observed.",
    fields: { journey_id: "J2", success: false, stop_reason: "completed" },
  },
];

const investigation = {
  version: 1,
  source_kind: "experiment_sample",
  correlation: "This recorded session is linked by its attempt ledger.",
  run: {
    id: runId,
    label: "J2 · full · a1",
    journey: "J2",
    attempt: "a1",
    success: false,
    stop_reason: "completed",
    iterations: 2,
    cost_usd: 0.01,
    result_mode: "full",
  },
  player_id: "poucet-recorded",
  agent_session_id: "agent-j2",
  gateway_session_id: "gateway-j2",
  objective: "Travel north and find the Massive Minotaur.",
  model: "claude-haiku-4-5",
  records,
  diagnostics: [{
    id: "false-completion",
    kind: "false_completion",
    severity: "critical",
    state: "open",
    title: "The run ended before the objective was verified",
    consequence: "A completed model turn was treated as a completed journey.",
    rule_version: "sessions-1",
    threshold: "stop reason completed and verified outcome false",
    at_record: "agent:6",
    evidence: ["agent:6", "benchmark:outcome"],
    alternatives: ["The final observation may be missing"],
    affected_conclusions: ["Journey completion"],
    resolution: null,
    related_occurrences: [],
  }],
  diagnostic_coverage: [
    "false_completion",
    "belief_divergence",
    "position_ambiguity",
    "confusion_loop",
    "progress_stall",
    "parse_degradation",
    "corrective_call_cluster",
    "stale_action",
    "context_churn",
    "instrumentation_gap",
  ],
  lens: {
    wire: lens("available", "Exact wire", "84 inbound bytes", ["gateway:1"]),
    parsed: lens("available", "Parsed state", "Newbie Entrance", ["gateway:2"]),
    rendered: lens("available", "Model context", "Find the Massive Minotaur.", ["agent:2"]),
    believed: lens("available", "Agent belief", "The journey is complete.", ["agent:6"]),
    truth: lens("available", "Observer truth", "Objective not satisfied.", ["benchmark:outcome"]),
  },
  world: {
    nodes: [
      {
        id: "place:10",
        place: 10,
        title: "Newbie Entrance",
        exits: ["north", "west"],
        mobs: ["newbie guard"],
        objects: ["wooden sign"],
        visits: 1,
        evidence: [2],
        first_seq: 2,
        last_seq: 2,
        state: "observed",
        confidence: "tracked",
        method: "position evidence",
      },
      {
        id: "place:11",
        place: 11,
        title: "White Square",
        exits: ["south", "east"],
        mobs: [],
        objects: [],
        visits: 1,
        evidence: [2],
        first_seq: 2,
        last_seq: 2,
        state: "candidate",
        confidence: "ambiguous",
        method: "duplicate-title",
      },
      {
        id: "place:12",
        place: 12,
        title: "White Square",
        exits: ["south", "west"],
        mobs: [],
        objects: [],
        visits: 2,
        evidence: [2],
        first_seq: 2,
        last_seq: 2,
        state: "candidate",
        confidence: "ambiguous",
        method: "duplicate-title",
      },
    ],
    edges: [{
      id: "10:12:north",
      source: "place:10",
      target: "place:12",
      direction: "north",
      traversals: 1,
      evidence: [2],
    }],
    current_title: "White Square",
    current_confidence: "ambiguous",
    candidates: ["place:11", "place:12"],
    candidate_details: [
      {
        node_id: "place:11",
        title: "White Square",
        supporting_exits: ["south"],
        conflicting_exits: ["east", "west"],
        reason: "The title matches, while part of the retained exit signature conflicts.",
        evidence: [2],
      },
      {
        node_id: "place:12",
        title: "White Square",
        supporting_exits: ["south", "west"],
        conflicting_exits: [],
        reason: "The title and complete exit signature both match.",
        evidence: [2],
      },
    ],
    duplicate_titles: [{
      title: "White Square",
      node_ids: ["place:11", "place:12"],
    }],
    objective_beacons: [],
    parse_miss_rate: 0,
    parse_misses: [],
    unknown_positions: 1,
  },
  cost: {
    total_usd: 0.01,
    response_total_usd: 0.01,
    raw_response_total_usd: 0.003,
    reconciliation_delta_usd: 0,
    complete: true,
    completeness_detail: "Every response reconciles to the retained cost curve.",
    fresh_input_tokens: 600,
    cache_read_tokens: 1_400,
    cache_write_tokens: 200,
    output_tokens: 120,
    points: [
      costPoint("agent:3", 1, 0.004, 420),
      costPoint("agent:6", 2, 0.006, 1_980),
    ],
  },
  capture_gaps: [],
};

export async function mockRecorded(page: Page) {
  await page.route("**/api/recorded-sessions", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 1,
        players: [{ id: "poucet-recorded", label: "poucet · recorded" }],
        sessions: [{
          id: runId,
          source_kind: "experiment_sample",
          player_id: "poucet-recorded",
          label: "J2 · full · a1",
          journey: "J2",
          attempt: "a1",
          success: false,
          stop_reason: "completed",
          iterations: 2,
          cost_usd: 0.01,
          result_mode: "full",
        }],
      }),
    });
  });
  await page.route(`**/api/recorded-sessions/${runId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(investigation),
    });
  });
  await page.route("**/api/ask", async (route) => {
    const request = route.request().postDataJSON() as {
      scope: {
        space: "sessions";
        run_id: string;
        selected_record_id?: string;
      };
    };
    const early = request.scope.selected_record_id === "agent:1";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        tier: "deterministic",
        question: "Why did the agent stop?",
        query: {
          version: 1,
          operation: "diagnose_stop",
          scope: request.scope,
          filters: [],
          order: "causal",
          limit: 25,
        },
        scope_record_id: request.scope.selected_record_id ?? null,
        plan: [{
          operation: "diagnose_stop",
          source: "benchmark",
          detail: "Join the final claim to its explicitly linked outcome.",
        }],
        answer: early
          ? "At this moment, no final response was retained."
          : "The linked objective predicate remained false.",
        claims: early ? [] : [{
          text: "The objective was not satisfied.",
          confidence: "high",
          citations: ["benchmark:outcome"],
        }],
        citations: early ? [] : [{
          id: "benchmark:outcome",
          source: "benchmark",
          label: "Verified objective outcome",
          sequence: null,
          trace_id: null,
          excerpt: "success=false, stop_reason=completed",
        }],
        missing: early ? ["final response at selected moment"] : [],
        model_cost_usd: 0,
        model_input_tokens: 0,
        model_output_tokens: 0,
        model_summary: null,
        model_summary_citations: [],
      }),
    });
  });
}

function evidence(
  id: string,
  parent_id: string | null,
  source: "agent" | "gateway" | "benchmark",
  form: "wire" | "parsed" | "rendered" | "believed" | "truth",
  kind: string,
  sequence: number,
  label: string,
) {
  return {
    id,
    parent_id,
    source,
    form,
    kind,
    label,
    sequence,
    at: "2026-07-29T08:00:00Z",
    trace_id: null,
    iteration: null,
    turn: null,
    room_id: null,
    duration_ms: 0,
    cost_usd: 0,
    tokens: 0,
    status: "complete",
    preview: label,
    fields: { kind },
    source_ref: `${source} record ${sequence}`,
    capture_gaps: [],
  };
}

function lens(
  state: "available" | "missing",
  title: string,
  text: string,
  citations: string[],
) {
  return { state, title, text, citations };
}

function costPoint(
  record_id: string,
  iteration: number,
  cost_usd: number,
  context_tokens: number,
) {
  return {
    record_id,
    iteration,
    cost_usd,
    raw_response_cost_usd: cost_usd / 3,
    pricing_source: "attempt_cost_curve",
    fresh_input_tokens: 200,
    cache_read_tokens: context_tokens - 200,
    cache_write_tokens: 0,
    output_tokens: 60,
    context_tokens,
    progress: "Open contributing evidence",
  };
}
