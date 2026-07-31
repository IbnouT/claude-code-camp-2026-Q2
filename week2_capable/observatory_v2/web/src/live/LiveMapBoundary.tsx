import type { KeyboardEvent } from "react";
import {
  mapRoomHeight,
  mapRoomWidth,
  type MapPoint,
} from "./mapModel";
import type { FocusBoundary } from "./mapPresentation";

type Props = {
  boundary: FocusBoundary;
  currentPoint: MapPoint;
  point: MapPoint;
  roomTitle: string;
  onToggle: (roomId: string) => void;
};

const expanderDistance = mapRoomWidth / 2 + 26;

export function LiveMapBoundary({
  boundary,
  currentPoint,
  point,
  roomTitle,
  onToggle,
}: Props) {
  const roomCenter = {
    x: point.x + mapRoomWidth / 2,
    y: point.y + mapRoomHeight / 2,
  };
  const currentCenter = {
    x: currentPoint.x + mapRoomWidth / 2,
    y: currentPoint.y + mapRoomHeight / 2,
  };
  const angle = Math.atan2(
    roomCenter.y - currentCenter.y,
    roomCenter.x - currentCenter.x,
  );
  const rawDirection = {
    x: Math.cos(angle),
    y: Math.sin(angle),
  };
  const direction = rawDirection.y > 0.25
    ? {
      x: rawDirection.x < 0 ? -1 : 1,
      y: 0,
    }
    : rawDirection;
  const target = {
    x: roomCenter.x + direction.x * expanderDistance,
    y: roomCenter.y + direction.y * expanderDistance,
  };
  const label = boundary.expanded
    ? `Collapse rooms beyond ${roomTitle}`
    : `Show ${boundary.count} hidden rooms beyond ${roomTitle}`;
  const activate = () => onToggle(boundary.roomId);
  const handleKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    activate();
  };

  return (
    <g
      aria-label={label}
      className={[
        "live-map-boundary",
        boundary.expanded ? "is-expanded" : "",
      ].filter(Boolean).join(" ")}
      data-room-id={boundary.roomId}
      role="button"
      tabIndex={0}
      onClick={activate}
      onKeyDown={handleKeyDown}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <path
        d={`M${roomCenter.x},${roomCenter.y} L${target.x},${target.y}`}
      />
      <circle cx={target.x} cy={target.y} r="13" />
      <text x={target.x} y={target.y + 3.5}>
        {boundary.expanded ? "−" : `+${boundary.count}`}
      </text>
    </g>
  );
}
