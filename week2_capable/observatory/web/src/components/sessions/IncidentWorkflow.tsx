import {
  Bookmark,
  Download,
  FileCheck2,
  MessageSquarePlus,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  annotationKey,
  exportIncident,
  type InvestigatorAnnotation,
} from "../../data/incidents";
import type { SessionsLens } from "../../data/recordedSession";

type Props = {
  runId: string;
  selectedRecordId: string | null;
  diagnosticId: string | null;
  lens: SessionsLens;
  mode: "recorded" | "offline";
  initialAnnotations: InvestigatorAnnotation[];
  sourceVersions: Record<string, string>;
  redactionPolicy: string | null;
};

export function IncidentWorkflow({
  runId,
  selectedRecordId,
  diagnosticId,
  lens,
  mode,
  initialAnnotations,
  sourceVersions,
  redactionPolicy,
}: Props) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [annotations, setAnnotations] = useState<InvestigatorAnnotation[]>(
    () => (
      mode === "offline"
        ? initialAnnotations
        : loadAnnotations(runId)
    ),
  );
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selectedAnnotations = useMemo(
    () => annotations.filter((item) => item.target_id === selectedRecordId),
    [annotations, selectedRecordId],
  );

  useEffect(() => {
    setAnnotations(
      mode === "offline"
        ? initialAnnotations
        : loadAnnotations(runId),
    );
  }, [initialAnnotations, mode, runId]);

  useEffect(() => {
    if (mode !== "recorded") return;
    try {
      localStorage.setItem(annotationKey(runId), JSON.stringify(annotations));
    } catch {
      setError("Annotations cannot be persisted in this browser.");
    }
  }, [annotations, mode, runId]);

  const addAnnotation = (bookmark: boolean, text: string) => {
    if (!selectedRecordId || !text.trim()) return;
    if (
      bookmark
      && annotations.some(
        (item) => item.bookmark && item.target_id === selectedRecordId,
      )
    ) return;
    setAnnotations((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        target_id: selectedRecordId,
        bookmark,
        text: text.trim(),
        created_at: new Date().toISOString(),
      },
    ]);
  };

  return (
    <>
      <button
        aria-expanded={open}
        className="secondary-button"
        type="button"
        onClick={() => setOpen((value) => !value)}
      >
        <FileCheck2 size={14} aria-hidden="true" />
        Incident
        {annotations.length > 0 ? <span>{annotations.length}</span> : null}
      </button>
      {open ? (
        <aside className="incident-panel" aria-label="Incident workflow">
          <header>
            <span>
              <p className="eyebrow">
                {mode === "offline" ? "Offline capsule" : "Portable investigation"}
              </p>
              <h2>Incident workflow</h2>
            </span>
            <button
              aria-label="Close incident workflow"
              className="icon-button"
              type="button"
              onClick={() => setOpen(false)}
            >
              <X size={15} aria-hidden="true" />
            </button>
          </header>

          {mode === "offline" ? (
            <section className="incident-proof">
              <FileCheck2 size={18} aria-hidden="true" />
              <span>
                <strong>Integrity verified before opening</strong>
                <small>{redactionPolicy ?? "Sanitized portable evidence"}</small>
              </span>
              <dl>
                {Object.entries(sourceVersions).map(([name, version]) => (
                  <div key={name}><dt>{name}</dt><dd>{version}</dd></div>
                ))}
              </dl>
            </section>
          ) : (
            <>
              <section className="incident-selection">
                <span>Selected evidence</span>
                <strong>{selectedRecordId ?? "Select one record"}</strong>
                <small>
                  The export is limited to this chronological prefix and its
                  retained diagnostic evidence.
                </small>
              </section>
              <div className="incident-actions">
                <button
                  className="secondary-button"
                  disabled={!selectedRecordId}
                  type="button"
                  onClick={() => addAnnotation(true, "Bookmarked evidence")}
                >
                  <Bookmark size={14} aria-hidden="true" />
                  Bookmark
                </button>
                <button
                  className="primary-button"
                  disabled={!selectedRecordId}
                  type="button"
                  onClick={() => {
                    if (!selectedRecordId) return;
                    setError(null);
                    setStatus("Renewing redaction and sealing capsule…");
                    void exportIncident({
                      runId,
                      selectedRecordId,
                      diagnosticId,
                      lens,
                      annotations,
                    })
                      .then((blob) => {
                        download(blob, `boukensha-${runId}-incident.json`);
                        setStatus("Sanitized capsule exported.");
                      })
                      .catch((failure: unknown) => {
                        setStatus(null);
                        setError(
                          failure instanceof Error
                            ? failure.message
                            : "Incident export failed.",
                        );
                      });
                  }}
                >
                  <Download size={14} aria-hidden="true" />
                  Export capsule
                </button>
              </div>
              <label className="incident-note">
                <span>Add context to the selected evidence</span>
                <textarea
                  maxLength={2_000}
                  placeholder="What should another investigator understand?"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                />
              </label>
              <button
                className="text-button"
                disabled={!note.trim() || !selectedRecordId}
                type="button"
                onClick={() => {
                  addAnnotation(false, note);
                  setNote("");
                }}
              >
                <MessageSquarePlus size={13} aria-hidden="true" />
                Attach note
              </button>
            </>
          )}

          <section className="incident-annotations">
            <p className="eyebrow">Annotations at this evidence</p>
            {selectedAnnotations.map((item) => (
              <article key={item.id}>
                {item.bookmark ? <Bookmark size={13} aria-label="Bookmark" /> : null}
                <span>{item.text}</span>
                <time>{new Date(item.created_at).toLocaleString()}</time>
              </article>
            ))}
            {selectedAnnotations.length === 0 ? (
              <p>No annotation is attached to this evidence.</p>
            ) : null}
          </section>
          {status ? <p className="form-success" role="status">{status}</p> : null}
          {error ? <p className="form-error" role="alert">{error}</p> : null}
        </aside>
      ) : null}
    </>
  );
}

function loadAnnotations(runId: string): InvestigatorAnnotation[] {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem(annotationKey(runId)) ?? "[]",
    );
    if (!Array.isArray(value)) return [];
    return value.filter(isAnnotation);
  } catch {
    return [];
  }
}

function isAnnotation(value: unknown): value is InvestigatorAnnotation {
  if (value === null || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.id === "string"
    && typeof record.target_id === "string"
    && typeof record.bookmark === "boolean"
    && typeof record.text === "string"
    && typeof record.created_at === "string";
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}
