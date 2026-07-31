import "../../styles/sessions-unified.css";
import { useEffect, useMemo, useState } from "react";
import type {
  RecordedSessionInvestigation,
  SessionEvidenceRecord,
} from "../../data/recordedSession";
import { worldMapLayout } from "../live/liveCockpitModel";

type IncidentContext = {
  annotations: unknown[];
  sourceVersions: Record<string, unknown>;
  redactionPolicy: unknown;
  history: unknown;
};

type Props = {
  investigation: RecordedSessionInvestigation | null;
  loading: boolean;
  error: string | null;
  sourceState: "offline" | "recorded";
  incident: IncidentContext;
  onOpenSearch: () => void;
  onOpenRun: (runId: string) => void;
};

type LensChoice = "both" | "sequence" | "cost";

export function stepClass(record: SessionEvidenceRecord): string {
  const kind = record.kind.toLowerCase();
  if (kind.includes("plan") || kind.includes("reason")) return "kplan";
  if (record.source === "gateway" || kind.includes("tool") || kind.includes("command")) {
    return "ktool";
  }
  if (kind.includes("context") || kind.includes("memory")) return "kctx";
  return "kmodel";
}

function stepLabel(record: SessionEvidenceRecord): string {
  const cls = stepClass(record);
  if (cls === "kplan") return "Plan";
  if (cls === "kctx") return "Context injected";
  if (cls === "kmodel") return "Model call";
  return record.label;
}

function usd(value: number): string {
  return `$${value.toFixed(4)}`;
}

function formatK(value: number): string {
  return value >= 1_000 ? `${(value / 1_000).toFixed(1)}k` : String(value);
}

