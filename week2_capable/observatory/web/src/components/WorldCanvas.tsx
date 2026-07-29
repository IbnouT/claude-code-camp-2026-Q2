import { Crosshair, Layers3, LocateFixed } from "lucide-react";
import { edges, rooms } from "../app/demo";

export function WorldCanvas() {
  const byId = new Map(rooms.map((room) => [room.id, room]));

  return (
    <section className="world-panel" aria-labelledby="world-title">
      <header className="panel-heading">
        <div>
          <p className="eyebrow">Spatial evidence</p>
          <h2 id="world-title">Living world</h2>
        </div>
        <div className="panel-tools">
          <button className="icon-button" type="button" aria-label="Center current position">
            <LocateFixed size={16} aria-hidden="true" />
          </button>
          <button className="layer-button" type="button">
            <Layers3 size={15} aria-hidden="true" />
            Belief + inference
          </button>
        </div>
      </header>

      <div className="world-stage">
        <div className="map-status">
          <span className="status-orbit" aria-hidden="true" />
          Position unresolved
          <strong>2 candidates</strong>
        </div>
        <svg
          className="world-graph"
          viewBox="0 0 980 500"
          role="img"
          aria-label="Journey map ending at two ambiguous Newbie Zone entrances"
        >
          <defs>
            <pattern id="candidate-pattern" width="8" height="8" patternUnits="userSpaceOnUse">
              <path d="M0 8L8 0" stroke="currentColor" strokeOpacity=".18" />
            </pattern>
          </defs>
          <g className="map-edges">
            {edges.map((edge) => {
              const from = byId.get(edge.from)!;
              const to = byId.get(edge.to)!;
              return (
                <g key={`${edge.from}-${edge.to}`}>
                  <line
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    className={edge.traversals > 8 ? "edge is-loop" : "edge"}
                  />
                  {edge.traversals > 1 && (
                    <text
                      x={(from.x + to.x) / 2}
                      y={(from.y + to.y) / 2 - 9}
                      className="edge-count"
                    >
                      ×{edge.traversals}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
          <g className="map-rooms">
            {rooms.map((room) => (
              <g
                key={room.id}
                className={`room-node room-${room.state}`}
                transform={`translate(${room.x} ${room.y})`}
              >
                {room.state === "candidate" && (
                  <circle r="31" className="candidate-orbit" />
                )}
                <circle r={room.state === "frontier" ? 8 : 17} className="room-disc" />
                {room.state === "current" && (
                  <Crosshair x={-9} y={-9} size={18} aria-hidden="true" />
                )}
                <text y={room.state === "frontier" ? 27 : 36} textAnchor="middle">
                  {room.title}
                </text>
                {room.confidence !== undefined && (
                  <text y="-38" textAnchor="middle" className="confidence-label">
                    {Math.round(room.confidence * 100)}% candidate
                  </text>
                )}
              </g>
            ))}
          </g>
        </svg>
        <div className="map-legend" aria-label="Map legend">
          <span><i className="legend-dot visited" />Observed</span>
          <span><i className="legend-dot candidate" />Candidate</span>
          <span><i className="legend-dot frontier" />Frontier</span>
          <span><i className="legend-line loop" />Repeated path</span>
        </div>
      </div>
    </section>
  );
}
