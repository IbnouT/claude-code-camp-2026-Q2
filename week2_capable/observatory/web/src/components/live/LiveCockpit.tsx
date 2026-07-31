import "../../styles/live-cockpit.css";
import { useState } from "react";
import type {
  LiveEconomicsPoint,
  LiveSessionState,
  LiveSnapshot,
  LiveTimelineItem,
  RuntimeSession,
} from "../../data/liveContracts";
import {
  formatLiveCount,
  formatLiveUsd,
  latestTimelineItem,
  liveInputTokens,
  liveOutputTokens,
  type MapMode,
} from "./liveCockpitModel";
import { LiveStage, type CameraMode } from "./LiveStage";

type Props = {
  capabilities: unknown;
  live: LiveSessionState;
  session: RuntimeSession | null;
  onOpenControl: () => void;
  onOpenSearch: () => void;
};

const CONNECTION_MESSAGES: Record<string, string> = {
  discovering: "Discovering live sessions…",
  waiting: "Waiting for the first event from this session.",
  unavailable:
    "The live endpoint is unavailable. Evidence already captured stays readable.",
  ended: "This session has ended. Its full journey remains replayable.",
};

function vitalLabel(key: string): string {
  if (key === "hit") return "HP";
  return key.charAt(0).toUpperCase() + key.slice(1);
}

const VITAL_FILLS: Record<string, string> = {
  hit: "linear-gradient(90deg,#ff5d6c,#f5c463)",
  mana: "linear-gradient(90deg,#5db4ff,#9a8cff)",
  move: "linear-gradient(90deg,#5fdd9d,#4fd6c9)",
};

function combatLineClass(label: string): string {
  const text = label.toLowerCase();
  if (text.includes("critical")) return "crit";
  if (text.includes("dead") || text.includes("killed") || text.includes("xp")) {
    return "kill";
  }
  if (text.includes("hits you") || text.includes("wounds you")) return "dmgin";
  return "hit";
}

function timelineWeight(item: LiveTimelineItem): "major" | "minor" {
  const kind = item.kind.toLowerCase();
  return kind.includes("combat")
      || kind.includes("level")
      || kind.includes("milestone")
      || kind.includes("position")
      || kind.includes("room")
    ? "major"
    : "minor";
}

function timelineWord(item: LiveTimelineItem): string {
  const kind = item.kind.toLowerCase();
  if (kind.includes("combat")) return "combat";
  if (kind.includes("level")) return "level up";
  if (kind.includes("position") || kind.includes("room")) return "room";
  return item.kind;
}

function percent(seq: number, first: number, last: number): number {
  if (last <= first) return 50;
  return Math.min(98, Math.max(2, ((seq - first) / (last - first)) * 100));
}

