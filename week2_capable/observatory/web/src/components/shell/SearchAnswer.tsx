import type { AskResponse } from "../../data/ask";

type Props = {
  answer: AskResponse;
  onOpenCitation?: (citationId: string) => void;
};

export function SearchAnswer({ answer, onOpenCitation }: Props) {
  return (
    <div className="search-answer" aria-live="polite">
      <div className="answer-heading">
        <span>{answer.tier.replaceAll("_", " ")}</span>
        <b>
          ${answer.model_cost_usd.toFixed(4)} model spend
          {answer.model_input_tokens + answer.model_output_tokens > 0
            ? ` · ${answer.model_input_tokens + answer.model_output_tokens} tokens`
            : ""}
        </b>
      </div>
      <h2>{answer.answer}</h2>
      {answer.model_summary ? (
        <article className="answer-summary">
          <span>AI-generated summary</span>
          <p>{answer.model_summary}</p>
          <div>
            {answer.model_summary_citations.map((citation) => (
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
      ) : null}
      {answer.query ? (
        <div className="answer-query">
          <span>Validated query</span>
          <b>{answer.query.operation.replaceAll("_", " ")}</b>
          <small>
            {answer.query.scope.space} · {answer.query.order} · limit{" "}
            {answer.query.limit}
          </small>
        </div>
      ) : null}
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
      {answer.citations.length > 0 ? (
        <section>
          <p className="eyebrow">Exact evidence</p>
          {answer.citations.map((citation) => (
            <article key={citation.id}>
              <button
                type="button"
                onClick={() => onOpenCitation?.(citation.id)}
              >
                {citation.label}
              </button>
              <span>{citation.excerpt}</span>
              <small>{citation.source} · {citation.id}</small>
            </article>
          ))}
        </section>
      ) : null}
      {(answer.hypotheses ?? []).length > 0 ? (
        <section className="answer-hypotheses">
          <p className="eyebrow">Unsupported hypotheses</p>
          <ul>
            {answer.hypotheses.map((hypothesis) => (
              <li key={hypothesis}>{hypothesis}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {answer.missing.length > 0 ? (
        <div className="answer-missing">
          Capture gaps: {answer.missing.join(", ")}
        </div>
      ) : null}
    </div>
  );
}
