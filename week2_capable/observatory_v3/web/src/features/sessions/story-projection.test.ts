import { describe, expect, it } from "vitest"

import type { SessionInvestigation } from "@/data/session-investigation"

import {
  compareRecords,
  projectStory,
  segmentTurnsByNudges,
  type SessionEvidenceRecord,
} from "./story-projection"

function record(
  overrides: Partial<SessionEvidenceRecord> & { id: string }
): SessionEvidenceRecord {
  return {
    at: "2026-08-04T10:00:00.000Z",
    capture_gaps: [],
    cost_usd: 0,
    duration_ms: 0,
    fields: {},
    form: "parsed",
    iteration: null,
    kind: "note",
    label: "Record",
    parent_id: null,
    preview: "",
    room_id: null,
    sequence: 0,
    source: "agent",
    source_ref: "agent.jsonl line 1",
    status: "complete",
    tokens: 0,
    trace_id: null,
    turn: null,
    ...overrides,
  }
}

function investigation(
  records: SessionEvidenceRecord[],
  overrides: {
    objective?: string | null
    label?: string
    created_at?: string
    ended_at?: string | null
  } = {}
): SessionInvestigation {
  return {
    records,
    objective: overrides.objective ?? null,
    run: {
      created_at: overrides.created_at ?? "2026-08-04T09:59:00.000Z",
      ended_at: overrides.ended_at ?? null,
      label: overrides.label ?? "Run label",
    },
  } as unknown as SessionInvestigation
}

function at(seconds: number): string {
  return `2026-08-04T10:00:${String(seconds).padStart(2, "0")}.000Z`
}

describe("compareRecords", () => {
  it("orders by timestamp first", () => {
    const later = record({ id: "a", at: at(5) })
    const earlier = record({ id: "b", at: at(1) })
    expect(
      [later, earlier].sort(compareRecords).map((item) => item.id)
    ).toEqual(["b", "a"])
  })

  it("breaks timestamp ties by sequence within a source, else by id", () => {
    const first = record({ id: "z", sequence: 1 })
    const second = record({ id: "a", sequence: 2 })
    expect([second, first].sort(compareRecords).map((item) => item.id)).toEqual(
      ["z", "a"]
    )
    const agent = record({ id: "b", sequence: 9, source: "agent" })
    const gateway = record({ id: "a", sequence: 1, source: "gateway" })
    expect(
      [agent, gateway].sort(compareRecords).map((item) => item.id)
    ).toEqual(["a", "b"])
  })
})

describe("projectStory grouping", () => {
  it("groups records by turn and iteration into keyed iterations", () => {
    const story = projectStory(
      investigation([
        record({
          id: "i1",
          kind: "iteration",
          turn: 1,
          iteration: 1,
          at: at(1),
        }),
        record({ id: "p1", kind: "plan", turn: 1, iteration: 1, at: at(2) }),
        record({
          id: "i2",
          kind: "iteration",
          turn: 2,
          iteration: 1,
          at: at(10),
        }),
      ])
    )
    expect(story.turns.map((turn) => turn.number)).toEqual([1, 2])
    expect(
      story.byIteration.get("1:1")?.records.map((item) => item.id)
    ).toEqual(["i1", "p1"])
    expect(story.byIteration.get("2:1")?.id).toBe("i2")
  })

  it("takes number, turn, and start from the iteration boundary record", () => {
    const story = projectStory(
      investigation([
        record({ id: "p1", kind: "prompt", turn: 3, iteration: 2, at: at(5) }),
        record({
          id: "b1",
          kind: "iteration",
          turn: 3,
          iteration: 2,
          at: at(4),
        }),
      ])
    )
    const iteration = story.byIteration.get("3:2")
    expect(iteration?.id).toBe("b1")
    expect(iteration?.number).toBe(2)
    expect(iteration?.turn).toBe(3)
    expect(iteration?.startedAt).toBe(at(4))
    expect(iteration?.endedAt).toBe(at(5))
  })

  it("orders iterations by start time and titles idle ones by number", () => {
    const story = projectStory(
      investigation([
        record({
          id: "i2",
          kind: "iteration",
          turn: 1,
          iteration: 2,
          at: at(9),
        }),
        record({
          id: "i1",
          kind: "iteration",
          turn: 1,
          iteration: 1,
          at: at(1),
        }),
      ])
    )
    const numbers = story.turns[0]?.iterations.map((item) => item.number)
    expect(numbers).toEqual([1, 2])
    expect(story.turns[0]?.iterations[0]?.title).toBe("Iteration 1")
  })

  it("titles a movement iteration and summarizes its calls", () => {
    const story = projectStory(
      investigation([
        record({
          id: "i1",
          kind: "iteration",
          turn: 1,
          iteration: 1,
          at: at(1),
        }),
        record({
          id: "c1",
          kind: "tool_call",
          turn: 1,
          iteration: 1,
          at: at(2),
          fields: { name: "tbamud__go", args: { direction: "north" } },
        }),
        record({
          id: "pos1",
          kind: "position",
          turn: 1,
          iteration: 1,
          at: at(3),
          room_id: "room-7",
          fields: { title: "The Temple Square" },
        }),
      ])
    )
    const iteration = story.byIteration.get("1:1")
    expect(iteration?.title).toBe("Move to The Temple Square")
    expect(iteration?.subtitle).toBe("The Temple Square · move north")
    expect(iteration?.roomId).toBe("room-7")
  })

  it("sums iteration cost per turn and closes a single turn at run end", () => {
    const story = projectStory(
      investigation(
        [
          record({
            id: "i1",
            kind: "iteration",
            turn: 1,
            iteration: 1,
            at: at(1),
            cost_usd: 0.25,
          }),
          record({
            id: "r1",
            kind: "response",
            turn: 1,
            iteration: 1,
            at: at(2),
            cost_usd: 0.5,
          }),
        ],
        { ended_at: at(30) }
      )
    )
    expect(story.turns[0]?.costUsd).toBeCloseTo(0.75)
    expect(story.turns[0]?.endedAt).toBe(at(30))
  })
})

