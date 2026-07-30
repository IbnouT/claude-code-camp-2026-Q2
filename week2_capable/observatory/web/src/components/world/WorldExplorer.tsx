import {
  AlertTriangle,
  Crosshair,
  Eye,
  Focus,
  Layers3,
  Map as MapIcon,
  Route,
  ScanSearch,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  WorldNodeData,
  WorldProjectionData,
} from "../../data/worldContracts";
import {
  layoutWorld,
  visibleWorld,
  type WorldMode,
} from "./worldLayout";
import { WorldAtlas } from "./WorldAtlas";

type Props = {
  world: WorldProjectionData;
  className?: string;
  selectedNodeId: string | null;
  throughSequence?: number;
  combat?: boolean;
  eyebrow?: string;
  title?: string;
  onSelectNode: (nodeId: string) => void;
};

export function WorldExplorer({
  world,
  className,
  selectedNodeId,
  throughSequence,
  combat = false,
  eyebrow = "Spatial lens",
  title = "Living world",
  onSelectNode,
}: Props) {
  const [mode, setMode] = useState<WorldMode>("focus");
  const [scale, setScale] = useState<"journey" | "atlas">("journey");
  const [camera, setCamera] = useState<"follow" | "manual" | "fit">("follow");
  const mapScroll = useRef<HTMLDivElement>(null);
  const prefixNodes = useMemo(
    () => world.nodes.filter(
      (node) => throughSequence === undefined
        || node.first_seq <= throughSequence,
    ),
    [throughSequence, world.nodes],
  );
  const prefixIds = useMemo(
    () => new Set(prefixNodes.map((node) => node.id)),
    [prefixNodes],
  );
  const prefixEdges = useMemo(
    () => world.edges.filter(
      (edge) => prefixIds.has(edge.source) && prefixIds.has(edge.target),
    ),
    [prefixIds, world.edges],
  );
  const current = prefixNodes.find((node) => node.state === "current") ?? null;
  const anchorId = selectedNodeId ?? current?.id ?? prefixNodes.at(-1)?.id ?? null;
  const visibleNodes = useMemo(
    () => visibleWorld(prefixNodes, prefixEdges, anchorId, mode),
    [anchorId, mode, prefixEdges, prefixNodes],
  );
  const visibleIds = useMemo(
    () => new Set(visibleNodes.map((node) => node.id)),
    [visibleNodes],
  );
  const visibleEdges = useMemo(
    () => prefixEdges.filter(
      (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
    ),
    [prefixEdges, visibleIds],
  );
  const rawPoints = useMemo(
    () => layoutWorld(visibleNodes, visibleEdges),
    [visibleEdges, visibleNodes],
  );
  const rawMaxX = rawPoints.length
    ? Math.max(...rawPoints.map((point) => point.x))
    : 0;
  const rawMinX = rawPoints.length
    ? Math.min(...rawPoints.map((point) => point.x))
    : 0;
  const rawMaxY = rawPoints.length
    ? Math.max(...rawPoints.map((point) => point.y))
    : 0;
  const rawMinY = rawPoints.length
    ? Math.min(...rawPoints.map((point) => point.y))
    : 0;
  const graphWidth = rawMaxX - rawMinX;
  const graphHeight = rawMaxY - rawMinY;
  const maxX = Math.max(560, graphWidth + 150);
  const maxY = Math.max(310, graphHeight + 150);
  const offsetX = graphWidth + 150 < maxX
    ? (maxX - graphWidth) / 2 - rawMinX
    : 0;
  const offsetY = graphHeight + 150 < maxY
    ? (maxY - graphHeight) / 2 - rawMinY - 8
    : 0;
  const points = useMemo(
    () => rawPoints.map((point) => ({
      ...point,
      x: point.x + offsetX,
      y: point.y + offsetY,
    })),
    [offsetX, offsetY, rawPoints],
  );
  const byId = useMemo(
    () => new Map(points.map((point) => [point.node.id, point])),
    [points],
  );
  const selected = prefixNodes.find((node) => node.id === anchorId) ?? null;

  useEffect(() => {
    if (camera === "follow" && current !== null && selectedNodeId !== current.id) {
      onSelectNode(current.id);
    }
  }, [camera, current, onSelectNode, selectedNodeId]);

  useEffect(() => {
    const viewport = mapScroll.current;
    const point = anchorId === null ? undefined : byId.get(anchorId);
    if (viewport === null || point === undefined) return;
    const left = Math.max(0, point.x - viewport.clientWidth / 2);
    if (typeof viewport.scrollTo === "function") {
      viewport.scrollTo({ left, behavior: "instant" });
    } else {
      viewport.scrollLeft = left;
    }
  }, [anchorId, byId, camera, mode]);

  function select(node: WorldNodeData) {
    setCamera("manual");
    onSelectNode(node.id);
  }

  if (prefixNodes.length === 0) {
    return (
      <section className={`world-explorer is-empty${className ? ` ${className}` : ""}`}>
        <div className="world-explorer-heading">
          <span>
            <p className="eyebrow">{eyebrow}</p>
            <h2>{title}</h2>
          </span>
        </div>
        <div className="world-explorer-empty">
          <MapIcon size={24} aria-hidden="true" />
          <strong>No spatial evidence retained</strong>
          <span>This is a capture gap, not an empty world.</span>
        </div>
      </section>
    );
  }

  return (
    <section className={`world-explorer${className ? ` ${className}` : ""}`}>
      <div className="world-explorer-heading">
        <span>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{combat ? `${title} · combat` : title}</h2>
        </span>
        <div className="world-mode-control" role="group" aria-label="World framing">
          <ModeButton
            active={scale === "journey" && mode === "focus"}
            icon={Focus}
            label="Focus"
            onClick={() => {
              setScale("journey");
              setMode("focus");
            }}
          />
          <ModeButton
            active={scale === "journey" && mode === "grow"}
            icon={Route}
            label="Grow"
            onClick={() => {
              setScale("journey");
              setMode("grow");
            }}
          />
          <ModeButton
            active={scale === "journey" && mode === "lantern"}
            icon={ScanSearch}
            label="Lantern"
            onClick={() => {
              setScale("journey");
              setMode("lantern");
            }}
          />
          <button
            aria-pressed={scale === "atlas"}
            type="button"
            onClick={() => setScale(
              (currentScale) => currentScale === "atlas" ? "journey" : "atlas",
            )}
          >
            <Layers3 size={13} aria-hidden="true" />
            Atlas
          </button>
        </div>
      </div>

      {scale === "atlas" ? <WorldAtlas /> : (
      <>
      <div className={`world-explorer-stage is-${mode}`}>
        <div className="world-camera-control" role="group" aria-label="Map camera">
          <button
            aria-pressed={camera === "follow"}
            title="Follow current position"
            type="button"
            onClick={() => setCamera("follow")}
          >
            <Crosshair size={14} aria-hidden="true" />
            Follow
          </button>
          <button
            aria-pressed={camera === "fit"}
            title="Fit visible evidence"
            type="button"
            onClick={() => {
              setCamera("fit");
              setMode("grow");
            }}
          >
            <Eye size={14} aria-hidden="true" />
            Fit
          </button>
        </div>
        <div className="world-svg-scroll" ref={mapScroll}>
          <svg
            aria-label={`${title}, ${visibleNodes.length} of ${prefixNodes.length} places visible`}
            className="world-svg"
            role="group"
            style={{ height: maxY, width: maxX }}
            viewBox={`0 0 ${maxX} ${maxY}`}
          >
            {visibleEdges.map((edge) => {
              const start = byId.get(edge.source);
              const end = byId.get(edge.target);
              if (start === undefined || end === undefined) return null;
              return (
                <g className="world-edge" key={edge.id}>
                  <line
                    x1={start.x}
                    x2={end.x}
                    y1={start.y}
                    y2={end.y}
                  />
                  <text
                    x={(start.x + end.x) / 2}
                    y={(start.y + end.y) / 2 - 7}
                  >
                    {edge.direction}
                  </text>
                </g>
              );
            })}
            {points.map(({ node, x, y }) => {
              const active = node.id === anchorId;
              const duplicate = world.duplicate_titles.some(
                (group) => group.node_ids.includes(node.id),
              );
              const beacon = world.objective_beacons.find(
                (item) => item.node_id === node.id,
              );
              const inferred = node.state !== "candidate" && isInferred(node);
              return (
                <g
                  aria-label={`${node.title}, place ${node.place}, ${node.state}, confidence ${node.confidence}`}
                  className={`world-node is-${node.state}${inferred ? " is-inferred" : ""}${active ? " is-selected" : ""}`}
                  key={node.id}
                  role="button"
                  tabIndex={0}
                  transform={`translate(${x} ${y})`}
                  onClick={() => select(node)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      select(node);
                    }
                  }}
                >
                  {node.state === "candidate"
                    ? <rect height="36" rx="9" width="44" x="-22" y="-18" />
                    : <circle r={active ? 22 : 17} />}
                  {node.state === "current" ? (
                    <circle className="world-node-ring" r="29" />
                  ) : null}
                  {combat && node.state === "current" ? (
                    <text className="world-combat-glyph" y="-34">⚔</text>
                  ) : null}
                  {duplicate ? <text className="world-duplicate-glyph" x="18" y="-17">2×</text> : null}
                  {node.mobs.length > 0 ? (
                    <text className="world-entity-glyph is-mob" x="-29" y="-17">◆</text>
                  ) : null}
                  {node.objects.length > 0 ? (
                    <text className="world-entity-glyph is-object" x="-29" y="1">■</text>
                  ) : null}
                  <text className="world-visit-glyph" x="26" y="5">
                    {node.visits}×
                  </text>
                  {beacon !== undefined ? (
                    <>
                      <path
                        className="world-objective-beacon"
                        d="M 0 -42 L 5 -32 L 0 -35 L -5 -32 Z"
                      />
                      <text className="world-objective-label" y="-48">
                        Objective sighted
                      </text>
                    </>
                  ) : null}
                  <text className="world-node-title" y="39">
                    {shortTitle(node.title)}
                  </text>
                  <text className="world-node-meta" y="52">
                    #{node.place} · {node.confidence}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
        <div className="world-layer-legend" aria-label="World evidence layers">
          <span><i className="is-observed" />Observed</span>
          <span><i className="is-inferred" />Inferred</span>
          <span><i className="is-candidate" />Candidate</span>
          <span className={world.unknown_positions ? "has-evidence" : ""}>
            <i className="is-unknown" />Unknown
          </span>
          <button
            title="Open the isolated observer atlas"
            type="button"
            onClick={() => setScale("atlas")}
          >
            <Layers3 size={12} aria-hidden="true" />
            Truth isolated
          </button>
        </div>
      </div>

      {selected !== null ? (
        <RoomEvidence
          node={selected}
          candidate={world.candidate_details.find(
            (item) => item.node_id === selected.id,
          )}
          duplicateCount={
            world.duplicate_titles.find(
              (group) => group.node_ids.includes(selected.id),
            )?.node_ids.length ?? 1
          }
          beacon={world.objective_beacons.find(
            (item) => item.node_id === selected.id,
          )}
        />
      ) : null}

      {(world.unknown_positions > 0 || world.parse_misses.length > 0) ? (
        <div className="world-warning">
          <AlertTriangle size={15} aria-hidden="true" />
          <span>
            <strong>Spatial evidence is incomplete</strong>
            <small>
              {world.unknown_positions} unresolved positions ·{" "}
              {world.parse_misses.length} retained parse misses ·{" "}
              {(world.parse_miss_rate * 100).toFixed(1)}% cumulative miss rate
            </small>
          </span>
        </div>
      ) : null}

      <details className="world-table">
        <summary>Explore the same map as a structured list</summary>
        <div role="list">
          {prefixNodes.map((node) => (
            <div key={node.id} role="listitem">
              <button
                aria-current={node.id === anchorId ? "true" : undefined}
                type="button"
                onClick={() => select(node)}
              >
                <span>{node.title}</span>
                <small>
                  #{node.place} · {node.visits} visits · {node.exits.length} exits ·{" "}
                  {node.confidence}
                </small>
              </button>
            </div>
          ))}
        </div>
      </details>
      </>
      )}
    </section>
  );
}

function RoomEvidence({
  node,
  candidate,
  duplicateCount,
  beacon,
}: {
  node: WorldNodeData;
  candidate?: WorldProjectionData["candidate_details"][number];
  duplicateCount: number;
  beacon?: WorldProjectionData["objective_beacons"][number];
}) {
  return (
    <div className="world-room-evidence">
      <span className="world-room-symbol" aria-hidden="true">
        <MapIcon size={17} />
      </span>
      <span className="world-room-copy">
        <small>Selected spatial identity</small>
        <strong>{node.title}</strong>
        <span>
          place #{node.place} · {node.visits} visits · {node.method}
        </span>
      </span>
      <dl>
        <div>
          <dt>Exits</dt>
          <dd>{node.exits.join(", ") || "not captured"}</dd>
        </div>
        <div>
          <dt>Provenance</dt>
          <dd>{node.evidence.length} position records</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>
            Gateway position seq {node.evidence.join(", ") || "not retained"}
          </dd>
        </div>
        <div>
          <dt>Sightings</dt>
          <dd>
            {node.mobs.join(", ") || "no mobs captured"}
            {node.objects.length > 0 ? ` · ${node.objects.join(", ")}` : ""}
          </dd>
        </div>
        {duplicateCount > 1 ? (
          <div>
            <dt>Duplicate title</dt>
            <dd>{duplicateCount} distinct place identities</dd>
          </div>
        ) : null}
      </dl>
      {beacon !== undefined ? (
        <div className="world-objective-evidence">
          <Sparkles size={14} aria-hidden="true" />
          <span>
            <strong>Objective entity sighted: {beacon.label}</strong>
            <small>
              {beacon.reason} · {beacon.evidence.length} source records
            </small>
          </span>
        </div>
      ) : null}
      {candidate !== undefined ? (
        <div className="world-candidate-reason">
          <strong>Why this remains a candidate</strong>
          <p>{candidate.reason}</p>
          <span>
            supports {candidate.supporting_exits.join(", ") || "title only"}
          </span>
          <span>
            conflicts {candidate.conflicting_exits.join(", ") || "none captured"}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function ModeButton({
  active,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: typeof Focus;
  label: string;
  onClick: () => void;
}) {
  return (
    <button aria-pressed={active} type="button" onClick={onClick}>
      <Icon size={13} aria-hidden="true" />
      {label}
    </button>
  );
}

function shortTitle(value: string): string {
  return value.length > 22 ? `${value.slice(0, 21)}…` : value;
}

function isInferred(node: WorldNodeData): boolean {
  const method = node.method.toLowerCase();
  return (
    method.includes("topology")
    || method.includes("neighbourhood")
    || method.includes("inferred")
  );
}
