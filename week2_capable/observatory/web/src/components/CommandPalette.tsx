import {
  ArrowRight,
  CheckCircle2,
  Database,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { useState } from "react";
import type { AskResponse } from "../data/ask";
import type { EvidenceCitation } from "../data/investigation";

type Props = {
  open: boolean;
  onClose: () => void;
  runId: string | null;
  comparisonId: string | null;
  onOpenCitation: (citation: EvidenceCitation) => void;
};

const suggestions = [
  "Why did the agent stop?",
  "Which position candidates remain ambiguous?",
  "Compare raw, minimal, and full rendering.",
];

export function CommandPalette({
  open,
  onClose,
  runId,
  comparisonId,
  onOpenCitation,
}: Props) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allowModel, setAllowModel] = useState(false);

  if (!open) {
    return null;
  }

  const ask = (value: string) => {
    const next = value.trim();
    if (next.length < 3) return;
    setQuestion(next);
    setLoading(true);
    setError(null);
    void fetch("/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        question: next,
        run_id: runId,
        comparison_id: comparisonId,
        allow_model: allowModel,
      }),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("The evidence query could not run.");
        return response.json() as Promise<AskResponse>;
      })
      .then(setResult)
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Query failed.");
      })
      .finally(() => setLoading(false));
  };

  return (
    <div className="palette-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Ask or search evidence"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <form
          className="palette-input"
          onSubmit={(event) => {
            event.preventDefault();
            ask(question);
          }}
        >
          <Search size={18} aria-hidden="true" />
          <input
            autoFocus
            type="search"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask why it stopped, or compare rendering policies"
          />
          <button type="submit" aria-label="Run evidence query" disabled={loading}>
            {loading ? "…" : <ArrowRight size={14} aria-hidden="true" />}
          </button>
        </form>
        <label className="model-permission">
          <input
            type="checkbox"
            checked={allowModel}
            onChange={(event) => setAllowModel(event.target.checked)}
          />
          <span>
            Allow budgeted model translation only when local planning cannot
            match the question
          </span>
        </label>
        {result ? (
          <div className="ask-result">
            <header>
              <span>
                <CheckCircle2 size={13} aria-hidden="true" />
                {result.tier === "deterministic" ? "Local answer" : result.tier}
              </span>
              <small>${result.model_cost_usd.toFixed(4)} model spend</small>
            </header>
            <h3>{result.answer}</h3>
            <div className="query-plan">
              <p className="eyebrow">Visible query plan</p>
              {result.plan.map((step) => (
                <article key={`${step.source}:${step.operation}`}>
                  <Database size={12} aria-hidden="true" />
                  <div>
                    <strong>{step.operation.replaceAll("_", " ")}</strong>
                    <span>{step.detail}</span>
                  </div>
                </article>
              ))}
            </div>
            <div className="answer-claims">
              {result.claims.map((claim) => (
                <article key={claim.text}>
                  <span className={`claim-confidence is-${claim.confidence}`}>
                    {claim.confidence}
                  </span>
                  <p>{claim.text}</p>
                </article>
              ))}
            </div>
            <div className="answer-citations">
              {result.citations.map((citation) => (
                <button
                  key={citation.id}
                  type="button"
                  onClick={() => onOpenCitation(citation)}
                >
                  <span>{citation.label}</span>
                  <small>{citation.excerpt}</small>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="palette-content">
            <p className="eyebrow">Suggested investigations</p>
            {suggestions.map((suggestion, index) => (
              <button key={suggestion} type="button" onClick={() => ask(suggestion)}>
                {index === 0
                  ? <Sparkles size={15} aria-hidden="true" />
                  : <Search size={15} aria-hidden="true" />}
                {suggestion}
              </button>
            ))}
          </div>
        )}
        {error && <p className="palette-error">{error}</p>}
        <button className="palette-close" type="button" onClick={onClose} aria-label="Close">
          <X size={17} aria-hidden="true" />
        </button>
      </section>
    </div>
  );
}
