import {
  Activity,
  BookOpen,
  FlaskConical,
  MessageSquareText,
  Moon,
  Sun,
  Telescope,
} from "lucide-react";
import { useEffect, useState } from "react";
import type {
  ExperimentCatalog,
  ExperimentComparison,
  ExperimentJob,
} from "../contracts";
import type { Theme } from "../theme";
import { ExperimentBuilder } from "./ExperimentBuilder";
import { ExperimentWorkspace } from "./ExperimentWorkspace";

type Props = {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
};

type ComparisonCatalog = {
  comparisons: Array<{ id: string; title: string; journey: string }>;
};

export function ExperimentRoute({ theme, onThemeChange }: Props) {
  const query = new URLSearchParams(window.location.search);
  const [catalog, setCatalog] = useState<ComparisonCatalog>({ comparisons: [] });
  const [comparisonId, setComparisonId] = useState(
    query.get("comparison")?.trim() ?? "",
  );
  const [comparison, setComparison] = useState<ExperimentComparison | null>(null);
  const [experimentCatalog, setExperimentCatalog] = useState<ExperimentCatalog | null>(null);
  const [jobs, setJobs] = useState<ExperimentJob[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [askOpen, setAskOpen] = useState(false);
  const [authoring, setAuthoring] = useState(
    query.get("mode") === "new",
  );

  useEffect(() => {
    const abort = new AbortController();
    Promise.all([
      fetch("/api/comparisons", { cache: "no-store", signal: abort.signal }),
      fetch("/api/experiments/jobs", { cache: "no-store", signal: abort.signal }),
      fetch("/api/experiments/catalog", { cache: "no-store", signal: abort.signal }),
    ])
      .then(async ([catalogResponse, jobsResponse, experimentCatalogResponse]) => {
        if (!catalogResponse.ok) throw new Error("Comparison catalog unavailable");
        if (!experimentCatalogResponse.ok) {
          throw new Error("Experiment registry unavailable");
        }
        const nextCatalog = await catalogResponse.json() as ComparisonCatalog;
        const nextExperimentCatalog = (
          await experimentCatalogResponse.json()
        ) as ExperimentCatalog;
        const nextJobs = jobsResponse.ok
          ? await jobsResponse.json() as { jobs: ExperimentJob[] }
          : { jobs: [] };
        setCatalog(nextCatalog);
        setExperimentCatalog(nextExperimentCatalog);
        setJobs(nextJobs.jobs);
        setComparisonId((current) => (
          nextCatalog.comparisons.some((item) => item.id === current)
            ? current
            : nextCatalog.comparisons[0]?.id ?? ""
        ));
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Experiments unavailable");
          setLoading(false);
        }
      });
    return () => abort.abort();
  }, []);

  useEffect(() => {
    if (!comparisonId) {
      setComparison(null);
      setLoading(false);
      return;
    }
    const abort = new AbortController();
    setLoading(true);
    fetch(`/api/comparisons/${encodeURIComponent(comparisonId)}`, {
      cache: "no-store",
      signal: abort.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Comparison unavailable (${response.status})`);
        return await response.json() as ExperimentComparison;
      })
      .then((payload) => {
        setComparison(payload);
        setError("");
        const url = new URL(window.location.href);
        url.pathname = "/experiments";
        url.searchParams.set("comparison", payload.id);
        window.history.replaceState(null, "", url);
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Comparison unavailable");
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [comparisonId]);

  return (
    <div className="experiments-shell">
      <header className="live-header">
        <a className="live-brand" href="/" aria-label="Boukensha Observatory launcher">
          <span className="live-brand-mark"><Telescope size={19} /></span>
          <span className="live-brand-name">
            <strong>Boukensha</strong><small>Observatory</small>
          </span>
        </a>
        <nav className="live-nav" aria-label="Observatory spaces">
          <a className="live-nav-link" href="/"><Activity size={15} /><span>Live</span></a>
          <a className="live-nav-link" href="/sessions"><Telescope size={15} /><span>Sessions</span></a>
          <button aria-current="page" className="live-nav-link" type="button">
            <FlaskConical size={15} /><span>Experiments</span>
          </button>
          <button aria-disabled="true" className="live-nav-link" type="button">
            <BookOpen size={15} /><span>Knowledge</span>
          </button>
        </nav>
        <div className="experiment-header-context">
          <label>
            <span>Comparison</span>
            <select
              aria-label="Comparison"
              value={comparisonId}
              onChange={(event) => setComparisonId(event.target.value)}
            >
              {catalog.comparisons.map((item) => (
                <option key={item.id} value={item.id}>{item.title}</option>
              ))}
            </select>
          </label>
          <button
            className="experiment-new"
            type="button"
            onClick={() => {
              setAuthoring(true);
              const url = new URL(window.location.href);
              url.searchParams.set("mode", "new");
              window.history.replaceState(null, "", url);
            }}
          >
            <FlaskConical size={14} />
            New experiment
          </button>
          <button className="live-header-action live-ask-action" type="button" onClick={() => setAskOpen(true)}>
            <MessageSquareText size={14} /><span>Ask this experiment</span><kbd>⌘K</kbd>
          </button>
          <button
            aria-label={`Use ${theme === "dark" ? "light" : "dark"} theme`}
            className="live-icon-button"
            type="button"
            onClick={() => onThemeChange(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>
      {authoring && experimentCatalog !== null ? (
        <ExperimentBuilder
          catalog={experimentCatalog}
          onClose={() => {
            setAuthoring(false);
            const url = new URL(window.location.href);
            url.searchParams.delete("mode");
            window.history.replaceState(null, "", url);
          }}
          onJobCreated={(job) => {
            setJobs((current) => [
              job,
              ...current.filter((item) => item.id !== job.id),
            ]);
            setAuthoring(false);
          }}
        />
      ) : (
        <ExperimentWorkspace
          comparison={comparison}
          jobs={jobs}
          loading={loading}
          error={error}
        />
      )}
      {askOpen && comparison !== null ? (
        <ExperimentAsk
          comparisonId={comparison.id}
          onClose={() => setAskOpen(false)}
        />
      ) : null}
    </div>
  );
}

function ExperimentAsk({
  comparisonId,
  onClose,
}: {
  comparisonId: string;
  onClose: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  return (
    <div className="live-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        aria-label="Ask about this experiment"
        aria-modal="true"
        className="live-ask-dialog"
        role="dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <form
          className="live-ask-query"
          onSubmit={(event) => {
            event.preventDefault();
            if (!question.trim() || loading) return;
            setLoading(true);
            setError("");
            fetch("/api/ask", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                question: question.trim(),
                scope: { space: "experiments", comparison_id: comparisonId },
                allow_model: false,
                allow_summary: false,
              }),
            })
              .then(async (response) => {
                const payload = await response.json() as { answer?: string; detail?: string };
                if (!response.ok) throw new Error(payload.detail ?? `Ask returned ${response.status}`);
                setAnswer(payload.answer ?? "");
              })
              .catch((reason: unknown) => {
                setError(reason instanceof Error ? reason.message : "Ask failed");
              })
              .finally(() => setLoading(false));
          }}
        >
          <MessageSquareText size={17} />
          <input
            autoFocus
            aria-label="Question about this experiment"
            placeholder="Compare cost, paths, samples, or configuration"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button className="live-ask-submit" disabled={!question.trim() || loading} type="submit">
            {loading ? "Planning…" : "Ask"}
          </button>
          <button className="live-icon-button" type="button" onClick={onClose}>Close</button>
        </form>
        <div className="live-ask-scope">
          <span>Scope</span><strong>{comparisonId}</strong>
          <small>Definition, cohorts, samples, paths, and replay evidence. Model use is off.</small>
        </div>
        {error ? <p className="live-ask-error" role="alert">{error}</p> : null}
        {answer ? <div className="live-ask-answer"><p>{answer}</p></div> : null}
      </section>
    </div>
  );
}
