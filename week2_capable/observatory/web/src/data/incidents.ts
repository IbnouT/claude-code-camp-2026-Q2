import type { PlayerKnowledge } from "./knowledge";
import type { RecordedSessionInvestigation, SessionsLens } from "./recordedSession";

export type DiagnosticHistoryItem = {
  kind: string;
  runs: number;
  critical: number;
  warning: number;
  notice: number;
  latest_run: string;
  run_ids: string[];
};

export type DiagnosticHistory = {
  player_id: string | null;
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  items: DiagnosticHistoryItem[];
};

export type InvestigatorAnnotation = {
  id: string;
  target_id: string;
  bookmark: boolean;
  text: string;
  created_at: string;
};

export type IncidentCapsule = {
  kind: "boukensha.observatory.incident";
  version: 2;
  digest: string;
  payload: {
    generated_at: string;
    title: string;
    source_versions: Record<string, string>;
    player_id: string;
    investigation: RecordedSessionInvestigation;
    knowledge: PlayerKnowledge;
    history: DiagnosticHistory;
    selection: {
      selected_record_id: string;
      diagnostic_id: string | null;
      lens: SessionsLens;
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

export type IncidentExport = {
  runId: string;
  selectedRecordId: string;
  diagnosticId: string | null;
  lens: SessionsLens;
  annotations: InvestigatorAnnotation[];
};

export async function exportIncident(request: IncidentExport): Promise<Blob> {
  const response = await fetch("/api/incidents/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: request.runId,
      selected_record_id: request.selectedRecordId,
      diagnostic_id: request.diagnosticId,
      lens: request.lens,
      annotations: request.annotations,
    }),
  });
  if (!response.ok) {
    const payload = await response.json() as { detail?: string };
    throw new Error(
      payload.detail ?? "The incident could not be exported.",
    );
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
  if (!isRecord(value)) return false;
  if (
    value.kind !== "boukensha.observatory.incident"
    || value.version !== 2
    || typeof value.digest !== "string"
    || !isRecord(value.payload)
  ) return false;
  const payload = value.payload;
  return (
    typeof payload.player_id === "string"
    && isRecordedInvestigation(payload.investigation)
    && isKnowledge(payload.knowledge)
    && isRecord(payload.history)
    && payload.history.player_id === payload.player_id
    && typeof payload.history.total_runs === "number"
    && Array.isArray(payload.history.items)
    && isRecord(payload.selection)
    && typeof payload.selection.selected_record_id === "string"
    && typeof payload.selection.lens === "string"
    && Array.isArray(payload.annotations)
    && payload.annotations.every(isAnnotation)
    && isRecord(payload.redaction)
    && payload.redaction.local_paths_included === false
    && payload.redaction.credentials_included === false
  );
}

function isRecordedInvestigation(value: unknown): boolean {
  return isRecord(value)
    && value.source_kind === "experiment_sample"
    && typeof value.player_id === "string"
    && isRecord(value.run)
    && typeof value.run.id === "string"
    && Array.isArray(value.records)
    && Array.isArray(value.diagnostics)
    && isRecord(value.world)
    && isRecord(value.cost)
    && Array.isArray(value.capture_gaps);
}

function isKnowledge(value: unknown): boolean {
  return isRecord(value)
    && value.version === 1
    && typeof value.player_id === "string"
    && Array.isArray(value.assertions)
    && Array.isArray(value.changes)
    && Array.isArray(value.snapshots)
    && Array.isArray(value.recoveries)
    && Array.isArray(value.capture_gaps);
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
    && typeof value.target_id === "string"
    && typeof value.bookmark === "boolean"
    && typeof value.text === "string"
    && typeof value.created_at === "string";
}
