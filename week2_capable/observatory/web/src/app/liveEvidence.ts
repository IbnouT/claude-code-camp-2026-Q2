import type { WorkspaceFixture } from "./shellTypes";
import type { EventEnvelope } from "../data/contracts";
import type { LiveSessionState } from "../data/liveContracts";

type Evidence = WorkspaceFixture["evidence"];
type EvidenceValue = Evidence[keyof Evidence];

const missing = (preview: string): EvidenceValue => ({
  state: "missing",
  preview,
});

const available = (preview: string): EvidenceValue => ({
  state: "available",
  preview,
});

export function liveEvidenceForms(
  evidenceId: string | null,
  live: LiveSessionState,
): Evidence | null {
  if (evidenceId === null || live.snapshot === null) {
    return null;
  }
  const item = live.snapshot.timeline.find(
    (candidate) => candidate.id === evidenceId,
  );
  if (item === undefined) {
    return null;
  }
  const gateway = item.source === "gateway"
    ? live.events.find((event) => event.seq === item.sequence)
    : undefined;
  const wire = gateway === undefined
    ? undefined
    : correlatedWire(gateway, live.events);
  const agentLine = parseAgentLine(item.id);
  const believed = (
    agentLine !== null
    && live.snapshot.agent_belief?.line === agentLine
  )
    ? live.snapshot.agent_belief
    : (
      agentLine !== null
      && live.snapshot.agent_thought?.line === agentLine
        ? live.snapshot.agent_thought
        : null
    );
  const zone = live.snapshot.zone;
  const truthApplies = zone !== null && (
    zone.reset_sequence === item.sequence
    || zone.movement_sequences.includes(item.sequence)
  );

  return {
    wire: wire
      ? available(formatEvent(wire))
      : missing(
        "Wire bytes for this selected event are not retained in the live client.",
      ),
    parsed: gateway
      ? available(formatEvent(gateway))
      : missing("No parsed gateway form is retained for this selected event."),
    rendered: missing(
      "No model-facing rendered form is retained for this selected event.",
    ),
    believed: believed
      ? available(believed.text)
      : missing("No correlated agent belief is retained for this selected event."),
    truth: truthApplies
      ? available(
        `Observer atlas correlation: Zone ${zone.label}, room ${zone.room_vnum}.`,
      )
      : missing("Observer truth is not configured for this live session."),
  };
}

function correlatedWire(
  event: EventEnvelope,
  events: EventEnvelope[],
): EventEnvelope | undefined {
  const reference = event.data.wire_ref;
  if (
    typeof reference !== "object"
    || reference === null
    || Array.isArray(reference)
  ) {
    return undefined;
  }
  const fields = reference as Record<string, unknown>;
  const first = fields.first_seq;
  const last = fields.last_seq;
  if (!Number.isInteger(first) || !Number.isInteger(last)) {
    return undefined;
  }
  return events.find(
    (candidate) => (
      candidate.kind === "wire"
      && candidate.seq >= Number(first)
      && candidate.seq <= Number(last)
      && candidate.data.direction === "in"
    ),
  );
}

function parseAgentLine(id: string): number | null {
  if (!id.startsWith("agent-")) {
    return null;
  }
  const line = Number(id.slice("agent-".length));
  return Number.isInteger(line) && line >= 0 ? line : null;
}

function formatEvent(event: EventEnvelope): string {
  return JSON.stringify({
    sequence: event.seq,
    kind: event.kind,
    trace_id: event.trace_id,
    data: event.data,
  }, null, 2);
}