export function SessionsWorkspace({
  investigation,
  loading,
  error,
  sourceState,
  incident,
  onOpenSearch,
}: Props) {
  const [lens, setLens] = useState<LensChoice>("both");
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    new URL(window.location.href).searchParams.get("record"));
  const [openIteration, setOpenIteration] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);

  const records = investigation?.records ?? [];
  const selected = records.find((record) => record.id === selectedId) ?? null;
  const selectedIndex = selected === null
    ? -1
    : records.findIndex((record) => record.id === selected.id);

  /* initial linked selection: URL record if valid, else the last retained
     record — the investigation always opens with a synchronized selection */
  useEffect(() => {
    if (records.length === 0) return;
    setSelectedId((current) => {
      const valid = current !== null
        && records.some((record) => record.id === current);
      const chosen = valid ? current : records[records.length - 1].id;
      const owner = records.find((record) => record.id === chosen);
      if (owner && owner.iteration !== null) {
        setOpenIteration(owner.iteration);
      }
      return chosen;
    });
  }, [records]);

  /* auto replay: advance the selection through evidence order */
  useEffect(() => {
    if (!playing || records.length === 0) return undefined;
    const timer = window.setInterval(() => {
      setSelectedId((current) => {
        const index = records.findIndex((record) => record.id === current);
        const next = records[index + 1];
        if (!next) {
          setPlaying(false);
          return current;
        }
        return next.id;
      });
    }, 600);
    return () => window.clearInterval(timer);
  }, [playing, records]);

  const iterations = useMemo(() => {
    const map = new Map<number, SessionEvidenceRecord[]>();
    for (const record of records) {
      if (record.iteration === null) continue;
      const list = map.get(record.iteration);
      if (list) list.push(record);
      else map.set(record.iteration, [record]);
    }
    return [...map.entries()].sort((a, b) => a[0] - b[0]);
  }, [records]);

  const layout = useMemo(
    () =>
      investigation === null
        ? { nodes: [], edges: [], conflicts: [] }
        : worldMapLayout(investigation.world.nodes, investigation.world.edges),
    [investigation],
  );

  if (loading) {
    return (
      <div
        aria-label="Sessions investigation"
        className="sessions-unified"
        role="region"
      >
        <div className="workspace-note" role="status">Opening the recorded investigation…</div>
      </div>
    );
  }
  if (error !== null) {
    return (
      <div
        aria-label="Sessions investigation"
        className="sessions-unified"
        role="region"
      >
        <div className="workspace-note" role="alert">{error}</div>
      </div>
    );
  }
  if (investigation === null) {
    return (
      <div
        aria-label="Sessions investigation"
        className="sessions-unified"
        role="region"
      >
        <div className="workspace-note" role="status">
          No recorded session is selected. Pick a session in the header.
        </div>
      </div>
    );
  }

  const run = investigation.run;
  const turns = records.reduce(
    (top, record) => Math.max(top, record.turn ?? 0),
    0,
  );
  const ctxPeak = investigation.cost.points.reduce(
    (top, point) => Math.max(top, point.context_tokens),
    0,
  );
  const costByRecord = new Map(
    investigation.cost.points.map((point) => [point.record_id, point]),
  );
  const selectedRoom = selected?.room_id
    ? layout.nodes.find((node) => node.id === selected.room_id) ?? null
    : null;

  const selectRecord = (id: string): void => {
    setSelectedId(id);
    const record = records.find((item) => item.id === id);
    if (record?.iteration !== null && record?.iteration !== undefined) {
      setOpenIteration(record.iteration);
    }
  };

  const seekIndex = (index: number): void => {
    const target = records[Math.max(0, Math.min(records.length - 1, index))];
    if (target) selectRecord(target.id);
  };

  return (
    <div
      aria-label="Sessions investigation"
      className="sessions-unified"
      role="region"
    >
      {/* ---- subbar ---- */}
      <div className="subbar">
        <h2>
          {run.label}
          <span className={run.success ? "badge b-ok" : "badge b-bad"}>
            {run.success ? "success" : run.stop_reason || "failed"}
          </span>
          {sourceState === "offline" ? (
            <span
              className="badge b-offline"
              title={`Sanitized incident capsule · integrity verified${
                incident.annotations.length > 0
                  ? ` · ${incident.annotations.length} annotations`
                  : ""
              }`}
            >
              offline capsule
            </span>
          ) : null}
        </h2>
        <div className="meters">
          <span><b>{run.iterations}</b> iterations</span>
          <span><b>{turns}</b> turns</span>
          <span>ctx peak <b>{formatK(ctxPeak)}</b></span>
          <button
            className="cost-link"
            title="click → Cost lens"
            type="button"
            onClick={() => setLens("cost")}
          >
            total <b className="cost">{usd(investigation.cost.total_usd)}</b>
          </button>
        </div>
        <div aria-label="Lens" className="switch" role="group">
          <button
            className={lens === "both" ? "on" : undefined}
            type="button"
            onClick={() => setLens("both")}
          >
            Map + Sequence
          </button>
          <button
            className={lens === "sequence" ? "on" : undefined}
            type="button"
            onClick={() => setLens("sequence")}
          >
            Sequence
          </button>
          <button
            className={lens === "cost" ? "on" : undefined}
            type="button"
            onClick={() => setLens("cost")}
          >
            Cost
          </button>
        </div>
      </div>

      {/* ---- sync banner ---- */}
      {selected ? (
        <div className="sync">
          <span className="dot" />
          <span>
            Linked selection:{" "}
            <b>
              {selected.iteration !== null ? `Iteration ${selected.iteration}` : selected.label}
              {selected.turn !== null ? ` · Turn ${selected.turn}` : ""}
              {selectedRoom ? ` · ${selectedRoom.title}` : ""}
            </b>
            : highlighted in both lenses. Pick in either; the other follows.
          </span>
        </div>
      ) : null}

      {/* ---- body ---- */}
      <div className="body">
        {lens !== "sequence" && lens !== "cost" ? (
          <div className="pane map">
            <div className="ph">
              Spatial lens · Focus
              <span className="r">
                <button className="tool on" title="Follow selection" type="button">⌖</button>
                <button className="tool" title="Zoom in" type="button">+</button>
                <button className="tool" title="Zoom out" type="button">−</button>
              </span>
            </div>
            <div className="mapwrap">
              <svg
                aria-label="Session journey map"
                className="map"
                preserveAspectRatio="xMidYMid meet"
                role="img"
                viewBox="0 0 560 460"
              >
                <defs>
                  <radialGradient cx="50%" cy="50%" id="sess-sel" r="50%">
                    <stop offset="0" stopColor="#68e1dc" stopOpacity=".45" />
                    <stop offset="1" stopColor="#68e1dc" stopOpacity="0" />
                  </radialGradient>
                </defs>
                <g fill="none" stroke="#25333f" strokeWidth="2">
                  {layout.edges.map((edge) => (
                    <path
                      d={`M${(edge.sourceNode.x + 18) * 0.62},${(edge.sourceNode.y + 18) * 0.74} L${(edge.targetNode.x + 18) * 0.62},${(edge.targetNode.y + 18) * 0.74}`}
                      key={edge.id}
                    />
                  ))}
                </g>
                <g>
                  {layout.nodes.map((node) => {
                    const x = (node.x + 18) * 0.62 - 17;
                    const y = (node.y + 18) * 0.74 - 17;
                    const isSelected = selected?.room_id === node.id;
                    const isCurrent = node.state === "current";
                    return (
                      <g
                        key={node.id}
                        style={{ cursor: "pointer" }}
                        onClick={() => {
                          const match = [...records].reverse()
                            .find((record) => record.room_id === node.id);
                          if (match) selectRecord(match.id);
                        }}
                      >
                        {isSelected ? (
                          <circle cx={x + 17} cy={y + 17} fill="url(#sess-sel)" r="30" />
                        ) : null}
                        <rect
                          fill={isSelected ? "#132a1e" : isCurrent ? "#2c2416" : "#14212e"}
                          height="34"
                          rx="8"
                          stroke={isSelected
                            ? "#68e1dc"
                            : isCurrent
                              ? "#eac06a"
                              : "#2b3947"}
                          strokeWidth={isSelected || isCurrent ? 2 : 1}
                          width="34"
                          x={x}
                          y={y}
                        />
                        <text
                          className={isSelected ? "rl sel" : isCurrent ? "rl cur" : "rl"}
                          textAnchor="middle"
                          x={x + 17}
                          y={y + 54}
                        >
                          {node.title}
                          {isCurrent ? " ★" : ""}
                        </text>
                      </g>
                    );
                  })}
                </g>
              </svg>
              <div className="maptag">
                click a room → sequence jumps to when the agent was there
              </div>
            </div>
          </div>
        ) : null}

        {lens === "cost" ? (
          <div className="pane seq">
            <div className="ph">Cost lens</div>
            <div className="workspace-note">
              The full cost investigation screen is built next (cost.html).
              Total {usd(investigation.cost.total_usd)} · raw responses{" "}
              {usd(investigation.cost.raw_response_total_usd)} ·{" "}
              {investigation.cost.complete
                ? "reconciled to ledger"
                : investigation.cost.completeness_detail}
            </div>
          </div>
        ) : (
          <div className="pane seq">
            <div className="ph">Temporal lens · Sequence</div>
            <div className="seqbody">
              {iterations.map(([iteration, items]) => {
                const open = openIteration === iteration;
                const iterationCost = items.reduce(
                  (total, record) => total + record.cost_usd,
                  0,
                );
                const mudCalls = items.filter(
                  (record) => record.source === "gateway",
                ).length;
                const durationS = items.reduce(
                  (total, record) => total + record.duration_ms,
                  0,
                ) / 1000;
                const roomHere = items.find((record) => record.room_id)?.room_id;
                const roomTitle = roomHere
                  ? layout.nodes.find((node) => node.id === roomHere)?.title
                  : undefined;
                const hasSelection = items.some(
                  (record) => record.id === selectedId,
                );
                return (
                  <div className="iter" key={iteration}>
                    <button
                      className={hasSelection ? "ihead sel" : "ihead"}
                      type="button"
                      onClick={() => setOpenIteration(open ? null : iteration)}
                    >
                      <svg
                        aria-hidden="true"
                        className="chev"
                        fill="none"
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.75"
                        viewBox="0 0 24 24"
                      >
                        {open
                          ? <path d="M6 9l6 6 6-6" />
                          : <path d="M9 6l6 6-6 6" />}
                      </svg>
                      <span className="ttl">
                        ITERATION {iteration}
                        {roomTitle && open ? ` · at ${roomTitle}` : ""}
                      </span>
                      <span className="mm">
                        <span>{durationS.toFixed(1)}s</span>
                        <span><b>{mudCalls}</b> MUD calls</span>
                        <span className="cost">{usd(iterationCost)}</span>
                      </span>
                    </button>
                    {open ? (
                      <div className="kids">
                        {items.map((record) => {
                          const cls = stepClass(record);
                          const point = costByRecord.get(record.id);
                          const isSel = record.id === selectedId;
                          return (
                            <div className={`step ${cls}`} key={record.id}>
                              <button
                                className="shead"
                                type="button"
                                onClick={() => selectRecord(record.id)}
                              >
                                <span aria-hidden="true">{isSel ? "▾" : "▸"}</span>
                                <span className={cls === "ktool" ? "lbl mono" : "lbl"}>
                                  {stepLabel(record)}
                                </span>
                                <span className="side">
                                  {cls === "kmodel" && record.cost_usd > 0
                                    ? `${usd(record.cost_usd)} · ${(record.duration_ms / 1000).toFixed(1)}s`
                                    : cls === "ktool"
                                      ? `${record.duration_ms} ms`
                                      : cls === "kplan"
                                        ? "before tool call"
                                        : record.preview.slice(0, 60)}
                                </span>
                              </button>
                              {isSel ? (
                                <div className="sbody">
                                  {cls === "kplan" ? (
                                    <div className="plan">{record.preview}</div>
                                  ) : cls === "ktool" ? (
                                    <div className="term mono">{record.preview}</div>
                                  ) : cls === "kmodel" && point ? (
                                    <div className="meterrow">
                                      <span>
                                        ctx
                                        <span className="bar">
                                          <i
                                            style={{
                                              width: ctxPeak > 0
                                                ? `${Math.min(100, (point.context_tokens / ctxPeak) * 100)}%`
                                                : 0,
                                              background: "var(--color-violet)",
                                            }}
                                          />
                                        </span>
                                        {formatK(point.context_tokens)}
                                      </span>
                                      <span>+{point.output_tokens} out</span>
                                      <span className="cost">{usd(point.cost_usd)}</span>
                                    </div>
                                  ) : (
                                    <div className="plan">{record.preview}</div>
                                  )}
                                  <div className="deep">
                                    <button type="button" onClick={onOpenSearch}>
                                      open evidence →
                                    </button>
                                  </div>
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ---- replay bar ---- */}
      <div className="replay">
        <div className="rbgroup">
          <button aria-label="Jump to start" className="rb" type="button" onClick={() => seekIndex(0)}>⏮</button>
          <button aria-label="Step back" className="rb" type="button" onClick={() => seekIndex(selectedIndex - 1)}>◀|</button>
          <button
            aria-label={playing ? "Pause replay" : "Play replay"}
            className={playing ? "rb play" : "rb"}
            type="button"
            onClick={() => setPlaying((value) => !value)}
          >
            {playing ? "⏸" : "▶"}
          </button>
          <button aria-label="Step forward" className="rb" type="button" onClick={() => seekIndex(selectedIndex + 1)}>|▶</button>
          <button aria-label="Jump to end" className="rb" type="button" onClick={() => seekIndex(records.length - 1)}>⏭</button>
        </div>
        <div
          aria-label="Replay position"
          className="scrub"
          role="slider"
          aria-valuemax={records.length}
          aria-valuemin={0}
          aria-valuenow={selectedIndex + 1}
          tabIndex={0}
          onClick={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            const ratio = (event.clientX - rect.left) / rect.width;
            seekIndex(Math.round(ratio * (records.length - 1)));
          }}
        >
          <i
            style={{
              width: records.length > 1
                ? `${((selectedIndex + 1) / records.length) * 100}%`
                : 0,
            }}
          />
          <span
            className="kn"
            style={{
              left: records.length > 1
                ? `${((selectedIndex + 1) / records.length) * 100}%`
                : 0,
            }}
          />
        </div>
        <div className="rmeta">
          iteration{" "}
          <b>{selected?.iteration ?? "—"}</b> / {run.iterations} · following
          spatial + temporal together
        </div>
        <button className="opendetail" type="button" onClick={onOpenSearch}>
          Open turn detail →
        </button>
      </div>
    </div>
  );
}