function costCurve(values: number[], width: number, height: number): string {
  const top = values.at(-1) ?? 0;
  if (values.length < 2 || top <= 0) return "";
  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - 4 - (value / top) * (height - 8);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function cumulativeCostPoints(
  items: LiveTimelineItem[],
  width: number,
  height: number,
): string {
  const costs: number[] = [];
  let running = 0;
  for (const item of items) {
    running += item.cost_usd;
    costs.push(running);
  }
  return costCurve(costs, width, height);
}

function CostSpark({ economics }: { economics: LiveEconomicsPoint[] }) {
  const points = costCurve(
    economics.map((point) => point.cumulative_cost_usd),
    260,
    26,
  );
  if (points === "") {
    return <div className="minirow">cost points not captured yet</div>;
  }
  return (
    <svg aria-hidden="true" className="spark" preserveAspectRatio="none" viewBox="0 0 260 26">
      <polyline fill="none" points={points} stroke="#4fd6c9" strokeWidth="1.6" />
      <polygon fill="#4fd6c922" points={`0,26 ${points} 260,26`} />
    </svg>
  );
}

function cacheHitRate(usage: Record<string, number>): number | null {
  let cached = 0;
  let fresh = 0;
  for (const [key, value] of Object.entries(usage)) {
    if (key.includes("cache_read")) cached += value;
    else if (key.includes("input")) fresh += value;
  }
  const total = cached + fresh;
  return total > 0 ? Math.round((cached / total) * 100) : null;
}

function costPerTurnDelta(items: LiveTimelineItem[]): number | null {
  const paid = items.filter((item) => item.cost_usd > 0);
  const last = paid.at(-1);
  const prev = paid.at(-2);
  if (!last || !prev || prev.cost_usd === 0) return null;
  return Math.round(((last.cost_usd - prev.cost_usd) / prev.cost_usd) * 100);
}

function Rail({
  snapshot,
  controlAvailable,
  onOpenControl,
}: {
  snapshot: LiveSnapshot;
  controlAvailable: boolean;
  onOpenControl: () => void;
}) {
  const guard = controlAvailable ? onOpenControl : undefined;
  const latest = latestTimelineItem(snapshot);
  const turnCost = snapshot.current_turn_cost_usd;
  const economics = snapshot.economics;
  const lastPoint = economics.at(-1);
  const prevPoint = economics.at(-2);
  const delta = lastPoint && prevPoint && prevPoint.cost_usd > 0
    ? Math.round(
      ((lastPoint.cost_usd - prevPoint.cost_usd) / prevPoint.cost_usd) * 100,
    )
    : costPerTurnDelta(snapshot.timeline);
  const cache = cacheHitRate(snapshot.usage);
  const statusFields = snapshot.player_status.fields;
  const vitalMax = (key: string): number | null => {
    const field = statusFields[`${key}_max`] ?? statusFields[`max_${key}`];
    if (field && typeof field.value === "number") return field.value;
    const retained = snapshot.vitals[`${key}_max`];
    return typeof retained === "number" ? retained : null;
  };
  const vitalValue = (key: string): number | null => {
    const field = statusFields[key];
    if (field && typeof field.value === "number") return field.value;
    return key in snapshot.vitals ? snapshot.vitals[key] : null;
  };
  const belief = snapshot.agent_belief;

  return (
    <aside aria-label="Live session detail" className="rail">
      <div className="card obj">
        <h4>Objective</h4>
        <b>
          {(snapshot.objective_initial ?? snapshot.objective_context)?.title
            ?? snapshot.objective
            ?? "No objective recorded"}
        </b>
        {(snapshot.objective_initial ?? snapshot.objective_context)?.clue ? (
          <div className="sub" title="Objective clue from the objective definition, not observed world truth">
            {(snapshot.objective_initial ?? snapshot.objective_context)?.clue}
          </div>
        ) : null}
        <div className="prog" title="Objective progress is not measured live">
          <i style={{ width: 0 }} />
        </div>
        <div className="belief">
          <div>
            <small>Agent intends</small>
            <b
              className="intent-value"
              title={belief?.text ?? undefined}
            >
              {belief?.text ?? "not observed"}
            </b>
          </div>
          <div className={snapshot.combat ? "warn" : undefined}>
            <small>Observed</small>
            <b>
              {snapshot.combat
                ? "In combat"
                : snapshot.current_room ?? "not observed"}
            </b>
          </div>
        </div>
      </div>

      <div className="card agentcard">
        <h4>Direct the agent</h4>
        <div className="curgoal">
          Current goal:{" "}
          <b>
            {snapshot.objective_context?.title
              ?? snapshot.objective
              ?? "none recorded"}
          </b>
        </div>
        <div className="compose">
          <input
            aria-label="Open the agent control dialog"
            disabled={!controlAvailable}
            placeholder="Set or change the goal, or nudge…"
            readOnly
            onClick={guard}
            onFocus={guard}
          />
          <button disabled={!controlAvailable} type="button" onClick={guard}>
            Send
          </button>
        </div>
        <div className="quick">
          <button disabled={!controlAvailable} type="button" onClick={guard}>
            ↻ Reconsider route
          </button>
          {snapshot.suggested_action ? (
            <button
              disabled={!controlAvailable}
              title={snapshot.suggested_action.reason}
              type="button"
              onClick={controlAvailable
                ? () => {
                  window.dispatchEvent(
                    new CustomEvent("boukensha:control-prefill", {
                      detail: {
                        instruction: snapshot.suggested_action?.instruction,
                        reason: snapshot.suggested_action?.reason,
                        expected_sequence:
                          snapshot.suggested_action?.expected_sequence,
                      },
                    }),
                  );
                  onOpenControl();
                }
                : undefined}
            >
              ⤴ {snapshot.suggested_action.label}
            </button>
          ) : null}
          <button disabled={!controlAvailable} type="button" onClick={guard}>
            ✎ Replace goal
          </button>
        </div>
        <div className="ghint">
          {controlAvailable
            ? "Delivered to the agent (mortal) on this live session · asks you"
              + " to confirm before it takes effect · never writes to the game"
              + " world directly."
            : `Read-only: this session has no live control endpoint${
              snapshot.control_state ? ` (${snapshot.control_state})` : ""
            }. The cockpit keeps showing captured evidence.`}
        </div>
      </div>

      <div className="card">
        <h4>Vitals</h4>
        {(["hit", "mana", "move"] as const).every(
          (key) => vitalValue(key) === null,
        ) ? (
          <div className="sub">Vitals not captured yet.</div>
        ) : (
          <div className="vit">
            {(["hit", "mana", "move"] as const)
              .filter((key) => vitalValue(key) !== null)
              .map((key) => {
                const value = vitalValue(key) as number;
                const max = vitalMax(key);
                return (
                  <div className="vrow" key={key}>
                    <span className="lab">{vitalLabel(key)}</span>
                    <span
                      className="bar"
                      title={max === null
                        ? "Maximum is not captured; the bar shows no invented ratio"
                        : undefined}
                    >
                      <i
                        style={{
                          width: max === null || max <= 0
                            ? 0
                            : `${Math.min(100, (value / max) * 100)}%`,
                          background: VITAL_FILLS[key],
                        }}
                      />
                    </span>
                    <span className="num">
                      {max === null ? value : `${value}/${max}`}
                    </span>
                  </div>
                );
              })}
          </div>
        )}
      </div>

      <div className="card">
        <h4>Live economics</h4>
        <div className="econ">
          <div className="stat">
            <div className="k">Spend so far</div>
            <div
              className="v"
              title={snapshot.spend_cap_usd === null
                ? "No spend cap is configured on this session"
                : undefined}
            >
              {formatLiveUsd(snapshot.cost_usd)}
              {snapshot.spend_cap_usd === null ? null : (
                <small> / {formatLiveUsd(snapshot.spend_cap_usd)} cap</small>
              )}
            </div>
          </div>
          <div className="stat">
            <div className="k">Cost / turn</div>
            <div className="v">
              {formatLiveUsd(turnCost)}
              {delta === null ? null : (
                <small className={delta >= 0 ? "delta up" : "delta dn"}>
                  {" "}{delta >= 0 ? "▲" : "▼"} {Math.abs(delta)}%
                </small>
              )}
            </div>
          </div>
          <div className="stat wide">
            <div className="k">Cost per response: cumulative</div>
            <CostSpark economics={economics} />
            <div className="minirow">
              <span>context growth drives the climb</span>
              <span className="mono">↑</span>
            </div>
          </div>
          <div className="stat">
            <div className="k">Tokens · in/out</div>
            <div className="v" style={{ fontSize: 14 }}>
              {formatLiveCount(liveInputTokens(snapshot))}{" "}
              <small>/ {formatLiveCount(liveOutputTokens(snapshot))}</small>
            </div>
          </div>
          <div className="stat">
            <div className="k">Cache hit</div>
            <div className="v">{cache === null ? "—" : `${cache}%`}</div>
          </div>
          <div className="stat wide">
            <div className="minirow" style={{ marginTop: 0 }}>
              <span>Context window</span>
              <span className="mono">
                {lastPoint
                  ? formatLiveCount(lastPoint.context_tokens)
                  : "not observed"}
                {" / "}
                {snapshot.context_limit === null
                  ? "not observed"
                  : formatLiveCount(snapshot.context_limit)}
              </span>
            </div>
            <div className="prog" style={{ marginTop: 6 }}>
              <i
                style={{
                  width: lastPoint
                      && snapshot.context_limit !== null
                      && snapshot.context_limit > 0
                    ? `${Math.min(100, (lastPoint.context_tokens / snapshot.context_limit) * 100)}%`
                    : 0,
                  background: "linear-gradient(90deg,#5db4ff,#9a8cff)",
                }}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h4>Activity</h4>
        <div className="actv">
          {snapshot.combat ? (
            <span aria-hidden="true" className="ic">⚔</span>
          ) : null}
          <span>{latest?.label ?? "No activity captured yet."}</span>
        </div>
      </div>
    </aside>
  );
}

/** Semantic timeline projection: the full retained timeline stays evidence;
 * the spine renders semantic MARKERS (room transitions, milestones, combat
 * episode boundaries, control actions) plus deterministic clusters of minor
 * activity, with forward headroom while following live. */
type SpineMarker = {
  key: string;
  kind: "room" | "milestone" | "combat" | "control" | "cluster";
  sequence: number;
  label: string;
  count: number;
  firstId: string;
};

const HEADROOM_MAX = 92;

/** Quiet semantic spine (mock signature): ONE labelled room-entry landmark,
 * the LATEST level transition, combat start (quiet) + latest combat
 * (labelled) when the episode spans several retained observations, and all
 * remaining records collapsed into server-assigned quiet_cohort runs.
 * Every retained event stays reachable through the cluster evidence
 * links. */
function spineMarkers(snapshot: LiveSnapshot): SpineMarker[] {
  const markers: SpineMarker[] = [];
  const consumed = new Set<string>();

  // Representative room-entry landmark: the first transition to a new room
  // label inside the visible window.
  let lastRoomLabel: string | null = null;
  let roomLandmark: (typeof snapshot.timeline)[number] | null = null;
  for (const item of snapshot.timeline) {
    const kind = item.kind.toLowerCase();
    if (kind.includes("position") || kind.includes("room")) {
      if (item.label !== lastRoomLabel) {
        lastRoomLabel = item.label;
        if (roomLandmark === null) roomLandmark = item;
      }
    }
  }
  if (roomLandmark) {
    consumed.add(roomLandmark.id);
    markers.push({
      key: `room-${roomLandmark.id}`,
      kind: "room",
      sequence: roomLandmark.sequence,
      label: roomLandmark.label,
      count: 1,
      firstId: roomLandmark.id,
    });
  }

  // Combat: episode start (quiet) + latest observation (labelled); a single
  // retained observation projects one marker.
  const combatRecords = snapshot.timeline.filter((item) =>
    item.kind.toLowerCase().includes("combat"));
  const combatStart = combatRecords.at(0);
  const combatLatest = combatRecords.at(-1);
  if (combatStart) {
    consumed.add(combatStart.id);
    markers.push({
      key: `combat-${combatStart.id}`,
      kind: "combat",
      sequence: combatStart.sequence,
      label: "combat",
      count: 1,
      firstId: combatStart.id,
    });
  }
  if (combatLatest && combatLatest.id !== combatStart?.id) {
    consumed.add(combatLatest.id);
    markers.push({
      key: `combat-${combatLatest.id}`,
      kind: "combat",
      sequence: combatLatest.sequence,
      label: "combat",
      count: 1,
      firstId: combatLatest.id,
    });
  }

  // Operator control actions stay individually visible (quiet).
  for (const item of snapshot.timeline) {
    const kind = item.kind.toLowerCase();
    if (kind.includes("control") || kind.includes("operator")) {
      consumed.add(item.id);
      markers.push({
        key: `control-${item.id}`,
        kind: "control",
        sequence: item.sequence,
        label: item.label,
        count: 1,
        firstId: item.id,
      });
    }
  }

  // Latest level transition only. A level transition is a gateway
  // player-state observation, so the correlated timeline record (same
  // sequence) is consumed here — it must not count again inside a quiet
  // cluster.
  const milestone = snapshot.milestones.at(-1);
  if (milestone) {
    for (const item of snapshot.timeline) {
      if (item.sequence === milestone.sequence) consumed.add(item.id);
    }
    markers.push({
      key: `milestone-${milestone.sequence}`,
      kind: "milestone",
      sequence: milestone.sequence,
      label: "level up",
      count: 1,
      firstId: milestone.evidence,
    });
  }

  // Quiet activity cohorts: server-assigned, evidence-backed runs
  // (timeline[].quiet_cohort — landmarks keep null). One marker per cohort
  // at the member median sequence; positions derive purely from retained
  // record sequences.
  const cohorts = new Map<string, typeof snapshot.timeline>();
  for (const item of snapshot.timeline) {
    if (consumed.has(item.id) || item.quiet_cohort === null) continue;
    const list = cohorts.get(item.quiet_cohort);
    if (list) list.push(item);
    else cohorts.set(item.quiet_cohort, [item]);
  }
  for (const [cohort, list] of cohorts) {
    markers.push({
      key: `cluster-${cohort}`,
      kind: "cluster",
      sequence: list[Math.floor(list.length / 2)].sequence,
      label: `${list.length} retained records`,
      count: list.length,
      firstId: list[0].id,
    });
  }

  return markers.sort((a, b) => a.sequence - b.sequence);
}

function markerColor(kind: SpineMarker["kind"]): string {
  if (kind === "combat") return "var(--live-rose)";
  if (kind === "milestone") return "var(--live-amber)";
  if (kind === "room") return "var(--live-aqua)";
  if (kind === "control") return "var(--color-cyan)";
  return "#2f5680";
}

function Spine({
  snapshot,
  onOpenSearch,
}: {
  snapshot: LiveSnapshot;
  onOpenSearch: () => void;
}) {
  const items = snapshot.timeline;
  const first = items.at(0)?.sequence ?? 0;
  const last = Math.max(snapshot.latest_sequence, items.at(-1)?.sequence ?? 0);
  // Forward headroom: positions scale into [2, 92] while following live.
  const pos = (sequence: number): number =>
    last <= first
      ? 50
      : 2 + ((sequence - first) / (last - first)) * (HEADROOM_MAX - 2);
  const markers = spineMarkers(snapshot);
  // Label the latest marker of each distinct semantic kind.
  const labelled = (["room", "milestone", "combat"] as const)
    .map((kind) =>
      [...markers].reverse().find((marker) => marker.kind === kind))
    .filter((marker): marker is SpineMarker => marker !== undefined);
  const costPoints = costCurve(
    snapshot.economics.map((point) => point.cumulative_cost_usd),
    (900 * HEADROOM_MAX) / 100,
    22,
  );

  return (
    <div className="spine">
      <div className="sh">
        <small>Journey timeline</small>
        <span className="rt">
          turn {snapshot.turn ?? snapshot.iteration}
          {" · "}
          {snapshot.following_live ? "following live" : "time travel"}
          {"  ·  "}
          {formatLiveUsd(snapshot.cost_usd)} spent
        </span>
      </div>
      <div className="track">
        <div className="axis" />
        {costPoints === "" ? null : (
          <svg aria-hidden="true" className="costline" preserveAspectRatio="none" viewBox="0 0 900 22">
            <polyline fill="none" points={costPoints} stroke="#243449" strokeWidth="1.4" />
          </svg>
        )}
        {markers.map((marker) => (
          <button
            aria-label={marker.count > 1
              ? `Open ${marker.count} retained records near sequence ${marker.sequence}`
              : `Open evidence: ${marker.label} at sequence ${marker.sequence}`}
            className={marker.kind === "cluster" ? "ev small" : "ev"}
            key={marker.key}
            style={{
              left: `${pos(marker.sequence)}%`,
              background: markerColor(marker.kind),
            }}
            title={marker.label}
            type="button"
            onClick={() => {
              const url = new URL(window.location.href);
              url.searchParams.set("evidence", marker.firstId);
              url.searchParams.set("seq", String(marker.sequence));
              window.history.replaceState(null, "", url);
              onOpenSearch();
            }}
          />
        ))}
        <div
          className="cursor"
          style={{ left: `${pos(snapshot.through_sequence)}%` }}
        />
        {labelled.map((marker) => (
          <span
            className="tlab"
            key={`label-${marker.key}`}
            style={{ left: `${pos(marker.sequence)}%` }}
          >
            {marker.kind === "room"
              ? "room"
              : marker.kind === "milestone"
                ? "level up"
                : "combat"}
          </span>
        ))}
      </div>
    </div>
  );
}

const MAP_MODES: { id: MapMode; label: string }[] = [
  { id: "grow", label: "Grow" },
  { id: "focus", label: "Focus" },
  { id: "lantern", label: "Lantern" },
];

/** Small worlds render whole (Grow); Focus becomes the default once the
 *  learned graph is large enough to crowd (map_modes.html: "crowds fast:
 *  40+ rooms"). Explicit user choice always wins. */
const FOCUS_AUTO_THRESHOLD = 12;

export function LiveCockpit({ live, session, onOpenControl, onOpenSearch }: Props) {
  const [chosenMode, setChosenMode] = useState<MapMode | null>(null);
  const [camera, setCamera] = useState<CameraMode>("follow");
  const [zoom, setZoom] = useState(1);
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(
    () => new URL(window.location.href).searchParams.get("room"),
  );
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const snapshot = live.snapshot;
  const mode: MapMode = chosenMode
    ?? ((snapshot?.world.nodes.length ?? 0) > FOCUS_AUTO_THRESHOLD
      ? "focus"
      : "grow");
  const emptyMessage = snapshot === null
    ? CONNECTION_MESSAGES[live.connection]
      ?? (live.error ?? "No live evidence is available yet.")
    : null;

  if (snapshot === null) {
    return (
      <div aria-label="Live cockpit" className="live-cockpit" role="region">
        <div className="body">
          <div className="stage">
            <div className="stage-empty" role="status">{emptyMessage}</div>
          </div>
        </div>
      </div>
    );
  }
  const controlAvailable = session?.control_available === true;

  const observedRooms = snapshot.world.nodes.filter(
    (node) => node.state !== "candidate",
  ).length;
  const candidateRooms = snapshot.world.nodes.length - observedRooms;
  const milestone = snapshot.milestones
    .filter((item) => item.sequence <= snapshot.through_sequence)
    .at(-1);
  const milestoneRecent = milestone !== undefined
    && snapshot.through_sequence - milestone.sequence < 100;
  const thought = snapshot.agent_thought;
  const episode = snapshot.combat_episode;

  return (
    <div aria-label="Live cockpit" className="live-cockpit" role="region">
      <div className="body">
        <div className="stage">
          <div className="stagehead">
            <span className="chip">
              Turn <b>{snapshot.turn ?? "not observed"}</b>
              {" / iteration "}
              <b>{snapshot.iteration}</b>
            </span>
            <span className="chip">
              Zone <b>{snapshot.zone?.label ?? "unknown"}</b>
            </span>
            <span className="chip">
              Learned world <b>{observedRooms} rooms</b>
              {snapshot.world.frontier.length > 0
                ? ` · ${snapshot.world.frontier.length} frontier`
                : ""}
            </span>
            {snapshot.capture_gaps.length > 0 ? (
              <span
                className="chip gap"
                role="status"
                title={snapshot.capture_gaps.join(" · ")}
              >
                capture gaps <b>{snapshot.capture_gaps.length}</b>
              </span>
            ) : null}
          </div>
          <div className="stagetools">
            <div aria-label="Camera" className="toolbar" role="group">
              <small className="toolbar-label">Camera</small>
              <button
                className={camera === "follow" ? "on" : undefined}
                title="Follow agent"
                type="button"
                onClick={() => setCamera("follow")}
              >
                ⌖ Follow agent
              </button>
              <button
                className={camera === "center" ? "on" : undefined}
                title="Center the map on a clicked room"
                type="button"
                onClick={() => setCamera("center")}
              >
                ✛ Click-to-center
              </button>
            </div>
            <div aria-label="Map mode" className="toolbar" role="group">
              {MAP_MODES.map((item) => (
                <button
                  className={mode === item.id ? "on" : undefined}
                  key={item.id}
                  type="button"
                  onClick={() => setChosenMode(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <button
              aria-label="Zoom in"
              className="tool"
              title="Zoom in"
              type="button"
              onClick={() => setZoom((value) => Math.min(2, value * 1.25))}
            >
              +
            </button>
            <button
              aria-label="Zoom out"
              className="tool"
              title="Zoom out"
              type="button"
              onClick={() => setZoom((value) => Math.max(0.5, value / 1.25))}
            >
              −
            </button>
            <button
              aria-label="Ask about this session"
              className="tool ask"
              title="Ask about this session (⌘K)"
              type="button"
              onClick={onOpenSearch}
            >
              Ask
            </button>
          </div>

          {milestone && milestoneRecent ? (
            <div className="toast" role="status">
              ▲ LEVEL UP: now level {milestone.current}
            </div>
          ) : null}

          <LiveStage
            camera={camera}
            zoom={zoom}
            expanded={expanded}
            mode={mode}
            selectedRoomId={selectedRoomId}
            snapshot={snapshot}
            thought={thought}
            onOpenEvidence={(node) => {
              const url = new URL(window.location.href);
              url.searchParams.set("room", node.id);
              url.searchParams.set("seq", String(node.last_seq));
              window.history.replaceState(null, "", url);
              onOpenSearch();
            }}
            onSelectRoom={(roomId) => {
              setSelectedRoomId(roomId);
              const url = new URL(window.location.href);
              if (roomId) url.searchParams.set("room", roomId);
              else url.searchParams.delete("room");
              window.history.replaceState(null, "", url);
            }}
            onToggleExpand={(boundaryId) => {
              setExpanded((previous) => {
                const next = new Set(previous);
                if (next.has(boundaryId)) next.delete(boundaryId);
                else next.add(boundaryId);
                return next;
              });
            }}
          />

          {episode && (episode.active || episode.outcome !== null) ? (
            <div className="combat">
              <div className="ch">
                <span aria-hidden="true" className="ic">⚔</span>
                <div>
                  <b>
                    {episode.active
                      ? episode.opponent === null
                        ? "In combat"
                        : `In combat: ${episode.opponent}`
                      : episode.outcome === "victory"
                        ? `Victory${episode.opponent ? `: ${episode.opponent}` : ""}`
                        : episode.outcome === "defeated"
                          ? "Defeated"
                          : episode.outcome === "fled"
                            ? "Fled combat"
                            : `Combat ${episode.outcome ?? "ended"}`}
                  </b>
                  <br />
                  <small>
                    exchange {episode.observed_exchanges}
                    {episode.first_observed_turn === null
                      ? ""
                      : ` · since turn ${episode.first_observed_turn}`}
                  </small>
                </div>
              </div>
              <div className="lines mono">
                {episode.lines.length === 0 ? (
                  <span className="hit">combat lines not captured</span>
                ) : (
                  episode.lines.slice(-4).map((line) => (
                    <span
                      className={combatLineClass(line.text)}
                      key={line.sequence}
                    >
                      {line.text}
                    </span>
                  ))
                )}
              </div>
            </div>
          ) : null}

          <div className="legend">
            <h5>Legend</h5>
            <div className="row">
              <span className="sw" style={{ background: "#1c3350", border: "1px solid #2f5680" }} />
              Visited room
            </div>
            <div className="row">
              <span className="sw" style={{ background: "#3a1620", border: "1px solid #ff5d6c" }} />
              Current · combat
            </div>
            <div className="row">
              <span className="sw" style={{ background: "none", border: "1px dashed #26374b" }} />
              Frontier (unexplored)
            </div>
            <div className="row">
              <span className="sw" style={{ background: "none", border: "1px dashed #6a5a2a" }} />
              Ambiguous (dup title)
            </div>
            <div className="row">
              <span className="sw" style={{ background: "#ff5d6c", borderRadius: "50%" }} />
              Mob sighting
            </div>
          </div>

          <div className="hint">
            Click any room, event, or cost point to open its evidence: summary → wire.
          </div>
        </div>

        <Rail
          controlAvailable={controlAvailable}
          snapshot={snapshot}
          onOpenControl={onOpenControl}
        />
      </div>

      <Spine snapshot={snapshot} onOpenSearch={onOpenSearch} />
    </div>
  );
}
