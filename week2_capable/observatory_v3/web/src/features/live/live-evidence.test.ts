import { describe, expect, it } from "vitest"

import {
  formatAge,
  money,
  observedNumber,
  responseTrend,
} from "./live-evidence"
import type { VitalsFields } from "@/data/session-vitals"

const now = Date.parse("2026-08-04T12:00:00Z")

describe("live evidence helpers", () => {
  it("humanizes ages across the reference thresholds", () => {
    expect(formatAge("2026-08-04T12:00:00Z", now)).toBe("now")
    expect(formatAge("2026-08-04T11:59:30Z", now)).toBe("30s ago")
    expect(formatAge("2026-08-04T11:30:00Z", now)).toBe("30m ago")
    expect(formatAge("2026-08-04T09:00:00Z", now)).toBe("3h ago")
    expect(formatAge("not a date", now)).toBe("age unknown")
    expect(formatAge(now / 1000 - 90, now)).toBe("1m ago")
  })

  it("reads only numeric observed values", () => {
    const fields = {
      hit: { value: 12, sequence: 1, observed_at: 0, confidence: "high", method: "m" },
      posture: { value: "standing", sequence: 2, observed_at: 0, confidence: "high", method: "m" },
    } as unknown as VitalsFields
    expect(observedNumber(fields, "hit")).toBe(12)
    expect(observedNumber(fields, "posture")).toBeNull()
    expect(observedNumber(fields, "missing")).toBeNull()
  })

  it("formats money at the cent threshold", () => {
    expect(money(0.0079)).toBe("$0.0079")
    expect(money(0.016)).toBe("$0.016")
  })

  it("trends the last response against the prior", () => {
    expect(responseTrend([])).toBeNull()
    expect(responseTrend([0.01])).toBeNull()
    expect(responseTrend([0, 0.01])).toBeNull()
    expect(responseTrend([0.01, 0.02])).toBe(1)
  })
})
