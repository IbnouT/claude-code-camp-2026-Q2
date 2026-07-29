import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { RunComparison } from "../data/comparison";
import { CompareWorkspace } from "./CompareWorkspace";
import { ComparisonTimeline } from "./ComparisonTimeline";

const modes = ["raw", "minimal", "full"] as const;

const comparison: RunComparison = {
  id: "j1-rendering-n10",
  title: "J1 model-facing result rendering",
  journey: "J1",
  cohorts: modes.map((mode, index) => ({
    mode,
    samples: 10,
    successes: 10,
    cost_mean: [0.03, 0.04, 0.031][index],
    cost_median: [0.03, 0.04, 0.031][index],
    cost_stdev: 0.006,
    calls_mean: [13, 19.9, 13.8][index],
    calls_stdev: 2,
    invalid_calls: 0,
    corrective_calls: 0,
    tools: { move: [90, 157, 96][index] },
    attention: {
      fresh_tokens: 14000,
      cache_read_tokens: [40000, 90000, 57000][index],
      cache_write_tokens: 6000,
      output_tokens: 1000,
      result_chars: 4000,
      schema_tokens: 1500,
      movement_share: [0.69, 0.79, 0.7][index],
    },
  })),
  lanes: modes.map((mode) => ({
    mode,
    attempt: `${mode}-1`,
    success: true,
    cost_usd: 0.03,
    calls: 3,
    milestones: [
      {
        index: 1,
        kind: "observe",
        label: "look",
        tool: "look",
        argument: null,
      },
      {
        index: 2,
        kind: "move",
        label: mode === "minimal" ? "move south" : "move east",
        tool: "move",
        argument: mode === "minimal" ? "south" : "east",
      },
      {
        index: 3,
        kind: "outcome",
        label: "objective verified",
        tool: null,
        argument: null,
      },
    ],
  })),
  divergence: {
    index: 2,
    summary: "Representative paths first disagree at semantic action 2.",
    actions: { raw: "move east", minimal: "move south", full: "move east" },
  },
  counterfactuals: modes.map((mode, index) => ({
    mode,
    observations: 12,
    bytes: [4000, 4400, 6200][index],
    estimated_tokens: [1000, 1100, 1550][index],
    delta_from_raw: [0, 0.1, 0.55][index],
  })),
  parser_counterfactuals: modes.map((mode) => ({
    mode,
    frames: 12,
    recorded_version: "rules-1",
    replayed_version: "rules-1",
    recorded_lines: 100,
    recorded_typed: 90,
    replayed_lines: 100,
    replayed_typed: 90,
    recorded_miss_rate: 0.1,
    replayed_miss_rate: 0.1,
    typed_delta: 0,
  })),
  findings: ["Every mode completed every journey."],
};

describe("run comparison", () => {
  it("separates measured cohorts from same-evidence replay", () => {
    render(
      <CompareWorkspace comparison={comparison} selected={2} onSelect={vi.fn()} />,
    );
    expect(screen.getAllByText("10/10")).toHaveLength(3);
    expect(screen.getByText("Same evidence, three renderings")).toBeVisible();
    expect(screen.getByText("+55.0%", { exact: false })).toBeVisible();
    expect(screen.getByText("3/3 exact")).toBeVisible();
  });

  it("jumps and scrubs all lanes by semantic action", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <>
        <CompareWorkspace
          comparison={comparison}
          selected={1}
          onSelect={onSelect}
        />
        <ComparisonTimeline
          comparison={comparison}
          selected={1}
          onSelect={onSelect}
        />
      </>,
    );
    await user.click(screen.getByRole("button", { name: /First divergence/ }));
    expect(onSelect).toHaveBeenCalledWith(2);
    expect(screen.getAllByText("move east")).toHaveLength(2);
    expect(screen.getByText("move south")).toBeVisible();
  });
});
