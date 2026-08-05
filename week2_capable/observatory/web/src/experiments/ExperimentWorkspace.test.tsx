// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { ExperimentComparison } from "../contracts";
import { ExperimentWorkspace } from "./ExperimentWorkspace";

const comparison: ExperimentComparison = {
  id: "j1-rendering-n10",
  title: "J1 model-facing result rendering",
  journey: "J1",
  definition: {
    id: "j1-rendering",
    version: 1,
    title: "Result rendering",
    objective: "Measure journey behavior and cost.",
    success_predicate: "The bakery and bread menu are observed.",
    journey: "J1",
    starting_state: "Temple level 1",
    reset_strategy: "Verified reset before every sample",
    reset_identity: "level1-temple@1",
    arms: [
      { id: "raw", label: "Raw", values: { "render.mode": "raw" } },
      { id: "full", label: "Full", values: { "render.mode": "full" } },
    ],
    repetitions_per_arm: 1,
    per_sample_spend_ceiling_usd: 0.6,
    stop: {
      success_target: 2,
      verified_predicate_required: true,
      max_iterations_per_sample: 60,
      max_wall_seconds_per_sample: 900,
      max_total_cost_usd: 1.2,
      operator_stop_enabled: true,
    },
    effective_max_spend_usd: 1.2,
    source: "imported_evidence",
    parent_definition_id: null,
    changed_feature: null,
  },
  registry: [{
    id: "render.mode",
    label: "Model-facing result",
    group: "rendering",
    kind: "enum",
    description: "Shapes the same evidence for the model.",
    default: "full",
    options: ["raw", "full"],
    minimum: null,
    maximum: null,
    source: "gateway result-mode contract",
    execution_supported: true,
  }, {
    id: "memory.enabled",
    label: "Persistent knowledge",
    group: "memory",
    kind: "boolean",
    description: "Makes retained player knowledge available.",
    default: true,
    options: [],
    minimum: null,
    maximum: null,
    source: "agent knowledge contract",
    execution_supported: false,
  }],
  validation: {
    valid: true,
    comparable: true,
    execution_available: false,
    paid_confirmation_required: true,
    issues: [],
    checks: ["Reset identity is versioned."],
  },
  cohorts: [{
    mode: "raw",
    samples: 1,
    successes: 1,
    cost_mean: 0.03,
    cost_median: 0.03,
    cost_stdev: 0,
    calls_mean: 13,
    calls_stdev: 0,
    invalid_calls: 0,
    corrective_calls: 0,
    tools: { move: 8 },
    attention: {
      fresh_tokens: 100,
      cache_read_tokens: 200,
      cache_write_tokens: 20,
      output_tokens: 30,
      result_chars: 400,
      schema_tokens: 1000,
      movement_share: 0.6,
    },
  }, {
    mode: "full",
    samples: 1,
    successes: 1,
    cost_mean: 0.031,
    cost_median: 0.031,
    cost_stdev: 0,
    calls_mean: 14,
    calls_stdev: 0,
    invalid_calls: 0,
    corrective_calls: 0,
    tools: { move: 8 },
    attention: {
      fresh_tokens: 110,
      cache_read_tokens: 190,
      cache_write_tokens: 20,
      output_tokens: 32,
      result_chars: 600,
      schema_tokens: 1000,
      movement_share: 0.57,
    },
  }],
  samples: [{
    run_id: "run-raw-1",
    mode: "raw",
    attempt: "20260730T010203Z",
    success: true,
    setup_failure: false,
    excluded: false,
    exclusion_reason: null,
    cost_usd: 0.03,
    turns: 1,
    calls: 13,
  }, {
    run_id: "run-full-1",
    mode: "full",
    attempt: "20260730T020304Z",
    success: true,
    setup_failure: false,
    excluded: false,
    exclusion_reason: null,
    cost_usd: 0.031,
    turns: 1,
    calls: 14,
  }],
  lanes: [{
    mode: "raw",
    attempt: "20260730T010203Z",
    success: true,
    cost_usd: 0.03,
    calls: 13,
    milestones: [{
      index: 1,
      kind: "observe",
      label: "Observe Temple",
      tool: "look",
      argument: null,
    }],
  }, {
    mode: "full",
    attempt: "20260730T020304Z",
    success: true,
    cost_usd: 0.031,
    calls: 14,
    milestones: [{
      index: 1,
      kind: "observe",
      label: "Observe Temple",
      tool: "look",
      argument: null,
    }],
  }],
  divergence: {
    index: 1,
    summary: "First semantic divergence at action 1",
    actions: { raw: "look", full: "look" },
  },
  counterfactuals: [{
    mode: "raw",
    observations: 13,
    bytes: 400,
    estimated_tokens: 100,
    delta_from_raw: 0,
  }],
  parser_counterfactuals: [{
    mode: "raw",
    frames: 10,
    recorded_version: "rules-1",
    replayed_version: "rules-2",
    recorded_lines: 20,
    recorded_typed: 15,
    replayed_lines: 20,
    replayed_typed: 17,
    recorded_miss_rate: 0.25,
    replayed_miss_rate: 0.15,
    typed_delta: 2,
  }],
  findings: [
    "Both policies completed the journey.",
    "Mean cost remained close.",
    "Variation is retained.",
  ],
};

describe("ExperimentWorkspace", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/experiments");
  });

  it("connects cohort evidence to exact sample sessions", async () => {
    const user = userEvent.setup();
    render(
      <ExperimentWorkspace
        comparison={comparison}
        jobs={[]}
        loading={false}
        error=""
      />,
    );

    expect(screen.getByText("$0.061000")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Samples/ }));

    expect(screen.getByText("2026-07-30 01:02:03 UTC")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open run" })[0])
      .toHaveAttribute("href", "/sessions?run=run-raw-1");
  });

  it("separates executable configuration from observe-only dimensions", async () => {
    const user = userEvent.setup();
    render(
      <ExperimentWorkspace
        comparison={comparison}
        jobs={[]}
        loading={false}
        error=""
      />,
    );

    await user.click(screen.getByRole("button", { name: /Definition/ }));

    expect(screen.getByText(/runner-supported/)).toBeInTheDocument();
    expect(screen.getByText(/observe only/)).toBeInTheDocument();
    expect(screen.getByText("Imported evidence only")).toBeInTheDocument();
  });

  it("keeps counterfactual replay explicitly model-free", async () => {
    const user = userEvent.setup();
    render(
      <ExperimentWorkspace
        comparison={comparison}
        jobs={[]}
        loading={false}
        error=""
      />,
    );

    await user.click(screen.getByRole("button", { name: /Replay/ }));

    expect(screen.getByText("No model call")).toBeInTheDocument();
    expect(screen.getByText("+2 typed lines")).toBeInTheDocument();
  });
});
