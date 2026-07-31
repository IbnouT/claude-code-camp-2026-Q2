import {
  BookOpen,
  Boxes,
  Clock3,
  History,
  Map,
  Search,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import "../../styles/knowledge.css";
import "../../styles/knowledge-mock.css";
import {
  recoverKnowledge,
  type KnowledgeRecoveryAction,
} from "../../data/recoverKnowledge";
import { usePlayerKnowledge } from "../../data/usePlayerKnowledge";
import { StateBadge } from "../system/StateBadge";
import { FactDetail } from "./FactDetail";
import { KnowledgeLens } from "./KnowledgeLens";
import { KnowledgeRecoveryDialog } from "./KnowledgeRecoveryDialog";
import {
  type KnowledgeLayer,
  type KnowledgeLensId,
  visibleAssertions,
} from "./knowledgeModel";

type Props = {
  playerId: string;
  recoverySession: {
    id: string;
    latestSequence: number;
    available: boolean;
  } | null;
  onOpenEvidence: (sessionId: string, sequence: number) => boolean;
  onOpenSearch: () => void;
};

/** Primary lenses follow knowledge.html: the learned map opens first as the
 * coordinated screen; entities and progression are its peers. Overview,
 * snapshots, and history remain reachable as secondary views (capability
 * floor), placed after the primaries rather than as equal tabs. */
const primaryLenses: Array<{
  id: KnowledgeLensId;
  label: string;
  icon: typeof Map;
}> = [
  { id: "map", label: "Learned map", icon: Map },
  { id: "entities", label: "Entities", icon: Boxes },
  { id: "progression", label: "Progression", icon: UserRound },
  { id: "milestones", label: "Milestones", icon: Sparkles },
];

const secondaryLenses: Array<{
  id: KnowledgeLensId;
  label: string;
  icon: typeof Map;
}> = [
  { id: "overview", label: "Overview", icon: BookOpen },
  { id: "snapshots", label: "Snapshots", icon: ShieldCheck },
  { id: "history", label: "History", icon: History },
];

const allLensIds: KnowledgeLensId[] = [
  ...primaryLenses.map((item) => item.id),
  ...secondaryLenses.map((item) => item.id),
];

export function KnowledgeWorkspace({
  playerId,
  recoverySession,
  onOpenEvidence,
  onOpenSearch,
}: Props) {
  const [revision, setRevision] = useState(0);
  const { knowledge, loading, error } = usePlayerKnowledge(playerId, revision);
  const [lens, setLens] = useState<KnowledgeLensId>(() => lensFromUrl());
  const [layer, setLayer] = useState<KnowledgeLayer>("learned");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(
    () => assertionFromUrl(),
  );
  const [recovery, setRecovery] = useState<KnowledgeRecoveryAction | null>(null);
  const [snapshotDigest, setSnapshotDigest] = useState<string | null>(null);
  const [evidenceGap, setEvidenceGap] = useState<string | null>(null);
  const assertions = useMemo(
    () => visibleAssertions(knowledge, layer, query),
    [knowledge, layer, query],
  );
  const selected = knowledge.assertions.find(
    (item) => item.assertion_id === selectedId,
  ) ?? null;
  const setActiveLens = (next: KnowledgeLensId) => {
    setLens(next);
    const url = new URL(window.location.href);
    url.searchParams.set("knowledgeLens", next);
    window.history.replaceState(null, "", url);
  };
  const setSelectedAssertion = (assertionId: string | null) => {
    setSelectedId(assertionId);
    const url = new URL(window.location.href);
    if (assertionId) {
      url.searchParams.set("subject", `knowledge:${assertionId}`);
    } else {
      url.searchParams.delete("subject");
    }
    window.history.replaceState(null, "", url);
  };

  useEffect(() => {
    const restore = () => setSelectedId(assertionFromUrl());
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  if (loading && knowledge.player_id !== playerId) {
    return <div className="workspace-empty">Loading player knowledge…</div>;
  }

  return (
    <div
      aria-label="Player knowledge"
      className="knowledge-workspace"
      role="region"
    >
      {/* ---- lens subbar (mock: tabs left, quarantine note right) ---- */}
      <nav aria-label="Knowledge views" className="knowledge-lenses">
        {primaryLenses.map(({ id, label, icon: Icon }) => (
          <button
            aria-current={lens === id ? "page" : undefined}
            key={id}
            type="button"
            onClick={() => setActiveLens(id)}
          >
            <Icon size={14} aria-hidden="true" />
            {label}
          </button>
        ))}
        <span aria-hidden="true" className="lens-divider" />
        {secondaryLenses.map(({ id, label, icon: Icon }) => (
          <button
            aria-current={lens === id ? "page" : undefined}
            className="lens-secondary"
            key={id}
            type="button"
            onClick={() => setActiveLens(id)}
          >
            <Icon size={13} aria-hidden="true" />
            {label}
          </button>
        ))}
        <div className="truth-quarantine">
          <ShieldCheck size={15} aria-hidden="true" />
          <span>
            Ground truth is shown for comparison only: never fed back to the
            agent
          </span>
        </div>
      </nav>

      {/* ---- toolbar: layer, filter, cumulative state + recovery ---- */}
      <div className="knowledge-toolbar">
        <div aria-label="Knowledge layer" className="segmented-control">
          {([
            ["learned", "Learned"],
            ["observer_truth", "Truth"],
            ["diff", "Diff"],
          ] as const).map(([id, label]) => (
            <button
              aria-pressed={layer === id}
              key={id}
              type="button"
              onClick={() => setLayer(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="knowledge-search">
          <Search size={14} aria-hidden="true" />
          <span className="sr-only">Filter knowledge</span>
          <input
            placeholder="Filter subjects, facts, or values"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="knowledge-cumulative">
          <StateBadge
            state={knowledge.state === "ready" ? "actual" : "incomplete"}
          >
            {knowledge.state}
          </StateBadge>
          <span className="knowledge-cursor">
            <Clock3 aria-hidden="true" size={13} />
            change {knowledge.cdc_cursor}
          </span>
          <button
            className="secondary-button"
            type="button"
            onClick={onOpenSearch}
          >
            <Search aria-hidden="true" size={14} />
            Search knowledge
          </button>
          <button
            className="secondary-button warn"
            disabled={!recoverySession?.available}
            title={
              recoverySession?.available
                ? "Create a verified snapshot before resetting learned state"
                : "A live authenticated session is required"
            }
            type="button"
            onClick={() => {
              if (!recoverySession) return;
              setSnapshotDigest(null);
              setRecovery({
                action: "reset",
                sessionId: recoverySession.id,
                expectedSequence: recoverySession.latestSequence,
                reason: "operator-requested knowledge reset",
                snapshotId: null,
              });
            }}
          >
            Snapshot &amp; reset
          </button>
        </div>
      </div>

      {error ? (
        <div className="workspace-empty" role="alert">{error}</div>
      ) : null}
      {knowledge.capture_gaps.length > 0 ? (
        <aside className="knowledge-gap">
          <strong>Knowledge coverage is incomplete</strong>
          <span>{knowledge.capture_gaps.join(" · ")}</span>
        </aside>
      ) : null}
      {evidenceGap ? (
        <aside className="knowledge-gap" role="status">
          <strong>Recorded evidence link unavailable</strong>
          <span>{evidenceGap}</span>
        </aside>
      ) : null}

      <div className={`knowledge-layout${selected ? " has-detail" : ""}`}>
        <main>
          <KnowledgeLens
            assertions={assertions}
            canRecover={Boolean(recoverySession?.available)}
            knowledge={knowledge}
            lens={lens}
            onRestore={(snapshotId, digest) => {
              if (!recoverySession) return;
              setSnapshotDigest(digest);
              setRecovery({
                action: "restore",
                sessionId: recoverySession.id,
                expectedSequence: recoverySession.latestSequence,
                reason: "operator-requested snapshot restore",
                snapshotId,
              });
            }}
            onSelect={setSelectedAssertion}
          />
        </main>
        {selected ? (
          <FactDetail
            assertion={selected}
            history={knowledge.assertions.filter(
              (item) => item.fact_id === selected.fact_id,
            )}
            onClose={() => setSelectedAssertion(null)}
            onOpenEvidence={(sessionId, sequence) => {
              if (onOpenEvidence(sessionId, sequence)) {
                setEvidenceGap(null);
              } else {
                setEvidenceGap(
                  `Gateway session ${sessionId} is retained in knowledge, `
                  + "but no recorded run carries that correlation.",
                );
              }
            }}
          />
        ) : null}
      </div>
      <KnowledgeRecoveryDialog
        action={recovery}
        snapshotDigest={snapshotDigest}
        onCancel={() => setRecovery(null)}
        onConfirm={async (request) => {
          await recoverKnowledge(playerId, request);
          setRecovery(null);
          setRevision((value) => value + 1);
        }}
      />
    </div>
  );
}

function lensFromUrl(): KnowledgeLensId {
  const value = new URL(window.location.href).searchParams.get("knowledgeLens");
  return allLensIds.some((id) => id === value)
    ? value as KnowledgeLensId
    : "map";
}

function assertionFromUrl(): string | null {
  const value = new URL(window.location.href).searchParams.get("subject");
  return value?.startsWith("knowledge:")
    ? value.slice("knowledge:".length)
    : null;
}
