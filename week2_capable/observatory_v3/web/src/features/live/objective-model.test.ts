import { describe, expect, it } from "vitest"

import { projectObjective } from "./objective-model"
import type { SessionGoalItem } from "@/data/session-goals"

function goal(ordinal: number, title: string): SessionGoalItem {
  return {
    goal: {
      id: `goal-${ordinal}`,
      kind: "goal",
      parent_id: null,
      goal_id: `goal-${ordinal}`,
      turn_id: null,
      iteration_id: null,
      ordinal,
      occurred_at: "2026-08-04T15:00:00Z",
      title,
      source_ref: "agent.jsonl line 1",
      duration_ms: null,
      tokens: null,
      cost_usd: null,
    },
    nudges: [],
    turns: [],
    outcome: null,
    tokens: null,
    cost_usd: null,
    duration_ms: null,
    child_continuation_cursor: null,
  } as unknown as SessionGoalItem
}

describe("objective projection", () => {
  it("leads with the latest goal and counts revisions", () => {
    const result = projectObjective(
      [goal(1, "Find the bakery"), goal(2, "Defend the gate")],
      null,
      true
    )
    expect(result.title).toBe("Defend the gate")
    expect(result.revisionLabel).toBe("Revision 2")
    expect(result.clue).toBeNull()
  })

  it("falls back to the catalog objective, then to no goal", () => {
    expect(projectObjective([], "just chill", false).title).toBe("just chill")
    const empty = projectObjective([], null, true)
    expect(empty.title).toBe("No goal set")
    expect(empty.clue).toBe("First message starts the agent")
    expect(projectObjective([], null, false).clue).toBeNull()
  })
})
