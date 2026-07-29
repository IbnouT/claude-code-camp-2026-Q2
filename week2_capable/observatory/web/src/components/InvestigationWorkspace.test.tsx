import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Investigation } from "../data/investigation";
import { EvidenceLens } from "./EvidenceLens";
import { InvestigationDiagnostics } from "./InvestigationDiagnostics";
import { InvestigationWorkspace } from "./InvestigationWorkspace";

const investigation: Investigation = {
  run: {
    id: "r1",
    label: "J2 full",
    journey: "J2",
    attempt: "a1",
    success: false,
    stop_reason: "completed",
    iterations: 90,
    cost_usd: 0.21,
    result_mode: "full",
  },
  events: [{
    seq: 2,
    at: "now",
    phase: "response",
    label: "Model response",
    cost_usd: 0.01,
    duration_ms: 10,
    parent: null,
    citation: "agent:2",
    attributes: { iteration: 90 },
  }],
  diagnostics: [{
    id: "false-completion",
    kind: "false_completion",
    severity: "critical",
    title: "Run ended without satisfying its objective",
    detail: "The verified predicate remained false.",
    mechanism: "Completed turn plus failed outcome.",
    at: 2,
    evidence: ["agent:2", "benchmark:outcome"],
  }],
  citations: [
    {
      id: "agent:2",
      source: "agent",
      label: "Agent log line 2",
      sequence: 2,
      trace_id: null,
      excerpt: "I am done.",
    },
    {
      id: "benchmark:outcome",
      source: "benchmark",
      label: "Benchmark outcome",
      sequence: null,
      trace_id: null,
      excerpt: "success=false",
    },
  ],
  lens: {
    wire: { state: "available", title: "Wire", text: "2 refs", citations: [] },
    parsed: { state: "available", title: "Parsed", text: "Ambiguous", citations: [] },
    rendered: { state: "available", title: "Rendered", text: "Entrance", citations: [] },
    believed: {
      state: "available",
      title: "Believed",
      text: "I am done.",
      citations: ["agent:2"],
    },
    truth: {
      state: "available",
      title: "Truth",
      text: "Objective not satisfied.",
      citations: ["benchmark:outcome"],
    },
  },
};

describe("investigation workspace", () => {
  it("filters a causal trace with structured search", async () => {
    const user = userEvent.setup();
    render(
      <InvestigationWorkspace
        investigation={investigation}
        selected={2}
        onSelect={vi.fn()}
      />,
    );
    await user.type(
      screen.getByRole("textbox", { name: "Search causal evidence" }),
      "phase:response",
    );
    expect(screen.getByText("Clear · 1 matches")).toBeVisible();
  });

  it("connects a diagnostic to believed and verified evidence", async () => {
    const onDiagnostic = vi.fn();
    const onEvidence = vi.fn();
    const user = userEvent.setup();
    render(
      <>
        <EvidenceLens
          investigation={investigation}
          activeEvidence={["agent:2", "benchmark:outcome"]}
          onSelect={onEvidence}
        />
        <InvestigationDiagnostics
          diagnostics={investigation.diagnostics}
          selected="false-completion"
          onSelect={onDiagnostic}
        />
      </>,
    );
    expect(screen.getByText("I am done.")).toBeVisible();
    expect(screen.getByText("Objective not satisfied.")).toBeVisible();
    await user.click(screen.getByText("Run ended without satisfying its objective"));
    expect(onDiagnostic).toHaveBeenCalledWith(investigation.diagnostics[0]);
    await user.click(screen.getByText("Agent log line 2"));
    expect(onEvidence).toHaveBeenCalledWith(2);
  });
});
