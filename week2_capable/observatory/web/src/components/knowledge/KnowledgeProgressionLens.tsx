import { Backpack, Gauge, ShieldAlert } from "lucide-react";
import type { KnowledgeAssertion } from "../../data/knowledge";
import { AssertionList } from "./AssertionList";

type Props = {
  assertions: KnowledgeAssertion[];
  onSelect: (id: string) => void;
};

const groups = [
  {
    id: "vitals",
    label: "Vitals and posture",
    icon: Gauge,
    terms: ["hit", "mana", "move", "position", "level", "gold"],
  },
  {
    id: "inventory",
    label: "Inventory and equipment",
    icon: Backpack,
    terms: ["inventory", "equipment", "carrying", "wearing", "item"],
  },
  {
    id: "conditions",
    label: "Conditions",
    icon: ShieldAlert,
    terms: ["condition", "hungry", "thirsty", "affect", "combat"],
  },
] as const;

export function KnowledgeProgressionLens({
  assertions,
  onSelect,
}: Props) {
  const claimed = new Set<string>();
  const sections = groups.map((group) => {
    const matches = assertions.filter((assertion) => {
      const haystack = (
        `${assertion.subject} ${assertion.predicate}`.toLocaleLowerCase()
      );
      const match = group.terms.some((term) => haystack.includes(term));
      if (match) claimed.add(assertion.assertion_id);
      return match;
    });
    return { ...group, assertions: matches };
  });
  const other = assertions.filter((item) => !claimed.has(item.assertion_id));

  return (
    <div className="knowledge-progression-grid">
      {sections.map(({ id, label, icon: Icon, assertions: items }) => (
        <section className="knowledge-panel" key={id}>
          <div className="panel-heading">
            <span>
              <p className="eyebrow">Player state</p>
              <h2>{label}</h2>
            </span>
            <Icon size={17} aria-hidden="true" />
          </div>
          <AssertionList
            assertions={items}
            empty={`No ${label.toLocaleLowerCase()} are retained.`}
            onSelect={onSelect}
          />
        </section>
      ))}
      {other.length > 0 ? (
        <section className="knowledge-panel knowledge-progression-other">
          <div className="panel-heading">
            <span>
              <p className="eyebrow">Schema-aware fallback</p>
              <h2>Other player knowledge</h2>
            </span>
          </div>
          <AssertionList
            assertions={other}
            empty=""
            onSelect={onSelect}
          />
        </section>
      ) : null}
    </div>
  );
}
