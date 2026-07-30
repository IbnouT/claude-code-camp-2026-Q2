import { ArrowRight } from "lucide-react";
import type { KnowledgeAssertion } from "../../data/knowledge";
import { StateBadge } from "../system/StateBadge";
import {
  humanizeKnowledge,
  renderKnowledgeValue,
} from "./knowledgeModel";

type Props = {
  assertions: KnowledgeAssertion[];
  empty: string;
  onSelect: (id: string) => void;
};

export function AssertionList({ assertions, empty, onSelect }: Props) {
  if (assertions.length === 0) {
    return <p className="knowledge-empty">{empty}</p>;
  }
  return (
    <div className="assertion-list">
      {assertions.map((item) => (
        <button
          key={item.assertion_id}
          type="button"
          onClick={() => onSelect(item.assertion_id)}
        >
          <span>
            <strong>{humanizeKnowledge(item.subject)}</strong>
            <small>{humanizeKnowledge(item.predicate)}</small>
          </span>
          <b>{renderKnowledgeValue(item.value)}</b>
          <span className="assertion-meta">
            <StateBadge state={
              item.layer === "observer_truth"
                ? "actual"
                : item.conflict_group
                  ? "attention"
                  : "inferred"
            }>
              {item.conflict_group ? "conflict" : item.confidence}
            </StateBadge>
            <ArrowRight size={13} aria-hidden="true" />
          </span>
        </button>
      ))}
    </div>
  );
}
