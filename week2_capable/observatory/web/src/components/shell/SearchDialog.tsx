import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { AskResponse, QueryScope } from "../../data/ask";
import { SearchAnswer } from "./SearchAnswer";
import { StructuredQueryEditor } from "./StructuredQueryEditor";
import {
  filterFields,
  filterOperators,
  scopeDescription,
  suggestions,
  type QueryOrder,
} from "./queryOptions";

type Props = {
  open: boolean;
  scopeLabel?: string;
  scope: QueryScope;
  modelAvailable?: boolean;
  onClose: () => void;
  onOpenCitation?: (citationId: string) => void;
};

export function SearchDialog({
  open,
  scopeLabel,
  scope,
  modelAvailable = false,
  onClose,
  onOpenCitation,
}: Props) {
  const input = useRef<HTMLInputElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allowModel, setAllowModel] = useState(false);
  const [allowSummary, setAllowSummary] = useState(false);
  const [structured, setStructured] = useState(false);
  const [filterField, setFilterField] = useState(
    () => filterFields(scope.space)[0],
  );
  const [filterOperator, setFilterOperator] = useState("eq");
  const [filterValue, setFilterValue] = useState("");
  const [order, setOrder] = useState<QueryOrder>("causal");
  const scopeReady = scope.space === "live"
    ? Boolean(scope.live_session_id)
    : scope.space === "sessions"
      ? Boolean(scope.run_id)
      : scope.space === "knowledge"
        ? Boolean(scope.player_id)
        : true;
  const filterValid = !(
    structured
    && filterField === "cost_usd"
    && filterValue.trim()
    && !Number.isFinite(Number(filterValue))
  );

  useEffect(() => {
    if (open) {
      previousFocus.current = document.activeElement as HTMLElement | null;
      const saved = new URL(window.location.href).searchParams.get("q");
      if (saved) {
        setQuestion(saved);
      }
      const url = new URL(window.location.href);
      const savedField = url.searchParams.get("queryField");
      if (savedField) {
        setStructured(true);
        setFilterField(savedField);
        setFilterOperator(url.searchParams.get("queryOperator") ?? "eq");
        setFilterValue(url.searchParams.get("queryValue") ?? "");
        const savedOrder = url.searchParams.get("queryOrder");
        if (
          savedOrder === "causal"
          || savedOrder === "chronological"
          || savedOrder === "cost_desc"
        ) {
          setOrder(savedOrder);
        }
      }
      input.current?.focus();
      return;
    }
    previousFocus.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!filterFields(scope.space).includes(filterField)) {
      setFilterField(filterFields(scope.space)[0]);
      setFilterOperator("eq");
      setFilterValue("");
    }
  }, [filterField, scope.space]);

  useEffect(() => {
    const valid = filterOperators(filterField).map((item) => item.value);
    if (!valid.includes(filterOperator)) {
      setFilterOperator("eq");
    }
  }, [filterField, filterOperator]);

  if (!open) {
    return null;
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim() || !scopeReady || !filterValid) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          scope,
          ...(structured
            ? {
              query: {
                version: 1,
                operation: "search_evidence",
                scope,
                filters: filterValue.trim()
                  ? [{
                    field: filterField,
                    operator: filterOperator,
                    value: filterField === "cost_usd"
                      ? Number(filterValue)
                      : filterValue.trim(),
                  }]
                  : [],
                order,
                limit: 25,
              },
            }
            : {}),
          allow_model: allowModel,
          allow_summary: allowSummary,
        }),
      });
      const payload = await response.json() as AskResponse & {
        detail?: string;
      };
      if (!response.ok) {
        throw new Error(payload.detail ?? `Ask returned ${response.status}`);
      }
      setAnswer(payload);
      const url = new URL(window.location.href);
      url.searchParams.set("q", question.trim());
      if (structured) {
        url.searchParams.set("queryField", filterField);
        url.searchParams.set("queryOperator", filterOperator);
        url.searchParams.set("queryValue", filterValue.trim());
        url.searchParams.set("queryOrder", order);
      } else {
        for (const key of [
          "queryField",
          "queryOperator",
          "queryValue",
          "queryOrder",
        ]) {
          url.searchParams.delete(key);
        }
      }
      window.history.replaceState(null, "", url);
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
            disabled={!question.trim() || !scopeReady || !filterValid || loading}
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
            {scopeDescription(scope, scopeReady)}
          </small>
        </div>
        <StructuredQueryEditor
          scope={scope}
          enabled={structured}
          field={filterField}
          operator={filterOperator}
          value={filterValue}
          order={order}
          valid={filterValid}
          onEnabledChange={setStructured}
          onFieldChange={setFilterField}
          onOperatorChange={setFilterOperator}
          onValueChange={setFilterValue}
          onOrderChange={setOrder}
        />
        {modelAvailable ? (
          <div className="search-model-options">
            <label className="search-model-option">
              <input
                checked={allowModel}
                type="checkbox"
                onChange={(event) => setAllowModel(event.target.checked)}
              />
              <span>
                Translate an unmatched question into a validated local query
              </span>
            </label>
            <label className="search-model-option">
              <input
                checked={allowSummary}
                type="checkbox"
                onChange={(event) => setAllowSummary(event.target.checked)}
              />
              <span>
                Summarize returned evidence with cited IDs
              </span>
            </label>
          </div>
        ) : null}
        {answer === null && error === null ? (
          <div className="search-guidance">
            <p className="eyebrow">Deterministic by default</p>
            <h2>Ask with evidence, even without a model</h2>
            <p>
              Questions are planned into typed local operations. Every answer
              shows the plan, citations, missing data, and translation cost.
            </p>
            <div className="suggestion-grid">
              {suggestions(scope.space).map((suggestion) => (
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
          <SearchAnswer
            answer={answer}
            onOpenCitation={onOpenCitation}
          />
        ) : null}
      </section>
    </div>
  );
}
