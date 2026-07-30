import { describe, expect, it } from "vitest";
import type { SessionEvidenceRecord } from "../../data/recordedSession";
import { nextReplayIndex, orderRecords } from "./SessionsWorkspace";

const records: SessionEvidenceRecord[] = [
  record("agent:2", "2026-07-30T09:00:02Z", 2, 2, "response"),
  record("gateway:1", "2026-07-30T09:00:01Z", 1, 1, "position"),
  record("agent:1", "2026-07-30T09:00:00Z", 1, 1, "session_start"),
  record("gateway:2", "2026-07-30T09:00:03Z", 2, 2, "wire"),
];

describe("recorded session replay", () => {
  it("orders agent and gateway evidence on one retained clock", () => {
    expect(orderRecords(records).map((item) => item.id)).toEqual([
      "agent:1",
      "gateway:1",
      "agent:2",
      "gateway:2",
    ]);
  });

  it("steps by event, turn, and milestone without crossing the run", () => {
    const ordered = orderRecords(records);
    expect(nextReplayIndex(ordered, 0, "event", 1)).toBe(1);
    expect(nextReplayIndex(ordered, 0, "turn", 1)).toBe(2);
    expect(nextReplayIndex(ordered, 0, "milestone", 1)).toBe(1);
    expect(nextReplayIndex(ordered, 3, "event", 1)).toBe(3);
    expect(nextReplayIndex(ordered, 0, "event", -1)).toBe(0);
  });
});

function record(
  id: string,
  at: string,
  sequence: number,
  turn: number,
  kind: string,
): SessionEvidenceRecord {
  return {
    id,
    parent_id: null,
    source: id.startsWith("gateway") ? "gateway" : "agent",
    form: kind === "wire" ? "wire" : "parsed",
    kind,
    label: kind,
    sequence,
    at,
    trace_id: null,
    iteration: turn,
    turn,
    room_id: kind === "position" ? "room:temple" : null,
    duration_ms: 0,
    cost_usd: 0,
    tokens: 0,
    status: "complete",
    preview: kind,
    fields: {},
    source_ref: `${id}.jsonl`,
    capture_gaps: [],
  };
}
