import { Map as MapIcon, Network, ZoomIn } from "lucide-react";
import { useMemo, useState } from "react";
import type { KnowledgeAssertion } from "../../data/knowledge";
import { StateBadge } from "../system/StateBadge";
import { renderKnowledgeValue } from "./knowledgeModel";

type Props = {
  assertions: KnowledgeAssertion[];
  onSelect: (id: string) => void;
};

type Place = {
  id: string;
  title: string;
  zone: string;
  assertions: KnowledgeAssertion[];
  exits: number;
  uncertain: boolean;
};

export function KnowledgeMapLens({ assertions, onSelect }: Props) {
  const places = useMemo(() => projectPlaces(assertions), [assertions]);
  const [detail, setDetail] = useState<"auto" | "zones" | "rooms">("auto");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = places.find((place) => place.id === selectedId) ?? null;
  const zones = groupZones(places);
  const effective = detail === "auto"
    ? places.length > 48 ? "zones" : "rooms"
    : detail;
  const visiblePlaces = places.slice(0, 120);

  return (
    <section className="knowledge-panel knowledge-map-lens">
      <div className="panel-heading">
        <span>
          <p className="eyebrow">Semantic zoom · retained assertions only</p>
          <h2>Learned world</h2>
        </span>
        <div className="segmented-control" aria-label="Map level of detail">
          {(["auto", "zones", "rooms"] as const).map((level) => (
            <button
              aria-pressed={detail === level}
              key={level}
              type="button"
              onClick={() => setDetail(level)}
            >
              {level}
            </button>
          ))}
        </div>
      </div>
      <div className="knowledge-map-summary">
        <span><MapIcon size={14} aria-hidden="true" /> {places.length} places</span>
        <span><Network size={14} aria-hidden="true" /> {zones.length} zones</span>
        <span>
          <ZoomIn size={14} aria-hidden="true" />
          {effective === "zones" ? "Aggregated by zone" : "Room detail"}
        </span>
      </div>
      {effective === "zones" ? (
        <div className="knowledge-zone-grid">
          {zones.map((zone) => (
            <button
              key={zone.name}
              type="button"
              onClick={() => {
                setDetail("rooms");
                setSelectedId(zone.places[0]?.id ?? null);
              }}
            >
              <strong>{zone.name}</strong>
              <span>{zone.places.length} places</span>
              <small>
                {zone.places.reduce((sum, place) => sum + place.exits, 0)} exits
                · {zone.places.filter((place) => place.uncertain).length} unresolved
              </small>
            </button>
          ))}
        </div>
      ) : (
        <div className={`knowledge-room-browser${selected ? " has-selection" : ""}`}>
          <div className="knowledge-room-grid" aria-label="Learned rooms">
            {visiblePlaces.map((place) => (
              <button
                aria-pressed={selectedId === place.id}
                key={place.id}
                type="button"
                onClick={() => setSelectedId(place.id)}
              >
                <span className="room-node-dot" aria-hidden="true" />
                <strong>{place.title}</strong>
                <small>{place.zone} · {place.exits} exits</small>
                {place.uncertain ? (
                  <StateBadge state="attention">unresolved</StateBadge>
                ) : null}
              </button>
            ))}
          </div>
          {selected ? (
            <aside className="knowledge-map-detail">
              <p className="eyebrow">{selected.zone}</p>
              <h3>{selected.title}</h3>
              <code>{selected.id}</code>
              <div>
                {selected.assertions.map((assertion) => (
                  <button
                    key={assertion.assertion_id}
                    type="button"
                    onClick={() => onSelect(assertion.assertion_id)}
                  >
                    <span>{assertion.predicate}</span>
                    <strong>{renderKnowledgeValue(assertion.value)}</strong>
                  </button>
                ))}
              </div>
            </aside>
          ) : null}
        </div>
      )}
      {places.length > visiblePlaces.length && effective === "rooms" ? (
        <p className="knowledge-gap">
          Room rendering is capped at 120 nodes. Use zone aggregation or search
          to narrow this view.
        </p>
      ) : null}
      {places.length === 0 ? (
        <p className="knowledge-empty">No learned place assertions match this layer.</p>
      ) : null}
    </section>
  );
}

function projectPlaces(assertions: KnowledgeAssertion[]): Place[] {
  const grouped = new Map<string, KnowledgeAssertion[]>();
  for (const assertion of assertions) {
    const current = grouped.get(assertion.subject) ?? [];
    current.push(assertion);
    grouped.set(assertion.subject, current);
  }
  return [...grouped.entries()].map(([id, items]) => {
    const title = valueFor(items, ["title", "name"]) ?? id;
    const zone = valueFor(items, ["zone", "area", "region"]) ?? "Unassigned";
    return {
      id,
      title,
      zone,
      assertions: items,
      exits: items.filter((item) => item.predicate.startsWith("exit.")).length,
      uncertain: items.some(
        (item) => Boolean(item.conflict_group) || item.confidence === "ambiguous",
      ),
    };
  });
}

function valueFor(
  assertions: KnowledgeAssertion[],
  predicates: string[],
): string | null {
  const match = assertions.find((item) => (
    predicates.some((predicate) => item.predicate.includes(predicate))
  ));
  return match ? renderKnowledgeValue(match.value) : null;
}

function groupZones(places: Place[]) {
  const grouped = new Map<string, Place[]>();
  for (const place of places) {
    grouped.set(place.zone, [...(grouped.get(place.zone) ?? []), place]);
  }
  return [...grouped.entries()]
    .map(([name, entries]) => ({ name, places: entries }))
    .sort((left, right) => right.places.length - left.places.length);
}
