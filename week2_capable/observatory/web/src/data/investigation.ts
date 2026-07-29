export type RunSummary = {
  id: string;
  label: string;
  journey: string;
  attempt: string;
  success: boolean;
  stop_reason: string;
  iterations: number;
  cost_usd: number;
  result_mode: string;
};

export type EvidenceCitation = {
  id: string;
  source: "agent" | "gateway" | "benchmark";
  label: string;
  sequence: number | null;
  trace_id: string | null;
  excerpt: string;
};

export type InvestigationEvent = {
  seq: number;
  at: string;
  phase: string;
  label: string;
  cost_usd: number;
  duration_ms: number;
  parent: number | null;
  citation: string | null;
  attributes: Record<string, unknown>;
};

export type DiagnosticRecord = {
  id: string;
  kind:
    | "false_completion"
    | "position_ambiguity"
    | "confusion_loop"
    | "stall"
    | "parse_degradation";
  severity: "critical" | "warning" | "notice";
  title: string;
  detail: string;
  mechanism: string;
  at: number;
  evidence: string[];
};

export type EvidenceForm = {
  state: "available" | "missing";
  title: string;
  text: string;
  citations: string[];
};

export type Investigation = {
  run: RunSummary;
  events: InvestigationEvent[];
  diagnostics: DiagnosticRecord[];
  citations: EvidenceCitation[];
  lens: {
    wire: EvidenceForm;
    parsed: EvidenceForm;
    rendered: EvidenceForm;
    believed: EvidenceForm;
    truth: EvidenceForm;
  };
};

export function matchesInvestigationQuery(
  event: InvestigationEvent,
  query: string,
): boolean {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) {
    return true;
  }
  const fields = new Map([
    ["phase", event.phase],
    ["tool", String(event.attributes.tool ?? "")],
    ["iteration", String(event.attributes.iteration ?? "")],
  ]);
  return terms.every((term) => {
    const separator = term.indexOf(":");
    if (separator > 0) {
      const field = term.slice(0, separator);
      const expected = term.slice(separator + 1);
      return fields.get(field)?.toLowerCase().includes(expected) ?? false;
    }
    return `${event.label} ${event.phase} ${String(event.attributes.tool ?? "")}`
      .toLowerCase()
      .includes(term);
  });
}
