import { describe, expect, it } from "vitest";
import type { SessionEvidenceRecord } from "../../data/recordedSession";
import { stepClass } from "./SessionsWorkspace";

function record(overrides: Partial<SessionEvidenceRecord>): SessionEvidenceRecord {
  return {
    id: "r1",
    parent_id: null,
    source: "agent",
    form: "parsed",
    kind: "response",
    label: "Model call",
    sequence: 1,
    at: "2026-07-30T00:00:00Z",
    trace_id: null,
    iteration: 1,
    turn: 1,
    room_id: null,
    duration_ms: 10,
    cost_usd: 0,
    tokens: 0,
    status: "complete",
    preview: "",
    fields: {},
    source_ref: "agent.jsonl:1",
    capture_gaps: [],
    ...overrides,
  } as SessionEvidenceRecord;
}

describe("stepClass", () => {
  it("maps plan and reasoning records to the plan step", () => {
    expect(stepClass(record({ kind: "plan" }))).toBe("kplan");
    expect(stepClass(record({ kind: "reasoning" }))).toBe("kplan");
  });

  it("maps gateway records to the tool step", () => {
    expect(stepClass(record({ source: "gateway", kind: "command" }))).toBe("ktool");
  });

  it("maps context and memory records to the context step", () => {
    expect(stepClass(record({ kind: "context_injected" }))).toBe("kctx");
    expect(stepClass(record({ kind: "memory" }))).toBe("kctx");
  });

  it("defaults agent responses to the model step", () => {
    expect(stepClass(record({ kind: "response" }))).toBe("kmodel");
  });
});
