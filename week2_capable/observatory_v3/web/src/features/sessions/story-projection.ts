import type { SessionInvestigation } from "@/data/session-investigation"

type SessionEvidenceRecord = SessionInvestigation["records"][number]

type EvidenceFields = Record<string, unknown>

type SessionView = "story" | "map" | "cost"

type SessionSelection = {
  turn: number | null
  iteration: number | null
  recordId: string | null
}

type StoryOperatorMessage = {
  record: SessionEvidenceRecord
  action: "revise" | "guide"
  instruction: string
}

type StoryObjectiveEpoch = {
  id: string
  number: number
  title: string
  startedAt: string
  record: SessionEvidenceRecord | null
  nudges: StoryOperatorMessage[]
  firstIteration: StoryIteration | null
}

type StoryToolCycle = {
  id: string
  call: SessionEvidenceRecord
  records: SessionEvidenceRecord[]
  gatewayCall: SessionEvidenceRecord | null
  commands: SessionEvidenceRecord[]
  wires: SessionEvidenceRecord[]
  wireTexts: SessionEvidenceRecord[]
  parserInputs: SessionEvidenceRecord[]
  observations: SessionEvidenceRecord[]
  stateChanges: SessionEvidenceRecord[]
  gatewayResults: SessionEvidenceRecord[]
  agentResult: SessionEvidenceRecord | null
}

type StoryStep =
  | { type: "record"; record: SessionEvidenceRecord }
  | { type: "tool"; cycle: StoryToolCycle }

type StoryIteration = {
  id: string
  number: number
  turn: number
  startedAt: string
  endedAt: string
  durationMs: number
  costUsd: number
  title: string
  subtitle: string
  roomId: string | null
  roomTitle: string | null
  records: SessionEvidenceRecord[]
  steps: StoryStep[]
  responseIds: string[]
  toolCalls: number
  captureGaps: string[]
  controls: StoryOperatorMessage[]
  objectiveEpoch: number
}

type StoryTurn = {
  number: number
  startedAt: string
  endedAt: string
  durationMs: number
  costUsd: number
  iterations: StoryIteration[]
}

type StoryModel = {
  startRecords: SessionEvidenceRecord[]
  goalRecords: SessionEvidenceRecord[]
  operatorMessages: StoryOperatorMessage[]
  objectiveEpochs: StoryObjectiveEpoch[]
  turns: StoryTurn[]
  terminalRecords: SessionEvidenceRecord[]
  byRecordId: Map<string, SessionEvidenceRecord>
  byIteration: Map<string, StoryIteration>
}

const iterationKinds = new Set([
  "iteration",
  "prompt",
  "plan",
  "reasoning",
  "response",
  "tool_call",
  "tool_result",
  "retry",
  "limit_reached",
  "goal_revision",
  "guidance",
])

const terminalKinds = new Set([
  "session_close",
  "turn_end",
  "limit_reached",
  "crash",
  "stopped",
])

const stateKinds = new Set(["knowledge_change", "position", "parse_metric"])

function recordFields(record: SessionEvidenceRecord): EvidenceFields {
  return record.fields ?? {}
}