describe("projectStory objective epochs", () => {
  it("opens with the session_start objective and windows later revisions", () => {
    const story = projectStory(
      investigation([
        record({
          id: "s1",
          kind: "session_start",
          at: at(0),
          fields: { objective: { title: "Reach the temple" } },
        }),
        record({
          id: "i1",
          kind: "iteration",
          turn: 1,
          iteration: 1,
          at: at(1),
        }),
        record({
          id: "g1",
          kind: "goal_revision",
          turn: 1,
          iteration: 2,
          at: at(10),
          fields: { instruction: "Hunt the rat" },
        }),
        record({
          id: "i2",
          kind: "iteration",
          turn: 1,
          iteration: 2,
          at: at(11),
        }),
      ])
    )
    expect(
      story.objectiveEpochs.map((epoch) => [epoch.number, epoch.title])
    ).toEqual([
      [1, "Reach the temple"],
      [2, "Hunt the rat"],
    ])
    expect(story.byIteration.get("1:1")?.objectiveEpoch).toBe(1)
    expect(story.byIteration.get("1:2")?.objectiveEpoch).toBe(2)
    expect(story.objectiveEpochs[1]?.firstIteration?.id).toBe("i2")
  })

  it("falls back to one retained epoch titled from the objective", () => {
    const story = projectStory(
      investigation(
        [record({ id: "i1", kind: "iteration", turn: 1, iteration: 1 })],
        { objective: "  explore town  " }
      )
    )
    expect(story.objectiveEpochs).toHaveLength(1)
    expect(story.objectiveEpochs[0]?.title).toBe("explore town")
    expect(story.byIteration.get("1:1")?.objectiveEpoch).toBe(1)
  })

  it("assigns nudges to the epoch window that contains them", () => {
    const story = projectStory(
      investigation([
        record({
          id: "g1",
          kind: "goal_revision",
          at: at(0),
          fields: { instruction: "First goal" },
        }),
        record({
          id: "n1",
          kind: "guidance",
          at: at(5),
          preview: "Try the east gate",
        }),
        record({
          id: "g2",
          kind: "goal_revision",
          at: at(10),
          fields: { instruction: "Second goal" },
        }),
        record({
          id: "n2",
          kind: "guidance",
          at: at(15),
          preview: "Rest first",
        }),
        record({ id: "n3", kind: "guidance", at: at(16), preview: "   " }),
      ])
    )
    expect(
      story.objectiveEpochs.map((epoch) =>
        epoch.nudges.map((nudge) => nudge.instruction)
      )
    ).toEqual([["Try the east gate"], ["Rest first"]])
  })
})

