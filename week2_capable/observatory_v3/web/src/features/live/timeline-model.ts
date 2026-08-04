import type { LiveJourney } from "@/data/live-view"

type TimelineLandmark = {
  id: string
  kind: "room" | "level_up" | "operator_message" | "friction"
  sequence: number
  label: string
  shortLabel: string
}

/**
 * The causal landmarks visible in the retained window: rooms deduped
 * against the previous position, level ups, operator messages, and at
 * most one friction marker.
 */
function recentLandmarks(view: LiveJourney): TimelineLandmark[] {
  const gateway = view.timeline.filter((item) => item.source === "gateway")
  const firstRetained = gateway[0]?.sequence ?? view.latest_sequence
  const landmarks: TimelineLandmark[] = []

  let previousPosition: string | null = null
  for (const item of view.timeline) {
    if (item.source !== "gateway" || item.kind !== "position") continue
    if (item.label === previousPosition) continue
    previousPosition = item.label
    landmarks.push({
      id: `room-${item.id}`,
      kind: "room",
      sequence: item.sequence,
      label: item.label,
      shortLabel: "room",
    })
  }
  for (const milestone of view.milestones) {
    if (milestone.sequence < firstRetained) continue
    landmarks.push({
      id: `level-${milestone.sequence}`,
      kind: "level_up",
      sequence: milestone.sequence,
      label: `Level ${milestone.current}`,
      shortLabel: `level ${milestone.current}`,
    })
  }
  for (const item of view.timeline) {
    if (item.source !== "agent" || item.kind !== "operator_control") continue
    if (item.sequence < firstRetained) continue
    landmarks.push({
      id: `operator-${item.id}`,
      kind: "operator_message",
      sequence: item.sequence,
      label: item.label,
      shortLabel: "your message",
    })
  }
  const friction = view.friction
  if (
    friction.kind !== null &&
    friction.evidence.length > 0 &&
    !(friction.kind === "confusion_loop" && friction.repeated_command === null)
  ) {
    const sequence = Math.max(...friction.evidence)
    if (sequence >= firstRetained) {
      landmarks.push({
        id: `friction-${friction.kind}-${sequence}`,
        kind: "friction",
        sequence,
        label:
          friction.kind === "confusion_loop"
            ? `repeated “${friction.repeated_command}”`
            : "no new place",
        shortLabel:
          friction.kind === "confusion_loop"
            ? `repeated “${friction.repeated_command}”`
            : "no new place",
      })
    }
  }
  return landmarks.sort((left, right) => left.sequence - right.sequence)
}

/** SVG polyline points for the 900 by 52 cumulative cost curve. */
function costCurve(points: readonly { cumulative_cost_usd: number }[]): string {
  if (points.length < 2) return ""
  const highest = points[points.length - 1].cumulative_cost_usd
  if (highest <= 0) return ""
  return points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 900
      const y = 46 - (point.cumulative_cost_usd / highest) * 33
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
}

/** Sequence to track percent, 2 to 96, centered when degenerate. */
function trackPosition(sequence: number, first: number, last: number): number {
  if (last <= first) return 50
  const ratio = Math.min(Math.max((sequence - first) / (last - first), 0), 1)
  return 2 + ratio * 94
}

/** Every retained event sequence plus the live head, ascending. */
function eventSequences(view: LiveJourney): number[] {
  const set = new Set<number>(view.timeline.map((item) => item.sequence))
  set.add(view.latest_sequence)
  return [...set].sort((left, right) => left - right)
}

/** The latest landmark of each labelled kind, rooms never labelled. */
function labelledLandmarks(
  landmarks: readonly TimelineLandmark[]
): TimelineLandmark[] {
  const kinds = ["level_up", "operator_message", "friction"] as const
  return kinds.flatMap((kind) => {
    const last = [...landmarks].reverse().find((mark) => mark.kind === kind)
    return last === undefined ? [] : [last]
  })
}

export {
  costCurve,
  eventSequences,
  labelledLandmarks,
  recentLandmarks,
  trackPosition,
  type TimelineLandmark,
}