function projectStory(investigation: SessionInvestigation): StoryModel {
  const records = [...investigation.records].sort(compareRecords)
  const byRecordId = new Map(records.map((record) => [record.id, record]))
  const children = childIndex(records)
  const startRecords = records.filter(
    (record) =>
      record.iteration === null &&
      (record.kind === "session_start" ||
        record.kind === "session_open" ||
        record.kind === "surface_profile" ||
        record.kind === "login")
  )
  const operatorMessages = records
    .filter(
      (record) => record.kind === "goal_revision" || record.kind === "guidance"
    )
    .map(projectOperatorMessage)
    .filter((message): message is StoryOperatorMessage => message !== null)
  const goalRecords = operatorMessages
    .filter((message) => message.action === "revise")
    .map((message) => message.record)
  const iterationGroups = new Map<string, SessionEvidenceRecord[]>()
  for (const record of records) {
    if (record.turn === null || record.iteration === null) continue
    const key = iterationKey(record.turn, record.iteration)
    const group = iterationGroups.get(key) ?? []
    group.push(record)
    iterationGroups.set(key, group)
  }
  const iterations = [...iterationGroups.values()]
    .map((group) => projectIteration(group, children))
    .sort((left, right) => compareIteration(left, right))
  const objectiveEpochs = projectObjectiveEpochs(
    investigation,
    operatorMessages,
    iterations
  )
  const epochByIteration = new Map(
    objectiveEpochs.flatMap((epoch) =>
      iterations
        .filter((iteration) =>
          objectiveEpochAt(epoch, objectiveEpochs, iteration)
        )
        .map((iteration) => [iteration.id, epoch.number] as const)
    )
  )
  const attributedIterations = iterations.map((iteration) => ({
    ...iteration,
    objectiveEpoch: epochByIteration.get(iteration.id) ?? 1,
  }))
  const turnNumbers = [
    ...new Set(attributedIterations.map((iteration) => iteration.turn)),
  ].sort((left, right) => left - right)
  const turns = turnNumbers.map((number) => {
    const turnIterations = attributedIterations.filter(
      (iteration) => iteration.turn === number
    )
    const startedAt =
      turnIterations[0]?.startedAt ?? investigation.run.created_at ?? ""
    const endedAt =
      turnNumbers.length === 1 && investigation.run.ended_at
        ? investigation.run.ended_at
        : (turnIterations.at(-1)?.endedAt ?? startedAt)
    return {
      number,
      startedAt,
      endedAt,
      durationMs: elapsed(startedAt, endedAt),
      costUsd: sum(turnIterations.map((iteration) => iteration.costUsd)),
      iterations: turnIterations,
    }
  })
  const terminalRecords = records.filter(
    (record) =>
      terminalKinds.has(record.kind) &&
      (record.iteration === null || !iterationKinds.has(record.kind))
  )
  return {
    startRecords,
    goalRecords,
    operatorMessages,
    objectiveEpochs,
    turns,
    terminalRecords,
    byRecordId,
    byIteration: new Map(
      attributedIterations.map((iteration) => [
        iterationKey(iteration.turn, iteration.number),
        iteration,
      ])
    ),
  }
}

function projectIteration(
  records: SessionEvidenceRecord[],
  children: Map<string, SessionEvidenceRecord[]>
): StoryIteration {
  const ordered = [...records].sort(compareRecords)
  const boundary = ordered.find((record) => record.kind === "iteration")
  const number =
    boundary?.iteration ??
    ordered.find((record) => record.iteration !== null)?.iteration ??
    1
  const turn =
    boundary?.turn ?? ordered.find((record) => record.turn !== null)?.turn ?? 1
  const startedAt = boundary?.at ?? ordered[0]?.at ?? ""
  const endedAt = ordered.at(-1)?.at ?? startedAt
  const calls = ordered.filter(
    (record) => record.source === "agent" && record.kind === "tool_call"
  )
  const consumed = new Set<string>()
  const cycles = new Map<string, StoryToolCycle>()
  for (const call of calls) {
    const cycle = projectToolCycle(call, ordered, children)
    cycles.set(call.id, cycle)
    for (const record of cycle.records) consumed.add(record.id)
    consumed.delete(call.id)
  }
  const steps: StoryStep[] = []
  for (const record of ordered) {
    if (record.kind === "iteration") continue
    if (
      record.kind === "goal_revision" ||
      record.kind === "guidance" ||
      record.kind === "operator_control"
    ) {
      continue
    }
    if (cycles.has(record.id)) {
      steps.push({
        type: "tool",
        cycle: cycles.get(record.id) as StoryToolCycle,
      })
      continue
    }
    if (consumed.has(record.id)) continue
    if (
      record.source === "gateway" &&
      !["retry", "limit_reached"].includes(record.kind)
    ) {
      continue
    }
    steps.push({ type: "record", record })
  }
  const positions = ordered.filter(
    (record) => record.kind === "position" && record.room_id !== null
  )
  const roomRecord =
    positions.at(-1) ??
    ordered.find(
      (record) =>
        record.kind === "observation" &&
        (typeof recordFields(record).title === "string" ||
          recordFields(record).kind === "room")
    ) ??
    null
  const roomTitle =
    roomRecord === null
      ? null
      : typeof recordFields(roomRecord).title === "string"
        ? (recordFields(roomRecord).title as string)
        : typeof recordFields(roomRecord).text === "string"
          ? (recordFields(roomRecord).text as string)
          : roomRecord.preview || null
  const plan = ordered.find(
    (record) => record.kind === "plan" || record.kind === "reasoning"
  )
  const toolLabels = calls.map((call) => shortToolName(call)).filter(Boolean)
  const title = iterationTitle(number, roomTitle, toolLabels, plan)
  const subtitleParts = [
    roomTitle,
    calls.length > 0 ? summarizeCalls(calls) : null,
  ].filter((value): value is string => Boolean(value))
  const responseIds = ordered
    .filter((record) => record.kind === "response")
    .map((record) => record.id)
  return {
    id: boundary?.id ?? `iteration:${number}`,
    number,
    turn,
    startedAt,
    endedAt,
    durationMs: elapsed(startedAt, endedAt),
    costUsd: sum(ordered.map((record) => record.cost_usd)),
    title,
    subtitle: subtitleParts.join(" · ") || "Retained iteration evidence",
    roomId: roomRecord?.room_id ?? null,
    roomTitle,
    records: ordered,
    steps,
    responseIds,
    toolCalls: calls.length,
    captureGaps: [...new Set(ordered.flatMap((record) => record.capture_gaps))],
    controls: ordered
      .map(projectOperatorMessage)
      .filter((message): message is StoryOperatorMessage => message !== null),
    objectiveEpoch: 1,
  }
}

