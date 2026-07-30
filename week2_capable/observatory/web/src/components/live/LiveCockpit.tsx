import {
  AlertTriangle,
  ArrowRight,
  Bookmark,
  CircleDollarSign,
  Clock3,
  Database,
  Gauge,
  Pause,
  Play,
  Radio,
  Route,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ShellCapabilities, WorkspaceFixture } from "../../app/shellTypes";
import type { RuntimeSession } from "../../data/liveContracts";
import type { SessionEvidence } from "../../data/useSessionStream";
import { emptyWorld } from "../../data/worldContracts";
import { EvidenceForms } from "../system/EvidenceForms";
import { StateBadge } from "../system/StateBadge";
import { WorldExplorer } from "../world/WorldExplorer";

type Props = {
  capabilities: ShellCapabilities;
  live: SessionEvidence;
  session: RuntimeSession | null;
  onOpenControl: () => void;
  onOpenSearch: () => void;
};

export function LiveCockpit({
  capabilities,
  live,
  session,
  onOpenControl,
  onOpenSearch,
}: Props) {
  const [bookmarks, setBookmarks] = useState<number[]>([]);
  const [selectedWorldNodeId, setSelectedWorldNodeId] = useState<string | null>(null);
  useEffect(() => {
    setBookmarks([]);
    setSelectedWorldNodeId(null);
  }, [session?.id]);
  const snapshot = live.snapshot;
  const selectedEvent = live.events.find(
    (event) => event.seq === live.selectedSequence,
  );
  const evidence = useMemo<WorkspaceFixture["evidence"]>(
    () => evidenceFor(snapshot, selectedEvent?.kind, selectedEvent?.data),
    [selectedEvent, snapshot],
  );
  const liveSources = capabilities.sources.filter(
    (source) => source.id === "gateway" || source.id === "agent",
  );
  const readySources = liveSources.filter(
    (source) => source.state === "ready",
  ).length;
  const unavailableSource = liveSources.find(
    (source) => source.state === "unavailable",
  );
  const incompleteSources = liveSources.filter(
    (source) => source.state !== "ready",
  );
  const latestAt = live.events.at(-1)?.at;
  const freshness = latestAt === undefined
    ? "no event yet"
    : formatAge(Math.max(0, Date.now() - latestAt * 1_000));
  const tokens = snapshot === null
    ? 0
    : Object.values(snapshot.usage).reduce((total, value) => total + value, 0);
  const canControl = Boolean(
    session?.live
    && session.control_available
    && !["capture_gap", "quarantined", "stopped"].includes(
      snapshot?.control_state ?? "",
    ),
  );

  return (
    <div className="workspace live-workspace">
      <section className="workspace-intro" aria-labelledby="workspace-title">
        <div>
          <p className="eyebrow">Live · {connectionLabel(live.connection)}</p>
          <h1 id="workspace-title">
            {snapshot?.combat
              ? "The agent is in combat"
              : "Watch the journey form as the agent acts"}
          </h1>
          <p>
            {session === null
              ? "Start an agent or select a registered session to observe it."
              : `${session.character} · ${shortId(session.id)} · ${session.state}`}
          </p>
        </div>
        <div className="workspace-actions">
          <button className="secondary-button" type="button" onClick={onOpenSearch}>
            <Search size={14} aria-hidden="true" />
            Ask about this run
          </button>
          <div className="workspace-status">
            <StateBadge state={live.connection === "unavailable" ? "incomplete" : "actual"}>
              {connectionLabel(live.connection)}
            </StateBadge>
            <span>
              <Clock3 size={13} aria-hidden="true" />
              seq {live.selectedSequence}/{live.latestSequence}
            </span>
            <span><Radio size={13} aria-hidden="true" /> {freshness}</span>
          </div>
        </div>
      </section>

      {live.error ? (
        <section className="inline-failure" role="alert">
          <AlertTriangle size={17} aria-hidden="true" />
          <span>
            <strong>Live evidence is unavailable</strong>
            <small>{live.error}</small>
          </span>
        </section>
      ) : null}

      <section className="workspace-grid">
        <WorldExplorer
          className="world-card"
          combat={snapshot?.combat}
          eyebrow="Selected journey"
          onSelectNode={setSelectedWorldNodeId}
          selectedNodeId={selectedWorldNodeId}
          title="Living world"
          world={snapshot?.world ?? emptyWorld}
        />

        <aside className="attention-rail" aria-label="Run context and attention">
          <section className="attention-card">
            <div className="panel-heading">
              <span>
                <p className="eyebrow">Objective</p>
                <h2>{snapshot?.objective ?? "Objective not captured"}</h2>
              </span>
              <Route size={17} aria-hidden="true" />
            </div>
            <div className="belief-block">
              <StateBadge state="actual">Observed</StateBadge>
              <p>
                {snapshot?.current_room
                  ? `The latest observed room is ${snapshot.current_room}.`
                  : "No room observation is available in this prefix."}
              </p>
            </div>
            <div className="belief-block">
              <StateBadge state="believed">Agent account</StateBadge>
              <p>
                Agent reasoning appears only when its event stream contains it.
                It is never inferred from gateway activity.
              </p>
            </div>
            <button
              className="primary-button full-width"
              disabled={!canControl}
              type="button"
              onClick={onOpenControl}
            >
              {canControl ? "Direct the agent" : "Control unavailable"}
              <ArrowRight size={14} aria-hidden="true" />
            </button>
          </section>

          {snapshot !== null && snapshot.capture_gaps.length > 0 ? (
            <section className="attention-card diagnostic-card">
              <div className="diagnostic-icon" aria-hidden="true">
                <AlertTriangle size={17} />
              </div>
              <div>
                <p className="eyebrow">Capture gap</p>
                <h2>{captureGapTitle(snapshot.capture_gaps[0])}</h2>
                <p>{captureGapDetail(snapshot.capture_gaps[0])}</p>
                <button className="text-button" type="button">
                  Inspect instrumentation <ArrowRight size={13} aria-hidden="true" />
                </button>
              </div>
            </section>
          ) : null}

          {unavailableSource !== undefined ? (
            <section className="attention-card diagnostic-card">
              <div className="diagnostic-icon" aria-hidden="true">
                <AlertTriangle size={17} />
              </div>
              <div>
                <p className="eyebrow">Instrumentation issue</p>
                <h2>{unavailableSource.label} is unavailable</h2>
                <p>{unavailableSource.detail}</p>
              </div>
            </section>
          ) : null}

          <section className="metrics-card" aria-label="Live economics">
            <div>
              <CircleDollarSign size={15} aria-hidden="true" />
              <span>
                <small>Observed cost</small>
                <strong>{formatUsd(snapshot?.cost_usd)}</strong>
              </span>
            </div>
            <div>
              <Gauge size={15} aria-hidden="true" />
              <span>
                <small>Iteration</small>
                <strong>{snapshot?.iteration ?? 0}</strong>
              </span>
            </div>
            <div>
              <Database size={15} aria-hidden="true" />
              <span>
                <small>Tokens</small>
                <strong>{formatCount(tokens)}</strong>
              </span>
            </div>
          </section>

          <section className="source-card">
            <ShieldCheck size={17} aria-hidden="true" />
            <span>
              <small>Instrumentation completeness</small>
              <strong>
                {snapshot?.capture_gaps.length
                  ? `${snapshot.capture_gaps.length} visible capture gap${snapshot.capture_gaps.length === 1 ? "" : "s"}`
                  : `${readySources}/${liveSources.length} Live sources ready`}
              </strong>
            </span>
            <StateBadge state={
              snapshot?.capture_gaps.length || incompleteSources.length
                ? "incomplete"
                : "actual"
            }>
              {snapshot?.capture_gaps.length || incompleteSources.length
                ? "Incomplete"
                : "Complete"}
            </StateBadge>
          </section>
        </aside>

        <section className="timeline-card live-timeline" aria-labelledby="timeline-heading">
          <div className="panel-heading">
            <span>
              <p className="eyebrow">Causal time</p>
              <h2 id="timeline-heading">Activity</h2>
            </span>
            <div className="timeline-controls">
              <button
                className="icon-button"
                disabled={!live.followingLive || live.latestSequence === 0}
                type="button"
                aria-label="Pause live following"
                onClick={() => live.select(live.latestSequence)}
              >
                <Pause size={14} aria-hidden="true" />
              </button>
              <button
                className="icon-button"
                disabled={live.followingLive}
                type="button"
                aria-label="Return to live"
                onClick={live.resume}
              >
                <Play size={14} aria-hidden="true" />
              </button>
              <button
                className="icon-button"
                disabled={live.selectedSequence === 0}
                type="button"
                aria-label="Bookmark selected sequence"
                onClick={() => {
                  setBookmarks((current) => (
                    current.includes(live.selectedSequence)
                      ? current.filter((value) => value !== live.selectedSequence)
                      : [...current, live.selectedSequence].sort((left, right) => left - right)
                  ));
                }}
              >
                <Bookmark size={14} aria-hidden="true" />
              </button>
            </div>
          </div>
          <div className="time-scrubber">
            <input
              aria-label="Selected sequence"
              disabled={live.latestSequence === 0}
              max={Math.max(1, live.latestSequence)}
              min="1"
              type="range"
              value={Math.max(1, live.selectedSequence)}
              onChange={(event) => live.select(Number(event.target.value))}
            />
            <span>
              {live.followingLive ? "Following live" : `Paused at #${live.selectedSequence}`}
            </span>
            {bookmarks.length > 0 ? (
              <span>{bookmarks.length} bookmark{bookmarks.length === 1 ? "" : "s"}</span>
            ) : null}
          </div>
          {snapshot !== null && snapshot.timeline.length > 0 ? (
            <ol className="timeline-list">
              {snapshot.timeline.slice(-30).map((item) => (
                <li
                  className={`timeline-item item-${timelineKind(item.kind)} ${
                    item.sequence === live.selectedSequence ? "is-selected" : ""
                  }`}
                  key={item.id}
                >
                  <button
                    aria-label={`Select sequence ${item.sequence}: ${item.label}`}
                    disabled={item.sequence === 0}
                    type="button"
                    onClick={() => live.select(item.sequence)}
                  >
                    <span className="timeline-symbol" aria-hidden="true" />
                    <time>{formatTime(item.at)}</time>
                    <span className="timeline-label">{item.label}</span>
                    <code>#{item.sequence || "pre"}</code>
                    <span className="timeline-cost">
                      {item.cost_usd > 0 ? formatUsd(item.cost_usd) : item.source}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <div className="timeline-empty">No causal events captured yet.</div>
          )}
        </section>

        <EvidenceForms evidence={evidence} />
      </section>

      <footer className="workspace-footer">
        <span>
          <Sparkles size={13} aria-hidden="true" />
          {session?.legacy ? "Legacy gateway source" : "Launcher registry source"}
        </span>
        <span>
          {live.followingLive ? "Live prefix" : `Historical prefix through #${live.selectedSequence}`}
        </span>
      </footer>
    </div>
  );
}

function evidenceFor(
  snapshot: SessionEvidence["snapshot"],
  selectedKind: string | undefined,
  selectedData: Record<string, unknown> | undefined,
): WorkspaceFixture["evidence"] {
  const selected = selectedData === undefined
    ? "No event is selected."
    : JSON.stringify(selectedData, null, 2);
  return {
    wire: {
      state: selectedKind === "wire" ? "available" : "missing",
      preview: selectedKind === "wire"
        ? selected
        : "Select a wire event to inspect its captured frame metadata.",
    },
    parsed: {
      state: snapshot?.current_room ? "available" : "missing",
      preview: snapshot?.current_room
        ? `room=${snapshot.current_room} · confidence=${snapshot.position_confidence} · method=${snapshot.position_method ?? "not captured"}`
        : "No parsed position exists in this prefix.",
    },
    rendered: {
      state: snapshot ? "available" : "missing",
      preview: snapshot
        ? `${snapshot.rooms.length} observed spatial identities · ${snapshot.timeline.length} causal items`
        : "No live projection is available.",
    },
    believed: {
      state: "missing",
      preview: "No agent belief record is linked to the selected event.",
    },
    truth: {
      state: "missing",
      preview: "Observer truth is not configured for this live session.",
    },
  };
}

function connectionLabel(value: SessionEvidence["connection"]): string {
  return {
    discovering: "Discovering sessions",
    waiting: "Waiting for evidence",
    streaming: "Streaming",
    paused: "Viewing history",
    replaying: "Reconstructing",
    ended: "Recorded session",
    unavailable: "Unavailable",
  }[value];
}

function captureGapTitle(value: string): string {
  return {
    agent_events_missing: "Agent events were not captured",
    agent_events_incomplete: "Agent event stream is incomplete",
    gateway_events_missing: "Gateway events were not captured",
    position_not_observed: "Position has not been observed",
  }[value] ?? value.replaceAll("_", " ");
}

function captureGapDetail(value: string): string {
  if (value.startsWith("agent_events")) {
    return "Gateway activity remains visible, but objective, reasoning, tokens, and model cost cannot be reconstructed.";
  }
  if (value === "gateway_events_missing") {
    return "The agent record may exist, but no game or parser evidence can be shown.";
  }
  return "The map remains empty until a traceable room or position observation arrives.";
}

function timelineKind(kind: string): string {
  if (kind.includes("tool") || kind === "command") {
    return "tool";
  }
  if (kind.includes("observation") || kind === "position") {
    return "observation";
  }
  if (kind.includes("diagnostic") || kind.includes("limit")) {
    return "diagnostic";
  }
  return "model";
}

function formatTime(value: number): string {
  return new Date(value * 1_000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatAge(milliseconds: number): string {
  if (milliseconds < 1_000) {
    return `${Math.round(milliseconds)} ms`;
  }
  if (milliseconds < 60_000) {
    return `${Math.round(milliseconds / 1_000)} s`;
  }
  return `${Math.round(milliseconds / 60_000)} min`;
}

function formatUsd(value: number | undefined): string {
  return value === undefined ? "not captured" : `$${value.toFixed(4)}`;
}

function formatCount(value: number): string {
  return value >= 1_000 ? `${(value / 1_000).toFixed(1)}k` : String(value);
}

function shortId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}
