import type { Page } from "@playwright/test";
import type { ComparisonMode, RunComparison } from "../src/data/comparison";

const modes: ComparisonMode[] = ["raw", "minimal", "full"];

export async function mockExperiment(page: Page) {
  await page.route("**/api/experiments/jobs", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ jobs: [] }),
    });
  });
  await page.route("**/api/comparisons/j1-rendering-n10", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture()),
    });
  });
  await page.route("**/api/experiments/fork", async (route) => {
    const request = route.request().postDataJSON() as {
      definition: RunComparison["definition"];
      arm_id: string;
      feature_id: string;
      value: boolean | number | string;
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...request.definition,
        id: `${request.definition.id}-fork-fixture`,
        version: request.definition.version + 1,
        source: "executable_definition",
        parent_definition_id: request.definition.id,
        changed_feature: `${request.arm_id}:${request.feature_id}`,
        arms: request.definition.arms.map((arm) => (
          arm.id === request.arm_id
            ? {
              ...arm,
              values: { ...arm.values, [request.feature_id]: request.value },
            }
            : arm
        )),
      }),
    });
  });
  await page.route("**/api/experiments/validate", async (route) => {
    const request = route.request().postDataJSON() as {
      definition: RunComparison["definition"];
    };
    const queue = request.definition.arms.flatMap((arm) => (
      Array.from(
        { length: request.definition.repetitions_per_arm },
        (_, index) => `${arm.id}-${String(index + 1).padStart(3, "0")}-fixture`,
      )
    ));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        validation: {
          valid: true,
          comparable: true,
          execution_available: false,
          paid_confirmation_required: true,
          issues: [],
          checks: ["Fixture validation passed."],
        },
        queue,
      }),
    });
  });
  await page.route("**/api/experiments/run", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: "execution_disabled",
        detail: "Experiment execution is disabled by local policy.",
      }),
    });
  });
}

export async function mockExperimentExecution(page: Page) {
  const sample = {
    id: "raw-001-fixture",
    arm_id: "raw",
    ordinal: 1,
    state: "running",
    run_id: null,
    cost_usd: null,
    turns: null,
    calls: null,
    detail: "Reset verified, sample process started",
    effective_config: { "render.mode": "raw" },
  };
  const job = {
    id: "job-fixture",
    player_profile: "alpha",
    definition: {
      ...fixture().definition,
      id: "j1-rendering-n10-definition-pilot",
      title: "Model-facing result rendering pilot",
      repetitions_per_arm: 1,
      effective_max_spend_usd: 1.8,
      source: "executable_definition",
      stop: {
        ...fixture().definition.stop,
        success_target: 3,
        max_total_cost_usd: 1.8,
      },
    },
    state: "running",
    confirmed_max_spend_usd: 1.8,
    spent_usd: 0,
    current_sample: sample.id,
    samples: [sample],
  };
  await page.unroute("**/api/experiments/run");
  await page.unroute("**/api/experiments/jobs");
  await page.route("**/api/experiments/jobs", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ jobs: [job] }),
    });
  });
  await page.route("**/api/experiments/run", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify(job),
    });
  });
  await page.route("**/api/experiments/jobs/job-fixture", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(job),
    });
  });
  await page.route("**/api/experiments/jobs/job-fixture/control", async (route) => {
    const request = route.request().postDataJSON() as { action: "stop" | "resume" };
    job.state = request.action === "stop" ? "stopped" : "running";
    sample.state = request.action === "stop" ? "queued" : "running";
    job.current_sample = request.action === "stop" ? null : sample.id;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(job),
    });
  });
}

export async function mockCompletedExperiment(page: Page) {
  const definition = {
    ...fixture().definition,
    id: "j1-rendering-completed-pilot",
    title: "Completed result rendering pilot",
    repetitions_per_arm: 1,
    effective_max_spend_usd: 1.8,
    source: "executable_definition",
    stop: {
      ...fixture().definition.stop,
      success_target: 3,
      max_total_cost_usd: 1.8,
    },
  };
  const samples = [
    completedSample("raw", "success", "raw-run-1", 0.12, 11, 17),
    completedSample("minimal", "agent_failure", "minimal-run-1", 0.14, 13, 19),
    completedSample("full", "setup_failure", null, 0.01, null, null),
  ];
  const job = {
    id: "completed-job-fixture",
    player_profile: "alpha",
    definition,
    state: "completed",
    confirmed_max_spend_usd: 1.8,
    spent_usd: 0.27,
    current_sample: null,
    samples,
  };
  await page.unroute("**/api/experiments/jobs");
  await page.route("**/api/experiments/jobs", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ jobs: [job] }),
    });
  });
}

function completedSample(
  arm: ComparisonMode,
  state: "success" | "agent_failure" | "setup_failure",
  runId: string | null,
  cost: number,
  turns: number | null,
  calls: number | null,
) {
  return {
    id: `${arm}-001-completed`,
    arm_id: arm,
    ordinal: 1,
    state,
    run_id: runId,
    cost_usd: cost,
    turns,
    calls,
    detail: state,
    effective_config: { "render.mode": arm },
  };
}

