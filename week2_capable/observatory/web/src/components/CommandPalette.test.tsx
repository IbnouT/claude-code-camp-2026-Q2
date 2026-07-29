import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommandPalette } from "./CommandPalette";

afterEach(() => vi.unstubAllGlobals());

describe("grounded investigation palette", () => {
  it("shows the query plan and cited claims returned by the read API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        tier: "deterministic",
        question: "Why did the agent stop?",
        plan: [{
          operation: "diagnose_stop",
          source: "benchmark",
          detail: "Join the final claim to the verified outcome.",
        }],
        answer: "The turn completed while the journey predicate stayed false.",
        claims: [{
          text: "The objective remained unmet.",
          confidence: "high",
          citations: ["benchmark:outcome"],
        }],
        citations: [{
          id: "benchmark:outcome",
          source: "benchmark",
          label: "Benchmark outcome",
          sequence: null,
          trace_id: null,
          excerpt: "success=false",
        }],
        missing: [],
        model_cost_usd: 0,
      }),
    }));
    const user = userEvent.setup();
    render(
      <CommandPalette
        open
        onClose={vi.fn()}
        runId="run-1"
        comparisonId="compare-1"
        onOpenCitation={vi.fn()}
      />,
    );

    await user.click(screen.getByText("Why did the agent stop?"));

    expect(screen.getByText("Visible query plan")).toBeVisible();
    expect(screen.getByText("diagnose stop")).toBeVisible();
    expect(screen.getByText("The objective remained unmet.")).toBeVisible();
    expect(screen.getByText("Benchmark outcome")).toBeVisible();
    expect(screen.getByText("$0.0000 model spend")).toBeVisible();
  });
});
