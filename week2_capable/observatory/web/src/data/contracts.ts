export type JsonObject = Record<string, unknown>;

export type EventEnvelope = {
  seq: number;
  session: string;
  at: number;
  kind: string;
  trace_id: string | null;
  data: JsonObject;
};

const EVENT_FIELDS = ["seq", "session", "at", "kind", "trace_id", "data"];
const REQUIRED_EVENT_FIELDS = ["seq", "session", "at", "kind", "data"];

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function decodeEvent(value: unknown): EventEnvelope {
  if (!isObject(value)) {
    throw new Error("event must be an object");
  }
  if (!Number.isInteger(value.seq) || Number(value.seq) <= 0) {
    throw new Error("event seq must be a positive integer");
  }
  if (typeof value.session !== "string" || value.session.length === 0) {
    throw new Error("event session must be a non-empty string");
  }
  if (typeof value.at !== "number" || !Number.isFinite(value.at)) {
    throw new Error("event at must be a finite number");
  }
  if (typeof value.kind !== "string" || value.kind.length === 0) {
    throw new Error("event kind must be a non-empty string");
  }
  if (value.trace_id !== null && typeof value.trace_id !== "string") {
    throw new Error("event trace_id must be a string or null");
  }
  if (!isObject(value.data)) {
    throw new Error("event data must be an object");
  }
  return {
    seq: Number(value.seq),
    session: value.session,
    at: value.at,
    kind: value.kind,
    trace_id: value.trace_id,
    data: value.data,
  };
}

export function assertCanonicalEventContract(value: unknown): void {
  if (!isObject(value) || !isObject(value.event)) {
    throw new Error("gateway contracts have no event schema");
  }
  const required = value.event.required;
  const properties = value.event.properties;
  if (!Array.isArray(required) || !required.every((item) => typeof item === "string")) {
    throw new Error("gateway event schema has no required field list");
  }
  if (!isObject(properties)) {
    throw new Error("gateway event schema has no property definitions");
  }
  const actual = [...required].sort().join(",");
  const expected = [...REQUIRED_EVENT_FIELDS].sort().join(",");
  const actualProperties = Object.keys(properties).sort().join(",");
  const expectedProperties = [...EVENT_FIELDS].sort().join(",");
  if (
    actual !== expected
    || actualProperties !== expectedProperties
    || value.event.additionalProperties !== false
  ) {
    throw new Error("gateway event schema is incompatible with this client");
  }
}
