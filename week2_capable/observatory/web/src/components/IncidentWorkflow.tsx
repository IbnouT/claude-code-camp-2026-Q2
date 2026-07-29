import {
  Archive,
  BadgeCheck,
  BookOpen,
  Download,
  FileInput,
  Flag,
  History,
  MessageSquarePlus,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type { Investigation } from "../data/investigation";
import {
  annotationKey,
  exportIncident,
  readIncident,
  type DiagnosticHistory,
  type IncidentCapsule,
  type InvestigatorAnnotation,
  type KnowledgeOverview,
} from "../data/incidents";

type Props = {
  open: boolean;
  investigation: Investigation | null;
  runId: string | null;
  selected: number;
  diagnosticId: string | null;
  capsule: IncidentCapsule | null;
  onClose: () => void;
  onOpenCapsule: (capsule: IncidentCapsule) => void;
};

export function IncidentWorkflow({
  open,
  investigation,
  runId,
  selected,
  diagnosticId,
  capsule,
  onClose,
  onOpenCapsule,
}: Props) {
  const [knowledge, setKnowledge] = useState<KnowledgeOverview | null>(null);
  const [history, setHistory] = useState<DiagnosticHistory | null>(null);
  const [annotations, setAnnotations] = useState<InvestigatorAnnotation[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const activeRun = investigation?.run.id ?? runId;

  useEffect(() => {
    if (!open) return;
    if (capsule !== null) {
      setKnowledge(capsule.payload.knowledge);
      setHistory(capsule.payload.history);
      setAnnotations(capsule.payload.annotations);
      return;
    }
    if (activeRun === null) return;
    const abort = new AbortController();
    void Promise.all([
      fetch(`/api/runs/${encodeURIComponent(activeRun)}/knowledge`, {
        signal: abort.signal,
      }).then((response) => response.ok ? response.json() : null),
      fetch("/api/diagnostic-history", { signal: abort.signal })
        .then((response) => response.ok ? response.json() : null),
    ]).then(([nextKnowledge, nextHistory]: [
      KnowledgeOverview | null,
      DiagnosticHistory | null,
    ]) => {
      setKnowledge(nextKnowledge);
      setHistory(nextHistory);
    }).catch(() => undefined);
    const saved = window.localStorage.getItem(annotationKey(activeRun));
    setAnnotations(saved === null
      ? []
      : JSON.parse(saved) as InvestigatorAnnotation[]);
    return () => abort.abort();
  }, [activeRun, capsule, open]);

  const coverage = useMemo(() => {
    if (history === null || history.total_runs === 0) return 0;
    return Math.round(
      (history.successful_runs / history.total_runs) * 100,
    );
  }, [history]);

  if (!open) return null;

  const addAnnotation = () => {
    const text = draft.trim();
    if (text === "" || activeRun === null) return;
    const note: InvestigatorAnnotation = {
      id: crypto.randomUUID(),
      at: selected,
      text,
      created_at: new Date().toISOString(),
    };
    const next = [...annotations, note];
    setAnnotations(next);
    setDraft("");
    if (capsule === null) {
      window.localStorage.setItem(annotationKey(activeRun), JSON.stringify(next));
    }
  };

  const download = async () => {
    if (activeRun === null || capsule !== null) return;
    setExporting(true);
    setError(null);
    try {
      const blob = await exportIncident(
        activeRun,
        selected,
        diagnosticId,
        annotations,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `boukensha-${investigation?.run.journey.toLowerCase() ?? "run"}-incident.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  const openFile = async (file: File | undefined) => {
    if (file === undefined) return;
    setError(null);
    try {
      onOpenCapsule(await readIncident(file));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Open failed.");
    }
  };

  return (
    <div className="incident-backdrop" role="presentation">
      <section
        className="incident-workflow"
        role="dialog"
        aria-modal="true"
        aria-labelledby="incident-title"
      >
        <header className="incident-header">
          <div>
            <span className="incident-mark"><Archive size={17} /></span>
            <span>
              <p className="eyebrow">Evidence handoff</p>
              <h2 id="incident-title">
                {capsule?.payload.title ?? investigation?.run.label ?? "Open incident"}
              </h2>
            </span>
          </div>
          <button type="button" aria-label="Close incident workflow" onClick={onClose}>
            <X size={16} />
          </button>
        </header>

        <div className="incident-trust-strip">
          <span><ShieldCheck size={13} /> Read-only evidence</span>
          <span><BadgeCheck size={13} /> Integrity sealed</span>
          <span>
            {capsule === null ? "Live source attached" : "Offline capsule"}
          </span>
          {capsule !== null && <code>{capsule.digest.slice(0, 12)}</code>}
        </div>

        <div className="incident-body">
          <div className="incident-primary">
            <section className="knowledge-overview">
              <header>
                <div>
                  <p className="eyebrow">Knowledge coverage</p>
                  <h3>What is known, and where it ends</h3>
                </div>
                <span className={`knowledge-state state-${knowledge?.state ?? "unavailable"}`}>
                  {knowledge?.state ?? "unavailable"}
                </span>
              </header>
              <div className="knowledge-metrics">
                {knowledge?.metrics.map((metric) => (
                  <article key={metric.label} title={metric.detail}>
                    <strong>{typeof metric.value === "number" && metric.value < 1
                      ? `${(metric.value * 100).toFixed(1)}%`
                      : metric.value}</strong>
                    <span>{metric.label}</span>
                  </article>
                ))}
              </div>
              <div className="frontier-list">
                <header>
                  <span><Flag size={12} /> Frontier</span>
                  <small>{knowledge?.frontier.length ?? 0} open edges</small>
                </header>
                {(knowledge?.frontier ?? []).slice(0, 5).map((item) => (
                  <article key={item.id}>
                    <BookOpen size={12} />
                    <span><strong>{item.title}</strong><small>{item.detail}</small></span>
                  </article>
                ))}
                {(knowledge?.frontier.length ?? 0) === 0 && (
                  <p>No frontier is derivable from the available evidence.</p>
                )}
              </div>
              {(knowledge?.missing_layers.length ?? 0) > 0 && (
                <p className="missing-layers">
                  Missing, not inferred: {knowledge?.missing_layers.join(" · ")}
                </p>
              )}
            </section>

            <section className="history-overview">
              <header>
                <div>
                  <p className="eyebrow">Diagnostic history</p>
                  <h3>Patterns across recorded runs</h3>
                </div>
                <span>{history?.total_runs ?? 0} runs</span>
              </header>
              <div className="history-summary">
                <div className="history-ring" style={{ "--coverage": `${coverage}%` } as CSSProperties}>
                  <strong>{coverage}%</strong><small>success</small>
                </div>
                <div className="history-list">
                  {history?.items.slice(0, 5).map((item) => (
                    <article key={item.kind}>
                      <span>{item.kind.replaceAll("_", " ")}</span>
                      <div><i style={{ width: `${Math.max(8, item.runs / history.total_runs * 100)}%` }} /></div>
                      <strong>{item.runs}</strong>
                    </article>
                  ))}
                </div>
              </div>
            </section>
          </div>

          <aside className="incident-notes">
            <header>
              <div>
                <p className="eyebrow">Investigator layer</p>
                <h3>Annotations</h3>
              </div>
              <MessageSquarePlus size={15} />
            </header>
            <p className="annotation-boundary">
              Notes are visibly separate from source evidence and never change a diagnostic.
            </p>
            <div className="annotation-list">
              {annotations.map((annotation) => (
                <article key={annotation.id}>
                  <span>Sequence {annotation.at}</span>
                  <p>{annotation.text}</p>
                  <small>{new Date(annotation.created_at).toLocaleString()}</small>
                </article>
              ))}
            </div>
            {activeRun !== null && (
              <div className="annotation-compose">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder={`Add context at sequence ${selected}`}
                  maxLength={2000}
                />
                <button type="button" onClick={addAnnotation}>Add note</button>
              </div>
            )}
          </aside>
        </div>

        <footer className="incident-footer">
          <div>
            <History size={13} />
            <span>
              {capsule === null
                ? "The capsule contains evidence, projections, notes, and source versions."
                : `${capsule.payload.redaction.replacements} sensitive values removed at export.`}
            </span>
          </div>
          {error !== null && <p role="alert">{error}</p>}
          <label className="incident-action secondary">
            <FileInput size={13} />
            Open capsule
            <input
              type="file"
              accept=".json,application/vnd.boukensha.incident+json"
              onChange={(event) => void openFile(event.target.files?.[0])}
            />
          </label>
          {capsule === null && activeRun !== null && (
            <button
              type="button"
              className="incident-action primary"
              disabled={exporting}
              onClick={() => void download()}
            >
              <Download size={13} />
              {exporting ? "Sealing…" : "Export handoff"}
            </button>
          )}
        </footer>
      </section>
    </div>
  );
}
