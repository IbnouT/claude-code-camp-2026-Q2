import { describe, expect, it } from "vitest"

import type { LiveJourney } from "@/data/live-view"
import {
  costCurve,
  eventSequences,
  labelledLandmarks,
  recentLandmarks,
  trackPosition,
} from "./timeline-model"

function journey(overrides: Partial<LiveJourney>): LiveJourney {
  return {
    latest_sequence: 100,
    timeline: [],
    milestones: [],
    friction: {
      kind: null,
      repeated_command: null,
      repeated_count: 0,
      distinct_places: 0,
      iterations: 0,
      new_places: 0,
      window_iterations: 0,
      iterations_since_new_place: null,
      threshold: "",
      evidence: [],
    },
    economics: [],
    ...overrides,
  } as unknown as LiveJourney
}

function item(
  sequence: number,
  kind: string,
  label: string,
  source = "gateway"
) {
  return { id: `${sequence}`, sequence, kind, label, source }
}

describe("timeline model", () => {
  it("dedups consecutive rooms and windows milestones", () => {
    const view = journey({
      timeline: [
        item(10, "position", "Temple"),
        item(20, "position", "Temple"),
        item(30, "position", "Field"),
      ],
      milestones: [
        { sequence: 5, current: 2 },
        { sequence: 40, current: 3 },
      ] as never,
    })
    const marks = recentLandmarks(view)
    expect(marks.map((m) => m.id)).toEqual(["room-10", "room-30", "level-40"])
  })

  it("applies the friction truth table", () => {
    const base = journey({ timeline: [item(10, "position", "Temple")] })
    const fired = journey({
      ...base,
      friction: {
        ...base.friction,
        kind: "confusion_loop",
        repeated_command: "north",
        evidence: [50, 60],
      },
    })
    expect(recentLandmarks(fired).at(-1)?.id).toBe("friction-confusion_loop-60")
    const noCommand = journey({
      ...base,
      friction: {
        ...base.friction,
        kind: "confusion_loop",
        repeated_command: null,
        evidence: [50],
      },
    })
    expect(recentLandmarks(noCommand).some((m) => m.kind === "friction")).toBe(
      false
    )
  })

  it("guards the cost curve and centers degenerate tracks", () => {
    expect(costCurve([])).toBe("")
    expect(costCurve([{ cumulative_cost_usd: 1 }])).toBe("")
    expect(
      costCurve([{ cumulative_cost_usd: 0.5 }, { cumulative_cost_usd: 0 }])
    ).toBe("")
    expect(
      costCurve([{ cumulative_cost_usd: 0.5 }, { cumulative_cost_usd: 1 }])
    ).toBe("0.0,29.5 900.0,13.0")
    expect(trackPosition(5, 10, 10)).toBe(50)
    expect(trackPosition(10, 0, 100)).toBeCloseTo(11.4)
  })

  it("dedups event sequences and labels the latest per kind", () => {
    const view = journey({
      timeline: [
        item(10, "position", "Temple"),
        item(10, "command", "look"),
        item(30, "operator_control", "guide", "agent"),
      ],
      milestones: [{ sequence: 20, current: 2 }] as never,
    })
    expect(eventSequences(view)).toEqual([10, 30, 100])
    const labels = labelledLandmarks(recentLandmarks(view))
    expect(labels.map((l) => l.kind)).toEqual(["level_up", "operator_message"])
  })
})
