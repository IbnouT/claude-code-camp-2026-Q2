import type { Investigation } from "./investigation";

export type KnowledgeMetric = {
  label: string;
  value: number | string;
  detail: string;
};

export type FrontierItem = {
  id: string;
  title: string;
  kind: "unresolved_position" | "untraversed_exit" | "missing_source";
  detail: string;
  citations: string[];
};

export type KnowledgeOverview = {
  state: "ready" | "partial" | "unavailable";
  source: string;
  metrics: KnowledgeMetric[];
  frontier: FrontierItem[];
  entities: string[];
  player: Record<string, string | number>;
  progression: string[];
  missing_layers: string[];
};

export type DiagnosticHistoryItem = {
  kind: string;
  runs: number;
  critical: number;
  warning: number;
  notice: number;
  latest_run: string;
};

export type DiagnosticHistory = {
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  items: DiagnosticHistoryItem[];
};

export type InvestigatorAnnotation = {
  id: string;
  at: number;
  text: string;
  created_at: string;
};

export type IncidentCapsule = {
  kind: "boukensha.observatory.incident";
  version: 1;
  digest: string;
  payload: {
    generated_at: string;
    title: string;
    source_versions: Record<string, string>;
    investigation: Investigation;
    knowledge: KnowledgeOverview;
    history: DiagnosticHistory;
    selection: {
      selected_sequence: number;
      diagnostic_id: string | null;
    };
    annotations: InvestigatorAnnotation[];
    redaction: {
      policy: string;
      replacements: number;
      local_paths_included: false;
      credentials_included: false;
    };
  };
};

export async function exportIncident(
  runId: string,
  selectedSequence: number,
  diagnosticId: string | null,
  annotations: InvestigatorAnnotation[],
): Promise<Blob> {
  const response = await fetch("/api/incidents/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      selected_sequence: selectedSequence,
      diagnostic_id: diagnosticId,
      annotations,
    }),
  });
  if (!response.ok) {
    throw new Error("The incident could not be exported.");
  }
  return response.blob();
}

export async function readIncident(file: File): Promise<IncidentCapsule> {
  const value: unknown = JSON.parse(await file.text());
  if (!isCapsule(value)) {
    throw new Error("This file is not a supported Boukensha incident.");
  }
  const digest = await sha256(JSON.stringify(value.payload));
  if (digest !== value.digest) {
    throw new Error("Integrity check failed. The incident was modified.");
  }
  return value;
}

export function annotationKey(runId: string): string {
  return `boukensha:annotations:${runId}`;
}

function isCapsule(value: unknown): value is IncidentCapsule {
  if (value === null || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  if (
    record.kind !== "boukensha.observatory.incident"
    || record.version !== 1
    || typeof record.digest !== "string"
    || record.payload === null
    || typeof record.payload !== "object"
  ) {
    return false;
  }
  const payload = record.payload as Record<string, unknown>;
  if (
    !isRecord(payload.investigation)
    || !isRecord(payload.investigation.run)
    || typeof payload.investigation.run.id !== "string"
    || typeof payload.investigation.run.label !== "string"
    || typeof payload.investigation.run.journey !== "string"
    || !Array.isArray(payload.investigation.events)
    || !Array.isArray(payload.investigation.diagnostics)
    || !Array.isArray(payload.investigation.citations)
    || !isRecord(payload.investigation.world)
    || !isRecord(payload.knowledge)
    || !Array.isArray(payload.knowledge.metrics)
    || !Array.isArray(payload.knowledge.frontier)
    || !Array.isArray(payload.knowledge.missing_layers)
    || !isRecord(payload.history)
    || typeof payload.history.total_runs !== "number"
    || !Array.isArray(payload.history.items)
    || !isRecord(payload.selection)
    || typeof payload.selection.selected_sequence !== "number"
    || !Array.isArray(payload.annotations)
    || !payload.annotations.every(isAnnotation)
    || !isRecord(payload.redaction)
    || payload.redaction.local_paths_included !== false
    || payload.redaction.credentials_included !== false
  ) {
    return false;
  }
  return true;
}

async function sha256(value: string): Promise<string> {
  const buffer = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return [...new Uint8Array(buffer)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isAnnotation(value: unknown): boolean {
  return isRecord(value)
    && typeof value.id === "string"
    && typeof value.at === "number"
    && typeof value.text === "string"
    && typeof value.created_at === "string";
}
