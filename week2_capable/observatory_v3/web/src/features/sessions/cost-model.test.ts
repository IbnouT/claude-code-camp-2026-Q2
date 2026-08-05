import { describe, expect, it } from "vitest"

import type { SessionInvestigation } from "@/data/session-investigation"

import {
  attributeCostPoints,
  barHeight,
  formatTimestamp,
  maximumCost,
  rankByCost,
  signedUsd,
  tokenShare,
  tokenTotal,
  usd,
  type AttributedCostPoint,
} from "./cost-model"

type SessionCostPoint = SessionInvestigation["cost"]["points"][number]
type SessionEvidenceRecord = SessionInvestigation["records"][number]

function point(recordId: string, costUsd: number): SessionCostPoint {
  return {
    record_id: recordId,
    iteration: 1,
    cost_usd: costUsd,
    raw_response_cost_usd: costUsd,
    pricing_source: "agent_response",
    fresh_input_tokens: 10,
    cache_read_tokens: 20,
    cache_write_tokens: 5,
    output_tokens: 15,
    context_tokens: 50,
    progress: "1/2",
  }
}

function record(id: string, turn: number): SessionEvidenceRecord {
  return {
    at: "2026-08-04T15:00:00Z",
    capture_gaps: [],
    cost_usd: 0,
    duration_ms: 0,
    form: "wire",
    id,
    iteration: 1,
    kind: "response",
    label: "Model response",
    parent_id: null,
    preview: "",
    room_id: null,
    sequence: 1,
    source: "agent",
    source_ref: "agent.jsonl line 1",
    status: "complete",
    tokens: 0,
    trace_id: null,
    turn,
  }
}

function investigationWith(
  points: SessionCostPoint[],
  records: SessionEvidenceRecord[]
): SessionInvestigation {
  return {
    cost: { points },
    records,
  } as unknown as SessionInvestigation
}

describe("attributeCostPoints", () => {
  it("joins each point to its record by id and keeps payload order", () => {
    const joined = attributeCostPoints(
      investigationWith(
        [point("r2", 0.02), point("r1", 0.01)],
        [record("r1", 3), record("r2", 4)]
      )
    )
    expect(joined.map((entry) => entry.record_id)).toEqual(["r2", "r1"])
    expect(joined[0].record?.turn).toBe(4)
    expect(joined[1].record?.turn).toBe(3)
  })

  it("keeps a null record for a point whose record was not retained", () => {
    const joined = attributeCostPoints(
      investigationWith([point("missing", 0.01)], [record("other", 1)])
    )
    expect(joined[0].record).toBeNull()
  })
})

describe("rankByCost", () => {
  it("ranks most expensive first without mutating the input", () => {
    const input = [
      { ...point("a", 0.01), record: null },
      { ...point("b", 0.03), record: null },
      { ...point("c", 0.02), record: null },
    ] satisfies AttributedCostPoint[]
    const ranked = rankByCost(input)
    expect(ranked.map((entry) => entry.record_id)).toEqual(["b", "c", "a"])
    expect(input.map((entry) => entry.record_id)).toEqual(["a", "b", "c"])
  })
})

describe("barHeight", () => {
  it("scales against the maximum with a 2% visibility floor", () => {
    expect(barHeight(0.05, 0.1)).toBe("50%")
    expect(barHeight(0.0001, 0.1)).toBe("2%")
    expect(barHeight(0.1, 0)).toBe("2%")
  })

  it("treats an empty point list as a zero maximum", () => {
    expect(maximumCost([])).toBe(0)
    expect(maximumCost([point("a", 0.02), point("b", 0.07)])).toBe(0.07)
  })
})

describe("token composition", () => {
  it("totals the four retained token classes", () => {
    expect(
      tokenTotal({
        fresh_input_tokens: 100,
        cache_read_tokens: 200,
        cache_write_tokens: 30,
        output_tokens: 70,
      } as SessionInvestigation["cost"])
    ).toBe(400)
  })

  it("shares the track by value and collapses a zero total", () => {
    expect(tokenShare(25, 100)).toBe("25%")
    expect(tokenShare(25, 0)).toBe("0%")
  })
})

describe("money formatting", () => {
  it("prints six decimals unsigned", () => {
    expect(usd(0.1234567)).toBe("$0.123457")
    expect(usd(0)).toBe("$0.000000")
  })

  it("signs deltas with a true minus sign and an exact-zero band", () => {
    expect(signedUsd(0.000001)).toBe("+$0.000001")
    expect(signedUsd(-0.000001)).toBe("−$0.000001")
    expect(signedUsd(0.0000004)).toBe("$0.000000")
    expect(signedUsd(-0.0000004)).toBe("$0.000000")
  })
})

describe("formatTimestamp", () => {
  it("formats a parsable instant with millisecond precision", () => {
    expect(formatTimestamp("2026-08-04T15:00:01.234Z")).toMatch(
      /\d{1,2}:\d{2}:\d{2}\.\d{3}/
    )
  })

  it("passes unparsable values through and names a missing one", () => {
    expect(formatTimestamp("not a date")).toBe("not a date")
    expect(formatTimestamp(undefined)).toBe("Timestamp unavailable")
  })
})
