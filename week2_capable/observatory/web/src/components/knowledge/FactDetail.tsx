import type { KnowledgeAssertion } from "../../data/knowledge";
import {
  humanizeKnowledge,
  renderKnowledgeValue,
} from "./knowledgeModel";

type Props = {
  assertion: KnowledgeAssertion;
  history: KnowledgeAssertion[];
  onClose: () => void;
  onOpenEvidence: (sessionId: string, sequence: number) => void;
};

export function FactDetail({
  assertion,
  history,
  onClose,
  onOpenEvidence,
}: Props) {
  return (
    <aside className="knowledge-detail" aria-label="Knowledge fact detail">
      <div className="panel-heading">
        <span>
          <p className="eyebrow">{assertion.layer} · {assertion.status}</p>
          <h2>{humanizeKnowledge(assertion.subject)}</h2>
        </span>
        <button className="text-button" type="button" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="fact-value">
        <span>{humanizeKnowledge(assertion.predicate)}</span>
        <strong>{renderKnowledgeValue(assertion.value)}</strong>
      </div>
      <dl>
        <div><dt>Confidence</dt><dd>{assertion.confidence}</dd></div>
        <div><dt>Fact ID</dt><dd>{assertion.fact_id}</dd></div>
        <div><dt>Assertion</dt><dd>{assertion.assertion_id}</dd></div>
        <div>
          <dt>Conflict</dt>
          <dd>{assertion.conflict_group ?? "none"}</dd>
        </div>
      </dl>
      <section>
        <p className="eyebrow">Supporting observations</p>
        {assertion.evidence.map((item) => (
          <button
            key={`${item.session_id}:${item.source_seq}:${item.wire_digest}`}
            type="button"
            onClick={() => onOpenEvidence(item.session_id, item.source_seq)}
          >
            <span>
              <strong>{item.session_id} · seq {item.source_seq}</strong>
              <small>{item.method} · {item.parser_version}</small>
            </span>
            <code>{item.wire_digest}</code>
          </button>
        ))}
      </section>
      <section>
        <p className="eyebrow">Assertion history</p>
        {history.map((item) => (
          <article key={item.assertion_id}>
            <strong>{renderKnowledgeValue(item.value)}</strong>
            <span>{item.status} · {item.confidence}</span>
          </article>
        ))}
      </section>
    </aside>
  );
}