function projectOperatorMessage(
  record: SessionEvidenceRecord
): StoryOperatorMessage | null {
  if (record.kind !== "goal_revision" && record.kind !== "guidance") {
    return null
  }
  const action = record.kind === "goal_revision" ? "revise" : "guide"
  const raw = recordFields(record).instruction
  const instruction =
    typeof raw === "string" ? raw.trim() : record.preview.trim()
  if (!instruction) return null
  return { record, action, instruction }
}

function projectObjectiveEpochs(
  investigation: SessionInvestigation,
  messages: StoryOperatorMessage[],
  iterations: StoryIteration[]
): StoryObjectiveEpoch[] {
  const goals = messages.filter((message) => message.action === "revise")
  const fallbackTitle =
    investigation.objective?.trim() ||
    investigation.run.label.trim() ||
    "Objective not retained"
  const sessionStart = investigation.records.find(
    (record) => record.kind === "session_start"
  )
  const rawObjective =
    sessionStart === undefined
      ? undefined
      : recordFields(sessionStart).objective
  const initialTitle =
    typeof rawObjective === "object" &&
    rawObjective !== null &&
    typeof (rawObjective as EvidenceFields).title === "string"
      ? String((rawObjective as EvidenceFields).title).trim()
      : ""
  const starts = [
    ...(initialTitle
      ? [
          {
            id: "objective:initial",
            title: initialTitle,
            startedAt:
              sessionStart?.at ??
              investigation.run.created_at ??
              iterations[0]?.startedAt ??
              "",
            record: sessionStart ?? null,
          },
        ]
      : []),
    ...goals.map((message) => ({
      id: message.record.id,
      title: message.instruction,
      startedAt: message.record.at,
      record: message.record,
    })),
  ]
  if (starts.length === 0) {
    starts.push({
      id: "objective:retained",
      title: fallbackTitle,
      startedAt: investigation.run.created_at ?? iterations[0]?.startedAt ?? "",
      record: null,
    })
  }
  return starts.map((goal, index) => {
    const next = starts[index + 1]
    const withinEpoch = (value: string): boolean =>
      compareTimestamp(value, goal.startedAt) >= 0 &&
      (next === undefined || compareTimestamp(value, next.startedAt) < 0)
    return {
      ...goal,
      number: index + 1,
      nudges: messages.filter(
        (message) =>
          message.action === "guide" && withinEpoch(message.record.at)
      ),
      firstIteration:
        iterations.find((iteration) => withinEpoch(iteration.startedAt)) ??
        null,
    }
  })
}

function objectiveEpochAt(
  epoch: StoryObjectiveEpoch,
  epochs: StoryObjectiveEpoch[],
  iteration: StoryIteration
): boolean {
  const next = epochs[epoch.number]
  return (
    compareTimestamp(iteration.startedAt, epoch.startedAt) >= 0 &&
    (next === undefined ||
      compareTimestamp(iteration.startedAt, next.startedAt) < 0)
  )
}

function projectToolCycle(
  call: SessionEvidenceRecord,
  iterationRecords: SessionEvidenceRecord[],
  children: Map<string, SessionEvidenceRecord[]>
): StoryToolCycle {
  const related = new Map<string, SessionEvidenceRecord>([[call.id, call]])
  const visit = (record: SessionEvidenceRecord): void => {
    for (const child of children.get(record.id) ?? []) {
      if (child.iteration !== call.iteration || related.has(child.id)) continue
      related.set(child.id, child)
      visit(child)
    }
  }
  visit(call)
  const traceIds = new Set(
    [...related.values()]
      .map((record) => record.trace_id)
      .filter((trace): trace is string => trace !== null)
  )
  for (const record of iterationRecords) {
    if (record.trace_id !== null && traceIds.has(record.trace_id)) {
      related.set(record.id, record)
    }
  }
  const records = [...related.values()].sort(compareRecords)
  return {
    id: call.id,
    call,
    records,
    gatewayCall:
      records.find(
        (record) => record.source === "gateway" && record.kind === "tool_call"
      ) ?? null,
    commands: records.filter((record) => record.kind === "command"),
    wires: records.filter((record) => record.kind === "wire"),
    wireTexts: records.filter((record) => record.kind === "wire_text"),
    parserInputs: records.filter((record) => record.kind === "parser_input"),
    observations: records.filter(
      (record) => record.kind === "observation" || record.kind === "unparsed"
    ),
    stateChanges: records.filter((record) => stateKinds.has(record.kind)),
    gatewayResults: records.filter(
      (record) => record.source === "gateway" && record.kind === "tool_result"
    ),
    agentResult:
      records.find(
        (record) => record.source === "agent" && record.kind === "tool_result"
      ) ?? null,
  }
}

