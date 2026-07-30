import {
  GitCompareArrows,
  History,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type {
  KnowledgeAssertion,
  PlayerKnowledge,
} from "../../data/knowledge";
import { StateBadge } from "../system/StateBadge";
import { AssertionList } from "./AssertionList";
import { KnowledgeEntitiesLens } from "./KnowledgeEntitiesLens";
import { KnowledgeMapLens } from "./KnowledgeMapLens";
import { KnowledgeProgressionLens } from "./KnowledgeProgressionLens";
import {
  formatKnowledgeTime,
  type KnowledgeLensId,
} from "./knowledgeModel";

type Props = {
  lens: KnowledgeLensId;
  knowledge: PlayerKnowledge;
  assertions: KnowledgeAssertion[];
  canRecover: boolean;
  onSelect: (id: string) => void;
  onRestore: (snapshotId: string, digest: string) => void;
};

export function KnowledgeLens({
  lens,
  knowledge,
  assertions,
  canRecover,
  onSelect,
  onRestore,
}: Props) {
  if (lens === "overview") {
    return (
      <div className="knowledge-overview">
        <section className="knowledge-metrics">
          {knowledge.metrics.map((metric) => (
            <article key={metric.id} title={metric.detail}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.detail}</small>
            </article>
          ))}
        </section>
        <section className="knowledge-panel">
          <div className="panel-heading">
            <span>
              <p className="eyebrow">Attention frontier</p>
              <h2>Unresolved knowledge</h2>
            </span>
            <GitCompareArrows size={17} aria-hidden="true" />
          </div>
          <AssertionList
            assertions={assertions.filter(
              (item) => item.conflict_group || item.confidence === "ambiguous",
            )}
            empty="No unresolved assertions match this view."
            onSelect={onSelect}
          />
        </section>
        <section className="knowledge-panel">
          <div className="panel-heading">
            <span>
              <p className="eyebrow">Recent knowledge</p>
              <h2>Current facts</h2>
            </span>
            <Sparkles size={17} aria-hidden="true" />
          </div>
          <AssertionList
            assertions={assertions.filter((item) => item.current).slice(0, 12)}
            empty="No current facts match this view."
            onSelect={onSelect}
          />
        </section>
      </div>
    );
  }
  if (lens === "snapshots") {
    return (
      <section className="knowledge-panel">
        <div className="panel-heading">
          <span>
            <p className="eyebrow">Recoverable state</p>
            <h2>Verified snapshots</h2>
          </span>
          <ShieldCheck size={17} aria-hidden="true" />
        </div>
        <div className="snapshot-list">
          {knowledge.snapshots.map((snapshot) => (
            <article key={snapshot.snapshot_id}>
              <StateBadge state={snapshot.verified ? "actual" : "attention"}>
                {snapshot.verified ? "verified" : "failed"}
              </StateBadge>
              <div>
                <strong>Generation {snapshot.generation}</strong>
                <span>{snapshot.reason}</span>
                <small>
                  change {snapshot.cdc_high_water} · {snapshot.digest.slice(0, 12)}…
                </small>
              </div>
              <button
                className="text-button"
                type="button"
                disabled={!snapshot.verified || !canRecover}
                title={
                  canRecover
                    ? "Restore through the selected authenticated live session"
                    : "A live authenticated session for this player is required"
                }
                onClick={() => onRestore(snapshot.snapshot_id, snapshot.digest)}
              >
                Restore
              </button>
            </article>
          ))}
          {knowledge.recoveries.map((item) => (
            <article key={item.operation_id}>
              <StateBadge state="inferred">{item.operation}</StateBadge>
              <div>
                <strong>{item.assertions} assertions</strong>
                <span>{item.reason}</span>
                <small>snapshot {item.snapshot_id.slice(0, 12)}…</small>
              </div>
            </article>
          ))}
          {knowledge.snapshots.length + knowledge.recoveries.length === 0 ? (
            <p className="knowledge-empty">No recovery history is retained.</p>
          ) : null}
        </div>
      </section>
    );
  }
  if (lens === "history") {
    return (
      <section className="knowledge-panel">
        <div className="panel-heading">
          <span>
            <p className="eyebrow">Append-only CDC</p>
            <h2>Knowledge history</h2>
          </span>
          <History size={17} aria-hidden="true" />
        </div>
        <div className="knowledge-history">
          {knowledge.changes.slice().reverse().map((change) => (
            <article key={change.change_seq}>
              <b>{change.change_seq}</b>
              <span>
                <strong>{change.operation}</strong>
                <small>{change.entity_type} · {change.entity_id}</small>
              </span>
              <time>{formatKnowledgeTime(change.at)}</time>
            </article>
          ))}
        </div>
      </section>
    );
  }
  if (lens === "map") {
    return (
      <KnowledgeMapLens
        assertions={assertions.filter(isMapAssertion)}
        onSelect={onSelect}
      />
    );
  }
  if (lens === "entities") {
    return (
      <KnowledgeEntitiesLens
        assertions={assertions.filter(isEntityAssertion)}
        onSelect={onSelect}
      />
    );
  }
  return (
    <KnowledgeProgressionLens
      assertions={assertions.filter(
        (item) => !isMapAssertion(item) && !isEntityAssertion(item),
      )}
      onSelect={onSelect}
    />
  );
}

function isMapAssertion(assertion: KnowledgeAssertion): boolean {
  return assertion.subject.startsWith("room:")
    || assertion.subject.startsWith("place:")
    || assertion.predicate.startsWith("exit.")
    || assertion.predicate.includes("zone");
}

function isEntityAssertion(assertion: KnowledgeAssertion): boolean {
  return ["entity:", "mob:", "object:", "npc:"].some(
    (prefix) => assertion.subject.startsWith(prefix),
  ) || assertion.predicate.includes("sighting");
}
