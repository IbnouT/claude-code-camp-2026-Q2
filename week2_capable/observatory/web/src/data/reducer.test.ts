import { describe, expect, it } from "vitest";
import {
  assertCanonicalEventContract,
  type EventEnvelope,
} from "./contracts";
import {
  createEvidenceState,
  ingestEvidence,
  resumeLive,
  selectSequence,
  selectedProjection,
} from "./reducer";

function event(seq: number, kind: string, data: Record<string, unknown> = {}): EventEnvelope {
  return { seq, session: "s1", at: seq, kind, trace_id: null, data };
}

const evidence = [
  event(1, "observation", { kind: "room", title: "Temple", confidence: "high" }),
  event(2, "position", { title: "Temple", confidence: "tracked" }),
  event(3, "future_kind", { value: 7 }),
];

describe("deterministic evidence reducer", () => {
  it("refuses a canonical schema drift before consuming evidence", () => {
    expect(() => assertCanonicalEventContract({
      event: {
        additionalProperties: false,
        properties: {
          seq: {}, session: {}, at: {}, kind: {}, data: {},
        },
        required: ["seq", "session", "at", "kind", "data"],
      },
    })).toThrow(/incompatible/);
    expect(() => assertCanonicalEventContract({
      event: {
        additionalProperties: false,
        properties: {
          seq: {}, session: {}, at: {}, kind: {}, trace_id: {}, data: {},
        },
        required: ["seq", "session", "at", "kind", "data"],
      },
    })).not.toThrow();
  });

  it("produces the same projection from replay or incremental live delivery", () => {
    const replay = ingestEvidence(createEvidenceState("s1"), evidence);
    const live = evidence.reduce(
      (state, item) => ingestEvidence(state, [item]),
      createEvidenceState("s1"),
    );
    expect(live).toEqual(replay);
    expect(selectedProjection(live)).toEqual(selectedProjection(replay));
  });

  it("preserves unknown events and deduplicates at-least-once delivery", () => {
    const state = ingestEvidence(createEvidenceState("s1"), [...evidence, evidence[2]]);
    expect(state.events).toHaveLength(3);
    expect(state.unknownKinds).toEqual(["future_kind"]);
  });

  it("keeps a selected past prefix frozen while live evidence continues", () => {
    const atTwo = ingestEvidence(createEvidenceState("s1"), evidence.slice(0, 2));
    const paused = selectSequence(atTwo, 1);
    const updated = ingestEvidence(paused, [evidence[2]]);
    expect(updated.latestSeq).toBe(3);
    expect(updated.selectedSeq).toBe(1);
    expect(selectedProjection(updated).roomTitle).toBe("Temple");
    expect(resumeLive(updated).selectedSeq).toBe(3);
  });

  it("makes missing sequences explicit", () => {
    const state = ingestEvidence(
      createEvidenceState("s1"),
      [event(1, "login"), event(4, "status")],
    );
    expect(state.gaps).toEqual([{ first: 2, last: 3 }]);
  });
});
