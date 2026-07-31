import type {
  RecordedSessionInvestigation,
  SessionEvidenceRecord,
} from "../../data/recordedSession";

export type PositionedSessionNode = {
  id: string;
  title: string;
  x: number;
  y: number;
  current: boolean;
  selected: boolean;
  candidate: boolean;
};

export type SessionIteration = {
  iteration: number;
  records: SessionEvidenceRecord[];
};

export function groupSessionIterations(
  records: SessionEvidenceRecord[],
): SessionIteration[] {
  const lastIteration = Math.max(
    1,
    ...records.map((record) => record.iteration ?? 1),
  );
  const grouped = new Map<number, SessionEvidenceRecord[]>();
  for (const record of records) {
    const iteration = record.iteration
      ?? (record.source === "benchmark" ? lastIteration : 1);
    grouped.set(iteration, [...(grouped.get(iteration) ?? []), record]);
  }
  return [...grouped.entries()]
    .sort(([left], [right]) => left - right)
    .map(([iteration, items]) => ({ iteration, records: items }));
}

export function positionSessionNodes(
  investigation: RecordedSessionInvestigation,
  selectedRoomId: string | null,
): PositionedSessionNode[] {
  const positions = [
    [132, 305],
    [132, 200],
    [250, 200],
    [250, 108],
    [375, 108],
    [455, 180],
  ] as const;
  return investigation.world.nodes.slice(0, positions.length).map((node, index) => ({
    id: node.id,
    title: node.title,
    x: positions[index]?.[0] ?? 280,
    y: positions[index]?.[1] ?? 230,
    current: node.state === "current"
      || (
        investigation.world.current_title === node.title
        && investigation.world.candidates.length <= 1
      ),
    selected: node.id === selectedRoomId,
    candidate: node.state === "candidate",
  }));
}

export function effectiveSelectedRoom(
  records: SessionEvidenceRecord[],
  selectedRoomId: string | null,
  selectedRecordId: string | null,
) {
  const selectedIndex = records.findIndex(
    (record) => record.id === selectedRecordId,
  );
  const visibleRecords = selectedIndex < 0
    ? records
    : records.slice(0, selectedIndex + 1);
  return selectedRoomId
    ?? [...visibleRecords].reverse().find((record) => record.room_id)?.room_id
    ?? null;
}

export function countSessionTurns(records: SessionEvidenceRecord[]) {
  return new Set(
    records
      .filter((record) => record.turn !== null)
      .map((record) => record.turn),
  ).size;
}

export function maxSessionContextTokens(
  investigation: RecordedSessionInvestigation,
) {
  return Math.max(
    0,
    ...investigation.cost.points.map((point) => point.context_tokens),
  );
}

export function formatSessionTitle(
  investigation: RecordedSessionInvestigation,
) {
  const objective = investigation.objective ?? "";
  const focus = objective.match(
    /(?:find|reach|locate)\s+(?:the\s+)?([a-z][a-z -]*?)(?:\s+and\b|[.,]|$)/i,
  )?.[1]?.trim().toLowerCase();
  return focus
    ? `${investigation.run.journey} · ${focus}`
    : investigation.run.label;
}

export function formatSessionRecordLabel(record: SessionEvidenceRecord) {
  if (record.kind !== "tool_call") return record.label;
  const name = typeof record.fields.name === "string"
    ? record.fields.name
    : record.label.replace(/^Call\s+/, "");
  const args = isRecord(record.fields.args) ? record.fields.args : {};
  const signature = Object.entries(args)
    .map(([key, value]) => `${key}: ${JSON.stringify(value)}`)
    .join(", ");
  return signature ? `${name}(${signature})` : name;
}

export function formatSessionRecordPreview(record: SessionEvidenceRecord) {
  if (record.kind === "tool_call") {
    const args = isRecord(record.fields.args) ? record.fields.args : {};
    return Object.entries(args)
      .map(([key, value]) => `${key}: ${JSON.stringify(value)}`)
      .join("\n") || "No tool arguments were retained.";
  }
  if (record.kind === "tool_result" && typeof record.fields.result === "string") {
    try {
      const parsed: unknown = JSON.parse(record.fields.result);
      if (isRecord(parsed) && typeof parsed.text === "string") {
        return parsed.text;
      }
    } catch {
      return record.fields.result;
    }
  }
  return record.preview || "Exact retained record has no preview.";
}

export function formatSessionTokens(tokens: number) {
  return tokens >= 1_000 ? `${(tokens / 1_000).toFixed(1)}k` : String(tokens);
}

export function formatSessionDuration(durationMs: number) {
  if (durationMs >= 1_000) return `${(durationMs / 1_000).toFixed(1)}s`;
  return `${durationMs} ms`;
}

export function sessionStepKind(record: SessionEvidenceRecord) {
  if (record.kind.includes("tool") || record.source === "gateway") return "tool";
  if (record.kind === "response") return "model";
  if (record.kind.includes("plan")) return "plan";
  return "context";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
