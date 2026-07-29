import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import type { Investigation } from "../data/investigation";
import { IncidentWorkflow } from "./IncidentWorkflow";

const investigation = {
  run: {
    id: "run-1",
    label: "J2 · failed",
    journey: "J2",
    attempt: "a1",
    success: false,
    stop_reason: "completed",
    iterations: 2,
    cost_usd: 0.02,
    result_mode: "full",
  },
  events: [],
  diagnostics: [],
  citations: [],
  lens: {},
  world: {
    nodes: [],
    edges: [],
    current_title: null,
    current_confidence: "unknown",
    candidates: [],
    parse_miss_rate: 0,
    unknown_positions: 0,
  },
} as unknown as Investigation;

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(
        url.includes("knowledge")
          ? {
            state: "partial",
            source: "Recorded run projection",
            metrics: [{
              label: "Known places",
              value: 57,
              detail: "Distinct places",
            }],
            frontier: [{
              id: "p1:north",
              title: "Nexus · north",
              kind: "untraversed_exit",
              detail: "Observed exit with no recorded traversal.",
              citations: [],
            }],
            entities: [],
            player: {},
            progression: [],
            missing_layers: ["entities", "player"],
          }
          : {
            total_runs: 30,
            successful_runs: 20,
            failed_runs: 10,
            items: [{
              kind: "confusion_loop",
              runs: 8,
              critical: 0,
              warning: 8,
              notice: 0,
              latest_run: "J2",
            }],
          },
      ),
    } as Response);
  }));
});

test("keeps investigator notes separate from evidence and visible in handoff", async () => {
  const user = userEvent.setup();
  render(
    <IncidentWorkflow
      open
      investigation={investigation}
      runId="run-1"
      selected={42}
      diagnosticId="confusion-loop"
      capsule={null}
      onClose={vi.fn()}
      onOpenCapsule={vi.fn()}
    />,
  );

  expect(screen.getByText("Read-only evidence")).toBeInTheDocument();
  expect(screen.getByText(/never change a diagnostic/i)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("57")).toBeInTheDocument());
  expect(screen.getByText("Nexus · north")).toBeInTheDocument();
  expect(screen.getByText("confusion loop")).toBeInTheDocument();

  await user.type(
    screen.getByPlaceholderText("Add context at sequence 42"),
    "The agent may have mistaken a revisit for progress.",
  );
  await user.click(screen.getByRole("button", { name: "Add note" }));

  expect(
    screen.getByText("The agent may have mistaken a revisit for progress."),
  ).toBeInTheDocument();
  expect(window.localStorage.getItem("boukensha:annotations:run-1"))
    .toContain("mistaken a revisit");
});
