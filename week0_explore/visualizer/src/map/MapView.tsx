import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { select } from "d3-selection";
import { zoom, zoomIdentity, ZoomBehavior, zoomTransform } from "d3-zoom";
import { easeCubicOut } from "d3-ease";
import "d3-transition";
import type { StateC } from "../state";
import { DIR_VEC, layoutMap } from "./layout";
import { ACTIVITY_META } from "../overlays";

const CELL_W = 148;
const CELL_H = 108;
const BOX_W = 104;
const BOX_H = 62;

const px = (gx: number) => gx * CELL_W;
const py = (gy: number) => gy * CELL_H;

interface Tip {
  key: string;
  x: number;
  y: number;
}

export default function MapView({ state }: { state: StateC }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const camRef = useRef<SVGGElement>(null);
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const [follow, setFollow] = useState(true);
  const [tip, setTip] = useState<Tip | null>(null);

  const { pos, bent } = useMemo(
    () => layoutMap(state.rooms, state.links),
    [state.rooms, state.links],
  );

  const hasLink = useMemo(() => {
    const s = new Set<string>();
    for (const l of state.links) s.add(`${l.from}|${l.dir}`);
    return s;
  }, [state.links]);

  // camera: d3-zoom owns the transform of the inner group
  useEffect(() => {
    const svg = svgRef.current!;
    const z = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 2.5])
      .on("zoom", (e) => {
        camRef.current?.setAttribute("transform", e.transform.toString());
      })
      .on("start", (e) => {
        if (e.sourceEvent) setFollow(false); // manual pan/zoom breaks follow
      });
    zoomRef.current = z;
    select(svg).call(z).on("dblclick.zoom", null);
    return () => {
      select(svg).on(".zoom", null);
    };
  }, []);

  // glide to keep the agent centered
  useEffect(() => {
    const svg = svgRef.current;
    const z = zoomRef.current;
    if (!svg || !z || !follow || !state.position) return;
    const p = pos.get(state.position);
    if (!p) return;
    const { width, height } = svg.getBoundingClientRect();
    const k = Math.max(0.6, zoomTransform(svg).k);
    const t = zoomIdentity
      .translate(width / 2 - px(p.x) * k, height / 2 - py(p.y) * k)
      .scale(k);
    select(svg)
      .transition()
      .duration(800)
      .ease(easeCubicOut)
      .call(z.transform, t);
  }, [state.position, pos, follow]);

  const rooms = Object.entries(state.rooms);

  return (
    <div className="relative h-full w-full map-plane">
      <svg ref={svgRef} className="h-full w-full cursor-grab active:cursor-grabbing">
        <g ref={camRef}>
          {/* links under everything */}
          {state.links.map((l, i) => {
            const a = pos.get(l.from);
            const b = pos.get(l.to);
            if (!a || !b) return null;
            const ax = px(a.x), ay = py(a.y), bx = px(b.x), by = py(b.y);
            const v = DIR_VEC[l.dir] ?? [0, 0];
            const d = bent.has(i)
              ? `M ${ax} ${ay} Q ${ax + v[0] * CELL_W * 0.9} ${ay + v[1] * CELL_H * 0.9} ${bx} ${by}`
              : `M ${ax} ${ay} L ${bx} ${by}`;
            const len = Math.hypot(bx - ax, by - ay) * (bent.has(i) ? 1.3 : 1);
            return (
              <path
                key={`${l.from}|${l.dir}|${l.to}`}
                d={d}
                fill="none"
                stroke="#383835"
                strokeWidth={2}
                strokeDasharray={l.ghost ? "4 5" : undefined}
                opacity={l.ghost ? 0.65 : 1}
                className={l.ghost ? undefined : "link-draw"}
                style={{ "--len": len } as React.CSSProperties}
              />
            );
          })}

          {/* fading trail of recent moves */}
          {state.trail.map((t, i) => {
            const a = pos.get(t.from);
            const b = pos.get(t.to);
            if (!a || !b) return null;
            return (
              <line
                key={`trail-${i}`}
                x1={px(a.x)} y1={py(a.y)} x2={px(b.x)} y2={py(b.y)}
                stroke="var(--accent)"
                strokeWidth={4}
                strokeLinecap="round"
                opacity={0.06 + 0.4 * ((i + 1) / state.trail.length)}
                pointerEvents="none"
              />
            );
          })}

          {/* frontier stubs — untried exits, breathing */}
          {rooms.map(([key, r]) => {
            const p = pos.get(key);
            if (!p) return null;
            return r.exits
              .filter((e) => !hasLink.has(`${key}|${e}`))
              .map((e) => {
                const v = DIR_VEC[e];
                if (!v) return null; // up/down handled on the box
                const sx = px(p.x) + v[0] * (BOX_W / 2 + 2);
                const sy = py(p.y) + v[1] * (BOX_H / 2 + 2);
                const ex = px(p.x) + v[0] * (BOX_W / 2 + 26);
                const ey = py(p.y) + v[1] * (BOX_H / 2 + 26);
                return (
                  <g key={`${key}-stub-${e}`} className="frontier-stub" pointerEvents="none">
                    <line x1={sx} y1={sy} x2={ex} y2={ey}
                      stroke="var(--ink-3)" strokeWidth={2} strokeDasharray="3 4" />
                    <circle cx={ex} cy={ey} r={2.5} fill="var(--ink-3)" />
                  </g>
                );
              });
          })}

          {/* rooms */}
          {rooms.map(([key, r]) => {
            const p = pos.get(key);
            if (!p) return null;
            const isCur = key === state.position;
            const death = r.flags.includes("death");
            const hazard = r.flags.includes("hazard") || death;
            const dark = r.flags.includes("dark");
            const ghost = r.flags.includes("ghost");
            const glow = isCur ? "room-glow" : death ? "death-glow" : hazard ? "hazard-glow" : "";
            return (
              <motion.g
                key={key}
                initial={{ opacity: 0, scale: 0.4 }}
                animate={{ opacity: 1, scale: 1, x: px(p.x), y: py(p.y) }}
                transition={{ type: "spring", stiffness: 260, damping: 24 }}
                className={glow}
                onMouseEnter={(e) => setTip({ key, x: e.clientX, y: e.clientY })}
                onMouseMove={(e) => setTip({ key, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setTip(null)}
              >
                <rect
                  x={-BOX_W / 2} y={-BOX_H / 2} width={BOX_W} height={BOX_H}
                  rx={8}
                  fill={isCur ? "#20304a" : ghost ? "transparent" : "var(--surface)"}
                  stroke={isCur ? "var(--accent)" : death ? "var(--critical)" : hazard ? "var(--warning)" : ghost ? "var(--ink-3)" : "var(--hairline)"}
                  strokeWidth={isCur ? 2 : 1}
                  strokeDasharray={ghost ? "5 4" : undefined}
                  opacity={ghost ? 0.7 : 1}
                />
                {dark ? (
                  <text x={0} y={7} textAnchor="middle" fontSize={22} fill="var(--ink-3)">?</text>
                ) : (
                  wrapTitle(r.title).map((line, i, arr) => (
                    <text
                      key={i}
                      x={0}
                      y={(i - (arr.length - 1) / 2) * 13 + 4}
                      textAnchor="middle"
                      fontSize={10.5}
                      fontStyle={ghost ? "italic" : undefined}
                      fill={isCur ? "var(--ink)" : ghost ? "var(--ink-3)" : "var(--ink-2)"}
                    >
                      {line}
                    </text>
                  ))
                )}
                {hazard && (
                  <text x={BOX_W / 2 - 12} y={-BOX_H / 2 + 14} fontSize={11}
                    fill={death ? "var(--critical)" : "var(--warning)"}>⚠</text>
                )}
                {r.exits.includes("up") && (
                  <text x={BOX_W / 2 - 13} y={BOX_H / 2 - 6} fontSize={9} fill="var(--ink-3)">▲</text>
                )}
                {r.exits.includes("down") && (
                  <text x={BOX_W / 2 - 24} y={BOX_H / 2 - 6} fontSize={9} fill="var(--ink-3)">▼</text>
                )}
                {isCur && (
                  <circle className="agent-dot" cx={-BOX_W / 2 + 13} cy={-BOX_H / 2 + 13}
                    r={4.5} fill="var(--accent)" />
                )}
              </motion.g>
            );
          })}

          {/* activity badge + thought bubble follow the agent */}
          {state.position && pos.get(state.position) && (
            <AgentCallout
              x={px(pos.get(state.position)!.x)}
              y={py(pos.get(state.position)!.y)}
              state={state}
            />
          )}
        </g>
      </svg>

      {/* position-unknown banner */}
      {state.position === null && Object.keys(state.rooms).length > 0 && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 rounded-md border border-[var(--warning)]/40 bg-[var(--surface)] px-4 py-1.5 text-sm text-[var(--warning)]">
          ⚠ position unknown — the agent is in darkness
        </div>
      )}

      {/* camera controls */}
      <div className="absolute bottom-4 left-4 flex gap-1.5">
        <CamBtn label="+" onClick={() => zoomBy(svgRef.current, zoomRef.current, 1.35)} />
        <CamBtn label="−" onClick={() => zoomBy(svgRef.current, zoomRef.current, 1 / 1.35)} />
        <CamBtn
          label="⌖ follow"
          active={follow}
          onClick={() => setFollow((f) => !f)}
        />
      </div>

      {/* hover tooltip */}
      {tip && state.rooms[tip.key] && (
        <div
          className="pointer-events-none absolute z-10 max-w-64 rounded-md border border-[var(--hairline)] bg-[var(--surface-2)] px-3 py-2 text-xs shadow-xl"
          style={{ left: tip.x + 14, top: tip.y + 10 }}
        >
          <div className="font-medium text-[var(--ink)]">{state.rooms[tip.key].title}</div>
          <div className="mt-0.5 text-[var(--ink-3)]">
            exits: {state.rooms[tip.key].exits.join(", ") || "none"}
          </div>
          {state.rooms[tip.key].hazards.map((h, i) => (
            <div key={i} className="mt-0.5 text-[var(--warning)]">⚠ {h}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function AgentCallout({ x, y, state }: { x: number; y: number; state: StateC }) {
  const act = state.activity;
  const meta = act ? ACTIVITY_META[act.kind] : null;
  // an old thought is history, not intention — drop the bubble after 5 min
  const thought = (state.thought_age_s ?? 0) <= 300 ? state.thought : "";
  const tLines = thought ? wrapTitle(thought, 34) : [];
  const bubbleW = thought ? Math.min(250, Math.max(...tLines.map((l) => l.length)) * 6.4 + 24) : 0;
  const bubbleH = tLines.length * 14 + 16;
  return (
    <g pointerEvents="none">
      {/* activity badge below the room */}
      {act && meta && act.kind !== "idle" && (
        <motion.g
          key={act.kind + act.detail}
          initial={{ opacity: 0, y: y + BOX_H / 2 - 4 }}
          animate={{ opacity: 1, y: y + BOX_H / 2 + 8 }}
          transition={{ duration: 0.35 }}
        >
          <rect
            x={x - (act.detail.length * 6 + 30) / 2}
            y={0}
            width={act.detail.length * 6 + 30}
            height={20}
            rx={10}
            fill="var(--surface-2)"
            stroke={meta.color}
            strokeOpacity={0.55}
          />
          <text x={x} y={14} textAnchor="middle" fontSize={11} fill={meta.color}>
            {meta.icon} {act.detail}
          </text>
        </motion.g>
      )}
      {/* thought bubble above the room */}
      {thought && (
        <motion.g
          key={thought}
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 22 }}
        >
          <path
            d={`M ${x - 6} ${y - BOX_H / 2 - 12} l 6 10 l 6 -10 z`}
            fill="var(--surface-2)"
          />
          <rect
            x={x - bubbleW / 2}
            y={y - BOX_H / 2 - 12 - bubbleH}
            width={bubbleW}
            height={bubbleH}
            rx={9}
            fill="var(--surface-2)"
            stroke="var(--accent)"
            strokeOpacity={0.45}
          />
          {tLines.map((l, i) => (
            <text
              key={i}
              x={x}
              y={y - BOX_H / 2 - 12 - bubbleH + 20 + i * 14 - 6}
              textAnchor="middle"
              fontSize={10.5}
              fontStyle="italic"
              fill="var(--ink-2)"
            >
              {l}
            </text>
          ))}
        </motion.g>
      )}
    </g>
  );
}

function CamBtn({ label, onClick, active }: { label: string; onClick: () => void; active?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
        active
          ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)]"
          : "border-[var(--hairline)] bg-[var(--surface)] text-[var(--ink-2)] hover:bg-[var(--surface-2)]"
      }`}
    >
      {label}
    </button>
  );
}

function zoomBy(
  svg: SVGSVGElement | null,
  z: ZoomBehavior<SVGSVGElement, unknown> | null,
  factor: number,
) {
  if (!svg || !z) return;
  select(svg).transition().duration(250).call(z.scaleBy, factor);
}

function wrapTitle(title: string, max = 17): string[] {
  const words = title.split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > max && cur) {
      lines.push(cur);
      cur = w;
    } else {
      cur = (cur + " " + w).trim();
    }
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 3);
}