describe("projectStory tool cycles and terminal records", () => {
  it("assembles a tool cycle from children and trace correlation", () => {
    const base = { turn: 1, iteration: 1 }
    const story = projectStory(
      investigation([
        record({ id: "i1", kind: "iteration", ...base, at: at(1) }),
        record({
          id: "call",
          kind: "tool_call",
          ...base,
          at: at(2),
          trace_id: "t-1",
        }),
        record({
          id: "gw-call",
          kind: "tool_call",
          source: "gateway",
          ...base,
          at: at(3),
          parent_id: "call",
          trace_id: "t-1",
        }),
        record({
          id: "wire-text",
          kind: "wire_text",
          source: "gateway",
          ...base,
          at: at(4),
          trace_id: "t-1",
        }),
        record({
          id: "obs",
          kind: "observation",
          source: "gateway",
          ...base,
          at: at(5),
          parent_id: "gw-call",
        }),
        record({
          id: "result",
          kind: "tool_result",
          ...base,
          at: at(6),
          trace_id: "t-1",
        }),
      ])
    )
    const steps = story.byIteration.get("1:1")?.steps ?? []
    expect(steps).toHaveLength(1)
    const step = steps[0]
    if (step?.type !== "tool") throw new Error("expected a tool step")
    expect(step.cycle.gatewayCall?.id).toBe("gw-call")
    expect(step.cycle.wireTexts.map((item) => item.id)).toEqual(["wire-text"])
    expect(step.cycle.observations.map((item) => item.id)).toEqual(["obs"])
    expect(step.cycle.agentResult?.id).toBe("result")
  })

  it("keeps terminal records unless a limit_reached carries an iteration", () => {
    const story = projectStory(
      investigation([
        record({ id: "close", kind: "session_close", at: at(20) }),
        record({
          id: "limit-in",
          kind: "limit_reached",
          turn: 1,
          iteration: 1,
          at: at(10),
        }),
        record({ id: "limit-out", kind: "limit_reached", at: at(15) }),
      ])
    )
    expect(story.terminalRecords.map((item) => item.id)).toEqual([
      "limit-out",
      "close",
    ])
  })
})

describe("segmentTurnsByNudges", () => {
  it("splits turns before the first nudge and per active nudge", () => {
    const story = projectStory(
      investigation([
        record({
          id: "g1",
          kind: "goal_revision",
          at: at(0),
          fields: { instruction: "Only goal" },
        }),
        record({
          id: "i1",
          kind: "iteration",
          turn: 1,
          iteration: 1,
          at: at(1),
        }),
        record({ id: "n1", kind: "guidance", at: at(5), preview: "Nudge one" }),
        record({
          id: "i2",
          kind: "iteration",
          turn: 1,
          iteration: 2,
          at: at(6),
        }),
        record({
          id: "i3",
          kind: "iteration",
          turn: 2,
          iteration: 1,
          at: at(9),
        }),
      ])
    )
    const epoch = story.objectiveEpochs[0]
    if (epoch === undefined) throw new Error("expected an epoch")
    const segments = segmentTurnsByNudges(epoch, story.turns)
    expect(
      segments.beforeFirstNudge.flatMap((turn) =>
        turn.iterations.map((item) => item.id)
      )
    ).toEqual(["i1"])
    expect(segments.nudges).toHaveLength(1)
    expect(
      segments.nudges[0]?.turns.flatMap((turn) =>
        turn.iterations.map((item) => item.id)
      )
    ).toEqual(["i2", "i3"])
  })

  it("attaches an early nudge to its own turn and iteration", () => {
    const story = projectStory(
      investigation([
        record({
          id: "g1",
          kind: "goal_revision",
          at: at(0),
          fields: { instruction: "Only goal" },
        }),
        record({
          id: "i1",
          kind: "iteration",
          turn: 1,
          iteration: 1,
          at: at(1),
        }),
        record({
          id: "n1",
          kind: "guidance",
          turn: 1,
          iteration: 1,
          at: at(2),
          preview: "Mid-iteration nudge",
        }),
      ])
    )
    const epoch = story.objectiveEpochs[0]
    if (epoch === undefined) throw new Error("expected an epoch")
    const segments = segmentTurnsByNudges(epoch, story.turns)
    expect(segments.beforeFirstNudge).toEqual([])
    expect(
      segments.nudges[0]?.turns.flatMap((turn) =>
        turn.iterations.map((item) => item.id)
      )
    ).toEqual(["i1"])
  })
})