function segmentTurnsByNudges(
  epoch: StoryObjectiveEpoch,
  turns: StoryTurn[]
): {
  beforeFirstNudge: StoryTurn[]
  nudges: Array<{ message: StoryOperatorMessage; turns: StoryTurn[] }>
} {
  const nudges = [...epoch.nudges].sort(
    (left, right) => Date.parse(left.record.at) - Date.parse(right.record.at)
  )
  const buckets = new Map<string, Set<string>>([
    ["before", new Set<string>()],
    ...nudges.map((nudge) => [nudge.record.id, new Set<string>()] as const),
  ])
  for (const turn of turns) {
    for (const iteration of turn.iterations) {
      const active = activeNudgeForIteration(epoch, iteration)
      buckets.get(active?.record.id ?? "before")?.add(iteration.id)
    }
  }
  return {
    beforeFirstNudge: filterTurnsByIterationIds(
      turns,
      buckets.get("before") ?? new Set()
    ),
    nudges: nudges.map((message) => ({
      message,
      turns: filterTurnsByIterationIds(
        turns,
        buckets.get(message.record.id) ?? new Set()
      ),
    })),
  }
}

function activeNudgeForIteration(
  epoch: StoryObjectiveEpoch | undefined,
  iteration: StoryIteration
): StoryOperatorMessage | null {
  if (epoch === undefined) return null
  return (
    [...epoch.nudges]
      .sort(
        (left, right) =>
          Date.parse(left.record.at) - Date.parse(right.record.at)
      )
      .filter(
        (message) =>
          (message.record.turn === iteration.turn &&
            message.record.iteration === iteration.number) ||
          Date.parse(message.record.at) <= Date.parse(iteration.startedAt)
      )
      .at(-1) ?? null
  )
}

function filterTurnsByIterationIds(
  turns: StoryTurn[],
  iterationIds: Set<string>
): StoryTurn[] {
  return turns
    .map((turn): StoryTurn => {
      const iterations = turn.iterations.filter((iteration) =>
        iterationIds.has(iteration.id)
      )
      return {
        ...turn,
        startedAt: iterations[0]?.startedAt ?? turn.startedAt,
        endedAt: iterations.at(-1)?.endedAt ?? turn.endedAt,
        durationMs: iterations.reduce(
          (total, iteration) => total + iteration.durationMs,
          0
        ),
        costUsd: iterations.reduce(
          (total, iteration) => total + iteration.costUsd,
          0
        ),
        iterations,
      }
    })
    .filter((turn) => turn.iterations.length > 0)
}

function evidenceText(record: SessionEvidenceRecord): string {
  const fields = recordFields(record)
  for (const key of [
    "text",
    "content",
    "result",
    "model_input",
    "mcp_result",
  ]) {
    const value = fields[key]
    if (typeof value === "string" && value.trim()) return value
  }
  return record.preview
}

function recordIndexForIteration(
  records: SessionEvidenceRecord[],
  turn: number | null,
  iteration: number | null
): number {
  if (records.length === 0) return -1
  if (turn === null || iteration === null) return records.length - 1
  for (let index = records.length - 1; index >= 0; index -= 1) {
    const record = records[index]
    if (record?.turn === turn && record.iteration === iteration) return index
  }
  return records.length - 1
}

function iterationKey(turn: number, iteration: number): string {
  return `${turn}:${iteration}`
}

function compareRecords(
  left: SessionEvidenceRecord,
  right: SessionEvidenceRecord
): number {
  const time = Date.parse(left.at) - Date.parse(right.at)
  if (time !== 0) return time
  if (left.source === right.source) return left.sequence - right.sequence
  return left.id.localeCompare(right.id)
}

