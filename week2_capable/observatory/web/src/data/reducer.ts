import type { ChronicleEvent } from "../app/types";
import type { EventEnvelope } from "./contracts";

const KNOWN_KINDS = new Set([
  "admin_operation",
  "login",
  "login_failed",
  "observation",
  "parse_metric",
  "position",
  "session_close",
  "session_open",
  "status",
  "surface_profile",
  "tool_call",
  "tool_rejected",
  "tool_result",
  "unparsed",
  "wire",
]);

export type SequenceGap = {
  first: number;
  last: number;
};

export type EvidenceState = {
  session: string;
  events: EventEnvelope[];
  latestSeq: number;
  selectedSeq: number;
  followingLive: boolean;
  gaps: SequenceGap[];
  unknownKinds: string[];
};

export type SelectedProjection = {
  throughSeq: number;
  events: EventEnvelope[];
  roomTitle: string | null;
  roomConfidence: string | null;
  positionTitle: string | null;
  positionConfidence: string | null;
  parseMissRate: number | null;
};

export function createEvidenceState(session: string): EvidenceState {
  return {
    session,
    events: [],
    latestSeq: 0,
    selectedSeq: 0,
    followingLive: true,
    gaps: [],
    unknownKinds: [],
  };
}

export function ingestEvidence(
  state: EvidenceState,
  incoming: EventEnvelope[],
): EvidenceState {
  const bySequence = new Map(state.events.map((event) => [event.seq, event]));
  for (const event of incoming) {
    if (state.session && event.session !== state.session) {
      continue;
    }
    bySequence.set(event.seq, event);
  }
  const events = [...bySequence.values()].sort((left, right) => left.seq - right.seq);
  const latestSeq = events.at(-1)?.seq ?? 0;
  return {
    ...state,
    session: state.session || events[0]?.session || "",
    events,
    latestSeq,
    selectedSeq: state.followingLive ? latestSeq : state.selectedSeq,
    gaps: sequenceGaps(events),
    unknownKinds: [...new Set(
      events.filter((event) => !KNOWN_KINDS.has(event.kind)).map((event) => event.kind),
    )].sort(),
  };
}

export function selectSequence(
  state: EvidenceState,
  sequence: number,
): EvidenceState {
  return {
    ...state,
    selectedSeq: Math.max(0, Math.min(sequence, state.latestSeq)),
    followingLive: false,
  };
}

export function resumeLive(state: EvidenceState): EvidenceState {
  return {
    ...state,
    selectedSeq: state.latestSeq,
    followingLive: true,
  };
}

export function selectedProjection(state: EvidenceState): SelectedProjection {
  const events = state.events.filter((event) => event.seq <= state.selectedSeq);
  const room = findLatest(events, (event) => (
    event.kind === "observation" && event.data.kind === "room"
  ));
  const position = findLatest(events, (event) => event.kind === "position");
  const metric = findLatest(events, (event) => event.kind === "parse_metric");
  return {
    throughSeq: state.selectedSeq,
    events,
    roomTitle: stringValue(room?.data.title),
    roomConfidence: stringValue(room?.data.confidence),
    positionTitle: stringValue(position?.data.title),
    positionConfidence: stringValue(position?.data.confidence),
    parseMissRate: numberValue(metric?.data.cumulative_miss_rate),
  };
}

export function toChronicle(events: EventEnvelope[]): ChronicleEvent[] {
  return events.slice(-40).map((event) => ({
    seq: event.seq,
    label: eventLabel(event),
    kind: chronicleKind(event.kind),
    cost: numberValue(event.data.cost_usd) ?? numberValue(event.data.cost) ?? 0,
    duration: numberValue(event.data.duration_ms) ?? 0,
  }));
}

function sequenceGaps(events: EventEnvelope[]): SequenceGap[] {
  const gaps: SequenceGap[] = [];
  let expected = 1;
  for (const event of events) {
    if (event.seq > expected) {
      gaps.push({ first: expected, last: event.seq - 1 });
    }
    expected = event.seq + 1;
  }
  return gaps;
}

function findLatest(
  events: EventEnvelope[],
  predicate: (event: EventEnvelope) => boolean,
): EventEnvelope | undefined {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event !== undefined && predicate(event)) {
      return event;
    }
  }
  return undefined;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function eventLabel(event: EventEnvelope): string {
  if (event.kind === "observation") {
    return stringValue(event.data.title) ?? stringValue(event.data.kind) ?? "Observation";
  }
  if (event.kind === "position") {
    return stringValue(event.data.title) ?? "Position update";
  }
  if (event.kind === "tool_call" || event.kind === "tool_result") {
    return stringValue(event.data.tool) ?? event.kind.replace("_", " ");
  }
  if (event.kind === "wire") {
    const direction = stringValue(event.data.direction);
    return direction ? `${direction} wire frame` : "Wire frame";
  }
  return event.kind.replaceAll("_", " ");
}

function chronicleKind(kind: string): ChronicleEvent["kind"] {
  if (kind === "tool_call" || kind === "tool_result") {
    return "tool";
  }
  if (kind === "wire") {
    return "wire";
  }
  if (kind === "observation" || kind === "position" || kind === "unparsed") {
    return "observation";
  }
  if (kind.includes("diagnostic")) {
    return "diagnostic";
  }
  return "model";
}
