import { describe, expect, it } from "vitest";
import { matchesInvestigationQuery, type InvestigationEvent } from "./investigation";

const event: InvestigationEvent = {
  seq: 7,
  at: "now",
  phase: "tool_call",
  label: "move",
  cost_usd: 0,
  duration_ms: 0,
  parent: 6,
  citation: "agent:7",
  attributes: { tool: "tbamud__move", iteration: 3 },
};

describe("structured investigation search", () => {
  it("supports field filters and plain terms", () => {
    expect(matchesInvestigationQuery(event, "phase:tool_call tool:move")).toBe(true);
    expect(matchesInvestigationQuery(event, "iteration:3 move")).toBe(true);
    expect(matchesInvestigationQuery(event, "phase:response")).toBe(false);
  });
});
