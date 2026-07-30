import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { AskResponse } from "../../data/ask";

type Props = {
  open: boolean;
  scopeLabel?: string;
  runId?: string;
  onClose: () => void;
  onOpenCitation?: (citationId: string) => void;
};

export function SearchDialog({
  open,
  scopeLabel,
  runId,
  onClose,
  onOpenCitation,
}: Props) {
  const input = useRef<HTMLInputElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      previousFocus.current = document.activeElement as HTMLElement | null;
      input.current?.focus();
      return;
    }
    previousFocus.current?.focus();
  }, [open]);

  if (!open) {
    return null;
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim() || !runId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          run_id: runId,
          selected_record_id: new URL(window.location.href).searchParams.get(
            "record",
          ),
          allow_model: false,
        }),
      });
      const payload = await response.json() as AskResponse & {
        detail?: string;
      };
      if (!response.ok) {
        throw new Error(payload.detail ?? `Ask returned ${response.status}`);
      }
      setAnswer(payload);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ask failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        aria-label="Ask or search evidence"
        aria-modal="true"
        className="search-dialog"
        role="dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <form className="search-query" onSubmit={submit}>
          <Search size={18} aria-hidden="true" />
          <input
            aria-label="Question or evidence query"
            value={question}
            placeholder="Ask why, find a trace, or search exact evidence"
            ref={input}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button
            className="primary-button"
            disabled={!question.trim() || !runId || loading}
            type="submit"
          >
            {loading ? "Planning…" : "Ask"}
          </button>
          <button
            aria-label="Close search"
            className="icon-button"
            type="button"
            onClick={onClose}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </form>
        <div className="search-scope">
          <span>Scope</span>
          <b>{scopeLabel ?? "Current Observatory space"}</b>
          <small>
            {runId
              ? "The answer is limited to this recorded run and the selected replay moment."
              : "Select a recorded session before asking an evidence question."}
          </small>
        </div>
        {answer === null && error === null ? (
          <div className="search-guidance">
            <p className="eyebrow">Deterministic by default</p>
            <h2>Ask with evidence, even without a model</h2>
            <p>
              Questions are planned into typed local operations. Every answer
              shows the plan, citations, missing data, and translation cost.
            </p>
            <div className="suggestion-grid">
              {[
                "Why did the agent stop?",
                "Which position candidates remain?",
                "Which evidence disagrees?",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => setQuestion(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {error ? <p className="search-error" role="alert">{error}</p> : null}
        {answer ? (
          <div className="search-answer" aria-live="polite">
            <div className="answer-heading">
              <span>
                {answer.tier.replaceAll("_", " ")}
              </span>
              <b>${answer.model_cost_usd.toFixed(4)} model spend</b>
            </div>
            <h2>{answer.answer}</h2>
            <section>
              <p className="eyebrow">Visible query plan</p>
              {answer.plan.length > 0 ? answer.plan.map((step) => (
                <article key={`${step.operation}:${step.source}`}>
                  <b>{step.operation.replaceAll("_", " ")}</b>
                  <span>{step.detail}</span>
                  <small>{step.source}</small>
                </article>
              )) : <p>No validated local operation matched this question.</p>}
            </section>
            {answer.claims.map((claim) => (
              <article className="answer-claim" key={claim.text}>
                <span>{claim.confidence}</span>
                <p>{claim.text}</p>
                <div>
                  {claim.citations.map((citation) => (
                    <button
                      key={citation}
                      type="button"
                      onClick={() => onOpenCitation?.(citation)}
                    >
                      {citation}
                    </button>
                  ))}
                </div>
              </article>
            ))}
            {answer.missing.length > 0 ? (
              <div className="answer-missing">
                Missing: {answer.missing.join(", ")}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
    </div>
  );
}
