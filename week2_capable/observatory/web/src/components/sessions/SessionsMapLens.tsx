import {
  Crosshair,
  Map as MapIcon,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { RecordedSessionInvestigation } from "../../data/recordedSession";
import { positionSessionNodes } from "./sessionsUnifiedModel";

type Props = {
  investigation: RecordedSessionInvestigation;
  selectedRoomId: string | null;
  onSelectRoom: (roomId: string) => void;
};

export function SessionsMapLens({
  investigation,
  selectedRoomId,
  onSelectRoom,
}: Props) {
  const nodes = positionSessionNodes(investigation, selectedRoomId);

  return (
    <section className="sessions-unified-pane is-map">
      <div className="sessions-unified-pane-header">
        <MapIcon size={14} aria-hidden="true" />
        Spatial lens · Focus
        <div>
          <button aria-label="Follow selected room" className="is-active" type="button">
            <Crosshair size={13} aria-hidden="true" />
          </button>
          <button aria-label="Zoom in" type="button">
            <ZoomIn size={13} aria-hidden="true" />
          </button>
          <button aria-label="Zoom out" type="button">
            <ZoomOut size={13} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="sessions-unified-map">
        {nodes.length === 0 ? (
          <div className="sessions-unified-map-gap">
            <MapIcon size={23} aria-hidden="true" />
            <b>No spatial evidence retained</b>
            <span>This is a capture gap, not an empty world.</span>
          </div>
        ) : (
          <svg
            aria-label={`Spatial evidence, ${nodes.length} retained places`}
            role="img"
            viewBox="0 0 560 460"
            preserveAspectRatio="xMidYMid meet"
          >
            <defs>
              <radialGradient id="sessions-selected-room" cx="50%" cy="50%" r="50%">
                <stop offset="0" stopColor="var(--color-cyan)" stopOpacity=".45" />
                <stop offset="1" stopColor="var(--color-cyan)" stopOpacity="0" />
              </radialGradient>
            </defs>
            <g className="sessions-unified-map-edges">
              {investigation.world.edges.map((edge) => {
                const start = nodes.find((node) => node.id === edge.source);
                const end = nodes.find((node) => node.id === edge.target);
                return start && end ? (
                  <line
                    key={edge.id}
                    x1={start.x}
                    x2={end.x}
                    y1={start.y}
                    y2={end.y}
                  />
                ) : null;
              })}
            </g>
            {nodes.map((node) => (
              <g
                className={[
                  "sessions-unified-map-node",
                  node.selected ? "is-selected" : "",
                  node.current ? "is-current" : "",
                  node.candidate ? "is-candidate" : "",
                ].filter(Boolean).join(" ")}
                key={node.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelectRoom(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectRoom(node.id);
                  }
                }}
              >
                {node.selected ? (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    fill="url(#sessions-selected-room)"
                    r="32"
                  />
                ) : null}
                <rect x={node.x - 17} y={node.y - 17} width="34" height="34" rx="8" />
                <text x={node.x} y={node.y + 38} textAnchor="middle">
                  {node.title}{node.current ? " ★" : ""}
                </text>
              </g>
            ))}
          </svg>
        )}
        <div className="sessions-unified-map-tag">
          click a room → sequence jumps to when the agent was there
        </div>
      </div>
    </section>
  );
}
