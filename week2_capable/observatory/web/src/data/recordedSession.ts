export type RecordedSessionCatalogItem = {
  id: string;
  source_kind: "experiment_sample";
  player_id: string;
  label: string;
  journey: string;
  attempt: string;
  success: boolean;
  stop_reason: string;
  iterations: number;
  cost_usd: number;
  result_mode: string;
};

export type SessionEvidenceForm =
  | "wire"
  | "parsed"
  | "rendered"
  | "believed"
  | "truth";

export type SessionEvidenceRecord = {
  id: string;
  parent_id: string | null;
  source: "agent" | "gateway" | "benchmark";
  form: SessionEvidenceForm;
  kind: string;
  label: string;
  sequence: number;
  at: string;
  trace_id: string | null;
  iteration: number | null;
  turn: number | null;
  room_id: string | null;
  duration_ms: number;
  cost_usd: number;
  tokens: number;
  status: "complete" | "partial" | "failed" | "unknown";
  preview: string;
  fields: Record<string, unknown>;
  source_ref: string;
  capture_gaps: string[];
};

export type SessionDiagnosticKind =
  | "false_completion"
  | "belief_divergence"
  | "position_ambiguity"
  | "confusion_loop"
  | "progress_stall"
  | "parse_degradation"
  | "corrective_call_cluster"
  | "stale_action"
  | "context_churn"
  | "instrumentation_gap";

export type SessionDiagnostic = {
  id: string;
  kind: SessionDiagnosticKind;
  severity: "critical" | "warning" | "notice";
  state: "open" | "acknowledged" | "resolved";
  title: string;
  consequence: string;
  rule_version: string;
  threshold: string;
  at_record: string;
  evidence: string[];
  alternatives: string[];
  affected_conclusions: string[];
  resolution: string | null;
  related_occurrences: string[];
};

export type SessionEvidenceLens = Record<
  SessionEvidenceForm,
  {
    state: "available" | "missing";
    title: string;
    text: string;
    citations: string[];
  }
>;

export type SessionWorldNode = WorldNodeData;

export type SessionCostPoint = {
  record_id: string;
  iteration: number | null;
  cost_usd: number;
  raw_response_cost_usd: number;
  pricing_source: "attempt_cost_curve" | "agent_response";
  fresh_input_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  output_tokens: number;
  context_tokens: number;
  progress: string;
};

export type RecordedSessionInvestigation = {
  version: number;
  source_kind: "experiment_sample";
  correlation: string;
  run: Omit<RecordedSessionCatalogItem, "source_kind" | "player_id">;
  player_id: string;
  agent_session_id: string | null;
  gateway_session_id: string | null;
  objective: string | null;
  model: string | null;
  records: SessionEvidenceRecord[];
  diagnostics: SessionDiagnostic[];
  diagnostic_coverage: SessionDiagnosticKind[];
  lens: SessionEvidenceLens;
  world: WorldProjectionData;
  cost: {
    total_usd: number;
    response_total_usd: number;
    raw_response_total_usd: number;
    reconciliation_delta_usd: number;
    complete: boolean;
    completeness_detail: string;
    fresh_input_tokens: number;
    cache_read_tokens: number;
    cache_write_tokens: number;
    output_tokens: number;
    points: SessionCostPoint[];
  };
  capture_gaps: string[];
};

export type SessionsLens =
  | "story"
  | "sequence"
  | "evidence"
  | "cost"
  | "diagnostics";

export function matchesSessionQuery(
  record: SessionEvidenceRecord,
  query: string,
): boolean {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const fields = new Map([
    ["source", record.source],
    ["form", record.form],
    ["kind", record.kind],
    ["trace", record.trace_id ?? ""],
    ["room", record.room_id ?? ""],
    ["turn", String(record.turn ?? "")],
    ["iteration", String(record.iteration ?? "")],
  ]);
  return terms.every((term) => {
    const separator = term.indexOf(":");
    if (separator > 0) {
      const field = term.slice(0, separator);
      const expected = term.slice(separator + 1);
      return fields.get(field)?.toLowerCase().includes(expected) ?? false;
    }
    return [
      record.label,
      record.preview,
      record.kind,
      record.source_ref,
    ].join(" ").toLowerCase().includes(term);
  });
}

export function recordAncestry(
  records: SessionEvidenceRecord[],
  selected: SessionEvidenceRecord,
): SessionEvidenceRecord[] {
  const byId = new Map(records.map((record) => [record.id, record]));
  const ancestry: SessionEvidenceRecord[] = [selected];
  const visited = new Set([selected.id]);
  let parent = selected.parent_id;
  while (parent !== null && !visited.has(parent)) {
    const record = byId.get(parent);
    if (record === undefined) break;
    ancestry.unshift(record);
    visited.add(record.id);
    parent = record.parent_id;
  }
  return ancestry;
}
import type {
  WorldNodeData,
  WorldProjectionData,
} from "./worldContracts";