function fixture(): RunComparison {
  const shared = {
    "tools.profile": "direct-full",
    "model.id": "claude-haiku-4-5",
    "context.compaction_threshold": 0.85,
    "memory.enabled": true,
    "policy.max_iterations": 60,
  };
  const costs = { raw: 0.0312, minimal: 0.0298, full: 0.0321 };
  const calls = { raw: 23.8, minimal: 25.1, full: 23.6 };
  return {
    id: "j1-rendering-n10",
    title: "J1 model-facing result rendering",
    journey: "J1",
    definition: {
      id: "j1-rendering-n10-definition",
      version: 1,
      title: "Model-facing result rendering",
      objective: "Reach the bakery from the temple and buy a danish.",
      success_predicate: "A danish is present in the verified inventory.",
      journey: "J1",
      starting_state: "level1-temple@1",
      reset_strategy: "verified snapshot before every sample",
      reset_identity: "level1-temple@1",
      arms: modes.map((mode) => ({
        id: mode,
        label: `${mode[0].toUpperCase()}${mode.slice(1)} results`,
        values: { ...shared, "render.mode": mode },
      })),
      repetitions_per_arm: 10,
      per_sample_spend_ceiling_usd: 0.60,
      stop: {
        success_target: 30,
        verified_predicate_required: true,
        max_iterations_per_sample: 60,
        max_wall_seconds_per_sample: 900,
        max_total_cost_usd: 18,
        operator_stop_enabled: true,
      },
      effective_max_spend_usd: 18,
      source: "imported_evidence",
      parent_definition_id: null,
      changed_feature: null,
    },
    registry: [
      feature("render.mode", "Model-facing result", "rendering", "enum", "full", ["raw", "minimal", "full"], "gateway result-mode contract"),
      feature("tools.profile", "Gateway tool surface", "tools", "enum", "direct-full", ["direct-full", "direct-core"], "gateway surface registry"),
      feature("model.id", "Agent model", "model", "text", "claude-haiku-4-5", [], "agent model catalog"),
      feature("context.compaction_threshold", "Compaction threshold", "context", "number", 0.85, [], "agent task settings"),
      feature("memory.enabled", "Persistent knowledge", "memory", "boolean", true, [], "agent knowledge contract"),
      feature("policy.max_iterations", "Maximum turns", "policy", "integer", 60, [], "agent task limits"),
    ],
    validation: {
      valid: true,
      comparable: true,
      execution_available: false,
      paid_confirmation_required: true,
      issues: [],
      checks: [
        "Every sample belongs to journey J1.",
        "Each arm contains ten retained samples.",
        "Reset receipts are retained and non-empty.",
        "Gateway capability digests match across arms.",
        "Every included sample has priced usage.",
        "Setup failures remain separate from agent outcomes.",
      ],
    },
    cohorts: modes.map((mode) => ({
      mode,
      samples: 10,
      successes: 10,
      cost_mean: costs[mode],
      cost_median: costs[mode] - 0.001,
      cost_stdev: 0.008,
      calls_mean: calls[mode],
      calls_stdev: 4.2,
      invalid_calls: mode === "minimal" ? 1 : 0,
      corrective_calls: mode === "minimal" ? 3 : 1,
      tools: { look: 10, move: 180, shop: 10 },
      attention: {
        fresh_tokens: 12400,
        cache_read_tokens: mode === "full" ? 51000 : 48000,
        cache_write_tokens: 6200,
        output_tokens: 2100,
        result_chars: mode === "raw" ? 9200 : mode === "minimal" ? 13100 : 24800,
        schema_tokens: 3500,
        movement_share: 0.72,
      },
    })),
    samples: modes.flatMap((mode) => Array.from({ length: 10 }, (_, index) => ({
      run_id: `${mode}-run-${index + 1}`,
      mode,
      attempt: `20260729-${mode}-${String(index + 1).padStart(2, "0")}`,
      success: true,
      setup_failure: false,
      excluded: false,
      exclusion_reason: null,
      cost_usd: costs[mode] + (index - 5) * 0.0007,
      turns: 18 + index,
      calls: Math.round(calls[mode] + (index % 3)),
    }))),
    lanes: modes.map((mode) => ({
      mode,
      attempt: `20260729-${mode}-05`,
      success: true,
      cost_usd: costs[mode],
      calls: Math.round(calls[mode]),
      milestones: [
        { index: 1, kind: "observe", label: "look", tool: "look", argument: null },
        { index: 2, kind: "move", label: "move north", tool: "move", argument: "north" },
        { index: 3, kind: "move", label: mode === "minimal" ? "move south" : "move east", tool: "move", argument: mode === "minimal" ? "south" : "east" },
        { index: 4, kind: "outcome", label: "objective verified", tool: null, argument: null },
      ],
    })),
    divergence: {
      index: 3,
      summary: "Representative paths first disagree at semantic action 3.",
      actions: { raw: "move east", minimal: "move south", full: "move east" },
    },
    counterfactuals: modes.map((mode, index) => ({
      mode,
      observations: 24,
      bytes: [9200, 13100, 24800][index],
      estimated_tokens: [2300, 3275, 6200][index],
      delta_from_raw: [0, 0.42, 1.7][index],
    })),
    parser_counterfactuals: modes.map((mode) => ({
      mode,
      frames: 118,
      recorded_version: "rules-1",
      replayed_version: "rules-1",
      recorded_lines: 940,
      recorded_typed: 821,
      replayed_lines: 940,
      replayed_typed: mode === "minimal" ? 824 : 821,
      recorded_miss_rate: 0.126,
      replayed_miss_rate: mode === "minimal" ? 0.123 : 0.126,
      typed_delta: mode === "minimal" ? 3 : 0,
    })),
    findings: [
      "All three policies completed every reset-verified journey.",
      "Minimal used more model calls than raw.",
      "Cost differences overlap cohort variability.",
    ],
  };
}

function feature(
  id: string,
  label: string,
  group: "model" | "tools" | "rendering" | "memory" | "context" | "policy",
  kind: "boolean" | "enum" | "integer" | "number" | "text",
  value: boolean | number | string,
  options: string[],
  source: string,
) {
  return {
    id,
    label,
    group,
    kind,
    description: `${label} is supplied by ${source}.`,
    default: value,
    options,
    source,
  };
}
