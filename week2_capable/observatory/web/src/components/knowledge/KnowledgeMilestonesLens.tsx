import { Milestone } from "lucide-react";
import type { KnowledgeAssertion } from "../../data/knowledge";
import { AssertionList } from "./AssertionList";

type Props = {
  assertions: KnowledgeAssertion[];
  onSelect: (id: string) => void;
};

export function KnowledgeMilestonesLens({
  assertions,
  onSelect,
}: Props) {
  return (
    <section className="knowledge-panel knowledge-milestones">
      <div className="panel-heading">
        <span>
          <p className="eyebrow">Retained progress evidence</p>
          <h2>Milestones and objectives</h2>
        </span>
        <Milestone size={17} aria-hidden="true" />
      </div>
      <AssertionList
        assertions={assertions}
        empty="No milestones or objective progress are retained."
        onSelect={onSelect}
      />
    </section>
  );
}
