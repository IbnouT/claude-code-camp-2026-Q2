import {
  Boxes,
  CircleHelp,
  Focus,
  Layers3,
  Map as MapIcon,
  Network,
  Route,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { WorldNode, WorldProjection } from "../data/investigation";
import { layoutWorld } from "../data/worldLayout";
import { AtlasProbe } from "./AtlasProbe";

type Props = {
  world: WorldProjection;
};

type View = "journey" | "neighbourhood" | "atlas";

export function LivingWorld({ world }: Props) {
  const initial = world.candidates[0] ?? world.nodes.at(-1)?.id ?? null;
  const [selected, setSelected] = useState<string | null>(initial);
  const [view, setView] = useState<View>("journey");
  const [showUncertainty, setShowUncertainty] = useState(true);
  const layout = useMemo(
    () => layoutWorld(world.nodes, world.edges, selected, view === "neighbourhood"),
    [selected, view, world.edges, world.nodes],
  );
  const selectedNode = world.nodes.find((node) => node.id === selected) ?? null;
  const nodeById = new Map(layout.nodes.map((node) => [node.id, node]));
  const neighbours = selectedNode
    ? world.edges.filter(
        (edge) => edge.source === selectedNode.id || edge.target === selectedNode.id,
      )
    : [];

  if (world.nodes.length === 0) {
    return (
      <section className="living-world empty-world">
        <MapIcon size={22} aria-hidden="true" />
        <h2>Living world</h2>
        <p>No recorded position graph is available for this run.</p>
      </section>
    );
  }

  return (
    <section className="living-world" aria-labelledby="living-world-title">
      <header className="living-world-toolbar">
        <div>
          <p className="eyebrow">Spatial investigation</p>
          <h2 id="living-world-title">Living world</h2>
        </div>
        <div className="world-view-switcher" aria-label="World view">
          <button
            type="button"
            className={view === "journey" ? "is-active" : ""}
            onClick={() => setView("journey")}
          >
            <Route size={13} aria-hidden="true" /> Journey
          </button>
          <button
            type="button"
            className={view === "neighbourhood" ? "is-active" : ""}
            onClick={() => setView("neighbourhood")}
            disabled={selected === null}
          >
            <Focus size={13} aria-hidden="true" /> Neighbourhood
          </button>
          <button
            type="button"
            className={view === "atlas" ? "is-active" : ""}
            onClick={() => setView("atlas")}
          >
            <Boxes size={13} aria-hidden="true" /> Capacity
          </button>
        </div>
      </header>

      <div className="world-layer-bar">
        <span><Layers3 size={13} aria-hidden="true" /> Evidence layers</span>
        <button type="button" disabled title="Agent belief positions are not recorded">
          Belief <small>missing</small>
        </button>
        <button type="button" className="is-active">
          Inference <small>{world.nodes.length}</small>
        </button>
        <button type="button" disabled title="Observer truth is not configured">
          Truth <small>missing</small>
        </button>
        <button
          type="button"
          className={showUncertainty ? "uncertainty-toggle is-active" : "uncertainty-toggle"}
          onClick={() => setShowUncertainty((value) => !value)}
        >
          <CircleHelp size={12} aria-hidden="true" /> Uncertainty
        </button>
      </div>

      {view === "atlas" ? (
        <AtlasProbe />
      ) : (
        <div className="living-world-body">
          <div className="evidence-map">
            <div className="world-metrics" aria-label="World evidence quality">
              <span>{world.nodes.length} distinct places</span>
              <span>{world.edges.length} observed transitions</span>
              <span className={world.parse_miss_rate > 0.05 ? "is-warning" : ""}>
                {(world.parse_miss_rate * 100).toFixed(1)}% parse miss
              </span>
              <span>{world.unknown_positions} unresolved positions</span>
            </div>
            <div className="world-scroll">
              <svg
                className="evidence-world-graph"
                viewBox={`0 0 ${layout.width} ${layout.height}`}
                role="img"
                aria-label="Evidence-backed journey graph"
              >
                <defs>
                  <marker
                    id="world-arrow"
                    viewBox="0 0 10 10"
                    refX="8"
                    refY="5"
                    markerWidth="5"
                    markerHeight="5"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" />
                  </marker>
                </defs>
                {layout.edges.map((edge) => {
                  const source = nodeById.get(edge.source);
                  const target = nodeById.get(edge.target);
                  if (!source || !target) return null;
                  const middleX = (source.x + target.x) / 2;
                  const middleY = (source.y + target.y) / 2;
                  return (
                    <g key={edge.id} className="evidence-edge">
                      <line
                        x1={source.x}
                        y1={source.y}
                        x2={target.x}
                        y2={target.y}
                        markerEnd="url(#world-arrow)"
                        style={{ strokeWidth: Math.min(5, 1.2 + edge.traversals * 0.35) }}
                      />
                      <text x={middleX} y={middleY - 7}>
                        {edge.direction} · {edge.traversals}×
                      </text>
                    </g>
                  );
                })}
                {layout.nodes.map((node) => (
                  <g
                    key={node.id}
                    role="button"
                    tabIndex={0}
                    aria-label={`${node.title}, place ${node.place}, ${node.state}`}
                    className={[
                      "evidence-node",
                      `is-${node.state}`,
                      selected === node.id ? "is-selected" : "",
                      showUncertainty ? "" : "hide-uncertainty",
                    ].join(" ")}
                    transform={`translate(${node.x} ${node.y})`}
                    onClick={() => setSelected(node.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelected(node.id);
                      }
                    }}
                  >
                    <circle r={node.state === "candidate" ? 23 : 18} />
                    {node.state === "candidate" && <circle className="candidate-ring" r={30} />}
                    <text className="node-title" x="0" y="41">{node.title}</text>
                    <text className="node-id" x="0" y="54">place {node.place}</text>
                  </g>
                ))}
              </svg>
            </div>
          </div>

          <aside className="world-inspector">
            {selectedNode ? (
              <>
                <p className="eyebrow">Selected place identity</p>
                <h3>{selectedNode.title}</h3>
                <span className={`world-state-chip is-${selectedNode.state}`}>
                  {selectedNode.state}
                </span>
                <dl>
                  <div><dt>Place ID</dt><dd>{selectedNode.place}</dd></div>
                  <div><dt>Visits</dt><dd>{selectedNode.visits}</dd></div>
                  <div><dt>Confidence</dt><dd>{selectedNode.confidence}</dd></div>
                  <div><dt>Method</dt><dd>{selectedNode.method}</dd></div>
                  <div>
                    <dt>Observed exits</dt>
                    <dd>{selectedNode.exits.join(", ") || "not parsed"}</dd>
                  </div>
                  <div>
                    <dt>Evidence range</dt>
                    <dd>{selectedNode.first_seq} → {selectedNode.last_seq}</dd>
                  </div>
                </dl>
                <div className="candidate-explanation">
                  <Network size={14} aria-hidden="true" />
                  <div>
                    <strong>
                      {selectedNode.state === "candidate"
                        ? "Why this remains a candidate"
                        : "Neighbourhood evidence"}
                    </strong>
                    <p>
                      Title identity is insufficient. This place remains
                      separate through place ID, observed exits, and
                      {` ${neighbours.length} recorded neighbourhood link${neighbours.length === 1 ? "" : "s"}.`}
                    </p>
                  </div>
                </div>
              </>
            ) : (
              <p>Select a place to inspect its evidence.</p>
            )}
            {world.candidates.length > 1 && (
              <div className="candidate-set">
                <p className="eyebrow">Unresolved candidate set</p>
                {world.candidates.map((candidate) => {
                  const node = world.nodes.find((item) => item.id === candidate);
                  return node ? (
                    <button
                      key={candidate}
                      type="button"
                      className={selected === candidate ? "is-active" : ""}
                      onClick={() => setSelected(candidate)}
                    >
                      <span>{node.title}</span>
                      <small>place {node.place} · {node.exits.join(" / ")}</small>
                    </button>
                  ) : null;
                })}
              </div>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
