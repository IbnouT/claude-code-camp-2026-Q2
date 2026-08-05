import { memo } from "react";
import type { FrontierMarker } from "./markerProjection";

type Props = {
  marker: FrontierMarker;
};

export const LiveMapFrontier = memo(function LiveMapFrontier({
  marker,
}: Props) {
  return (
    <g
      className="live-map-frontier"
      data-direction={marker.direction}
      data-source={marker.source}
    >
      <path
        d={[
          `M ${marker.start.x} ${marker.start.y}`,
          `L ${marker.end.x} ${marker.end.y}`,
        ].join(" ")}
      />
      <circle cx={marker.end.x} cy={marker.end.y} r="2.5" />
    </g>
  );
});
