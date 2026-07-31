import {
  memo,
  useRef,
} from "react";
import type { KeyboardEvent } from "react";
import type { WorldNode } from "../contracts";
import {
  mapRoomHeight,
  mapRoomWidth,
  type MapPoint,
} from "./mapModel";

type Props = {
  node: WorldNode;
  point: MapPoint;
  current: boolean;
  selected: boolean;
  combat: boolean;
  beacon: boolean;
  onSelect: (nodeId: string) => void;
};

export const LiveMapRoom = memo(function LiveMapRoom({
  node,
  point,
  current,
  selected,
  combat,
  beacon,
  onSelect,
}: Props) {
  const renderCount = useRef(0);
  renderCount.current += 1;
  const identityLabel = node.atlas === null || node.atlas === undefined
    ? `${node.title}, observed place ${node.place}`
    : (
      `${node.title}, atlas-correlated vnum ${node.atlas.vnum}, `
      + `${node.atlas.confidence} confidence`
    );
  const stateClass = roomStateClass({
    combat,
    current,
    selected,
    beacon,
  });
  const select = () => onSelect(node.id);
  const handleKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    select();
  };

  return (
    <g
      className={[
        "live-map-room",
        sectorClass(node.atlas?.sector),
        node.state === "candidate" ? "is-candidate" : "",
        stateClass,
        selected ? "is-selected" : "",
      ].filter(Boolean).join(" ")}
      data-room-id={node.id}
      data-render-count={import.meta.env.MODE === "test"
        ? renderCount.current
        : undefined}
      transform={`translate(${point.x} ${point.y})`}
      aria-label={current ? `Agent in ${identityLabel}` : identityLabel}
      aria-pressed={selected}
      role="button"
      tabIndex={0}
      onClick={select}
      onKeyDown={handleKeyDown}
    >
      <title>{identityLabel}</title>
      {current ? (
        <circle
          className="live-current-room-glow"
          cx={mapRoomWidth / 2}
          cy={mapRoomHeight / 2}
          r="48"
        />
      ) : null}
      {selected ? (
        <circle
          className="live-selected-room-ring"
          cx={mapRoomWidth / 2}
          cy={mapRoomHeight / 2}
          r={Math.hypot(mapRoomWidth, mapRoomHeight) / 2 + 2}
        />
      ) : null}
      <rect width={mapRoomWidth} height={mapRoomHeight} rx="10" />
      <text
        className="live-map-room-debug-id"
        x={mapRoomWidth / 2}
        y={mapRoomHeight / 2 + 4}
      >
        {node.atlas === null || node.atlas === undefined
          ? `p${node.place}`
          : `#${node.atlas.vnum}`}
      </text>
      <text
        className="live-map-room-title"
        x={mapRoomWidth / 2}
        y={current ? -14 : mapRoomHeight + 18}
      >
        {truncate(node.title, 18)}
      </text>
    </g>
  );
}, sameRoomRender);

export function roomStateClass({
  combat,
  current,
  selected,
  beacon,
}: {
  combat: boolean;
  current: boolean;
  selected: boolean;
  beacon: boolean;
}): string {
  if (combat && current) return "is-combat";
  if (current) return "is-current";
  if (selected) return "is-selected";
  if (beacon) return "is-beacon";
  return "";
}

export function sectorClass(sector: string | undefined): string {
  const normalized = sector?.trim().toLowerCase() ?? "unknown";
  if (normalized === "inside") return "is-sector-inside";
  if (normalized === "field") return "is-sector-field";
  if (normalized === "forest") return "is-sector-forest";
  if (normalized === "hills") return "is-sector-hills";
  if (normalized === "mountain") return "is-sector-mountain";
  if (normalized === "water") return "is-sector-semantic-water";
  if (
    normalized.startsWith("water")
    || normalized === "flying"
    || normalized === "underwater"
  ) {
    return "is-sector-water";
  }
  if (normalized === "city") return "is-sector-city";
  if (normalized === "interior") return "is-sector-interior";
  if (normalized === "open land" || normalized === "open-land") {
    return "is-sector-open-land";
  }
  if (normalized === "woodland") return "is-sector-woodland";
  if (normalized === "highland") return "is-sector-highland";
  if (normalized === "urban") return "is-sector-urban";
  if (normalized === "special") return "is-sector-special";
  if (normalized === "route") return "is-sector-route";
  if (normalized === "underground") return "is-sector-underground";
  if (normalized === "commerce") return "is-sector-commerce";
  if (normalized === "civic") return "is-sector-civic";
  if (normalized === "sacred") return "is-sector-sacred";
  return "is-sector-neutral";
}

function sameRoomRender(previous: Props, next: Props): boolean {
  return previous.node.id === next.node.id
    && previous.node.title === next.node.title
    && previous.node.place === next.node.place
    && previous.node.state === next.node.state
    && previous.node.atlas?.vnum === next.node.atlas?.vnum
    && previous.node.atlas?.confidence === next.node.atlas?.confidence
    && previous.node.atlas?.sector === next.node.atlas?.sector
    && previous.point.x === next.point.x
    && previous.point.y === next.point.y
    && previous.current === next.current
    && previous.selected === next.selected
    && previous.combat === next.combat
    && previous.beacon === next.beacon
    && previous.onSelect === next.onSelect;
}

function truncate(value: string, maximum: number): string {
  return value.length > maximum
    ? `${value.slice(0, maximum - 1)}…`
    : value;
}
