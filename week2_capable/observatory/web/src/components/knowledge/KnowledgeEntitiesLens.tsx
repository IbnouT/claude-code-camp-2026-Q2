import { ChevronLeft, ChevronRight, Footprints, Layers3 } from "lucide-react";
import { useMemo, useState } from "react";
import type { KnowledgeAssertion } from "../../data/knowledge";
import { StateBadge } from "../system/StateBadge";
import {
  humanizeKnowledge,
  renderKnowledgeValue,
} from "./knowledgeModel";

type Props = {
  assertions: KnowledgeAssertion[];
  onSelect: (id: string) => void;
};

const pageSize = 18;

export function KnowledgeEntitiesLens({ assertions, onSelect }: Props) {
  const entities = useMemo(() => groupEntities(assertions), [assertions]);
  const [type, setType] = useState("all");
  const [page, setPage] = useState(0);
  const types = [...new Set(entities.map((item) => item.type))];
  const filtered = type === "all"
    ? entities
    : entities.filter((item) => item.type === type);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const activePage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(
    activePage * pageSize,
    (activePage + 1) * pageSize,
  );

  return (
    <section className="knowledge-panel knowledge-entities-lens">
      <div className="panel-heading">
        <span>
          <p className="eyebrow">Distinct identities · cumulative sightings</p>
          <h2>Known entities</h2>
        </span>
        <span className="knowledge-count">{filtered.length} entities</span>
      </div>
      <div className="entity-type-filter" aria-label="Entity type filter">
        {["all", ...types].map((item) => (
          <button
            aria-pressed={type === item}
            key={item}
            type="button"
            onClick={() => {
              setType(item);
              setPage(0);
            }}
          >
            {item}
          </button>
        ))}
      </div>
      <div className="entity-table" role="table" aria-label="Known entities">
        {visible.map((entity) => (
          <button
            key={entity.id}
            role="row"
            type="button"
            onClick={() => onSelect(entity.primary.assertion_id)}
          >
            <span role="cell">
              <strong>{entity.name}</strong>
              <small>{entity.id}</small>
            </span>
            <span role="cell">{entity.type}</span>
            <span role="cell">
              <Footprints size={13} aria-hidden="true" />
              {entity.sightings} sightings
            </span>
            <span role="cell">
              <Layers3 size={13} aria-hidden="true" />
              {entity.assertions.length} facts
            </span>
            <StateBadge state={entity.mobile ? "attention" : "inferred"}>
              {entity.mobile ? "mobile / respawning" : entity.primary.confidence}
            </StateBadge>
          </button>
        ))}
      </div>
      <footer className="knowledge-pagination">
        <button
          aria-label="Previous entity page"
          disabled={activePage === 0}
          type="button"
          onClick={() => setPage((value) => Math.max(0, value - 1))}
        >
          <ChevronLeft size={14} aria-hidden="true" />
        </button>
        <span>Page {activePage + 1} of {pageCount}</span>
        <button
          aria-label="Next entity page"
          disabled={activePage + 1 >= pageCount}
          type="button"
          onClick={() => setPage((value) => value + 1)}
        >
          <ChevronRight size={14} aria-hidden="true" />
        </button>
      </footer>
      {entities.length === 0 ? (
        <p className="knowledge-empty">No entity assertions match this layer.</p>
      ) : null}
    </section>
  );
}

function groupEntities(assertions: KnowledgeAssertion[]) {
  const grouped = new Map<string, KnowledgeAssertion[]>();
  for (const assertion of assertions) {
    grouped.set(
      assertion.subject,
      [...(grouped.get(assertion.subject) ?? []), assertion],
    );
  }
  return [...grouped.entries()].map(([id, items]) => {
    const primary = items[0] as KnowledgeAssertion;
    const nameAssertion = items.find((item) => (
      item.predicate.includes("name") || item.predicate.includes("title")
    ));
    const type = id.split(":")[0] || "entity";
    return {
      id,
      name: nameAssertion
        ? renderKnowledgeValue(nameAssertion.value)
        : humanizeKnowledge(id),
      type,
      assertions: items,
      primary,
      sightings: new Set(
        items.flatMap((item) => item.evidence.map(
          (evidence) => `${evidence.session_id}:${evidence.source_seq}`,
        )),
      ).size,
      mobile: items.some((item) => (
        item.predicate.includes("sighting")
        || item.predicate.includes("mobile")
        || item.predicate.includes("respawn")
      )),
    };
  });
}