function childIndex(
  records: SessionEvidenceRecord[]
): Map<string, SessionEvidenceRecord[]> {
  const children = new Map<string, SessionEvidenceRecord[]>()
  for (const record of records) {
    if (record.parent_id === null) continue
    const bucket = children.get(record.parent_id) ?? []
    bucket.push(record)
    children.set(record.parent_id, bucket)
  }
  return children
}

function compareIteration(left: StoryIteration, right: StoryIteration): number {
  const time = compareTimestamp(left.startedAt, right.startedAt)
  if (time !== 0) return time
  if (left.turn !== right.turn) return left.turn - right.turn
  return left.number - right.number
}

function compareTimestamp(left: string, right: string): number {
  const leftTime = Date.parse(left)
  const rightTime = Date.parse(right)
  if (Number.isFinite(leftTime) && Number.isFinite(rightTime)) {
    return leftTime - rightTime
  }
  return left.localeCompare(right)
}

function shortToolName(record: SessionEvidenceRecord): string {
  const raw = recordFields(record).name
  const name =
    typeof raw === "string" ? raw : record.label.replace(/^Tool call · /, "")
  return name.replace(/^tbamud__/, "")
}

function summarizeCalls(calls: SessionEvidenceRecord[]): string {
  const descriptions = calls.map((call) => {
    const name = shortToolName(call)
    const args = recordFields(call).args
    if (name === "check" && typeof args === "object" && args !== null) {
      const kind = (args as EvidenceFields).kind
      if (kind === "where") return "check current location"
    }
    if (
      ["go", "move", "travel"].includes(name) &&
      typeof args === "object" &&
      args !== null
    ) {
      const direction = (args as EvidenceFields).direction
      if (typeof direction === "string") return `move ${direction}`
    }
    return name.replaceAll("_", " ")
  })
  if (descriptions.length === 2) {
    return `${descriptions[0]}, then ${descriptions[1]}`
  }
  return descriptions.length > 2
    ? `${descriptions.slice(0, -1).join(", ")}, then ${descriptions.at(-1)}`
    : (descriptions[0] ?? "")
}

function describeTools(tools: string[]): string {
  const first = tools[0]?.replaceAll("_", " ") ?? "Inspect retained activity"
  return tools.length === 1
    ? capitalize(first)
    : `${capitalize(first)} and ${tools.length - 1} more call${tools.length === 2 ? "" : "s"}`
}

function iterationTitle(
  number: number,
  roomTitle: string | null,
  tools: string[],
  plan: SessionEvidenceRecord | undefined
): string {
  const normalized = tools.map((tool) => tool.toLowerCase())
  if (normalized.includes("look") && normalized.includes("check")) {
    return "Orient in the world"
  }
  if (
    normalized.some(
      (tool) =>
        tool === "go" ||
        tool === "move" ||
        tool === "travel" ||
        tool.startsWith("move_")
    )
  ) {
    return roomTitle ? `Move to ${roomTitle}` : "Continue navigating"
  }
  if (
    normalized.some(
      (tool) =>
        tool.includes("attack") ||
        tool.includes("fight") ||
        tool.includes("kill")
    )
  ) {
    return "Engage the target"
  }
  if (
    normalized.some(
      (tool) =>
        tool.includes("find") ||
        tool.includes("search") ||
        tool.includes("track")
    )
  ) {
    return "Search the current area"
  }
  if (plan !== undefined) return firstSentence(evidenceText(plan), 76)
  if (tools.length > 0) return describeTools(tools)
  return `Iteration ${number}`
}

function firstSentence(value: string, maxLength: number): string {
  const compact = value.replace(/\s+/g, " ").trim()
  const sentence = compact.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? compact
  if (sentence.length <= maxLength) return sentence
  return `${sentence.slice(0, maxLength - 1).trimEnd()}…`
}

function capitalize(value: string): string {
  return value ? `${value[0].toUpperCase()}${value.slice(1)}` : value
}

function elapsed(start: string, end: string): number {
  const duration = Date.parse(end) - Date.parse(start)
  return Number.isFinite(duration) && duration > 0 ? duration : 0
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0)
}

export {
  activeNudgeForIteration,
  compareRecords,
  evidenceText,
  iterationKey,
  projectStory,
  projectStory as projectSessionStory,
  recordFields,
  recordIndexForIteration,
  segmentTurnsByNudges,
  type EvidenceFields,
  type SessionEvidenceRecord,
  type SessionSelection,
  type SessionView,
  type StoryIteration,
  type StoryModel,
  type StoryObjectiveEpoch,
  type StoryOperatorMessage,
  type StoryStep,
  type StoryToolCycle,
  type StoryTurn,
}
