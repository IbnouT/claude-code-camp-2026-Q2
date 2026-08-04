import { memo } from "react"

import type { FrontierMarker } from "./markerProjection"

type MapFrontierProps = {
  marker: FrontierMarker
}

/**
 * One unexplored exit: a short dashed stub from the room edge, ending in
 * a dot.
 */
const MapFrontier = memo(function MapFrontier({ marker }: MapFrontierProps) {
  return (
    <g
      className="pointer-events-none text-(--map-frontier)"
      data-direction={marker.direction}
      data-source={marker.source}
    >
      <path
        className="fill-none stroke-current stroke-2 [stroke-dasharray:3_4]"
        d={[
          `M ${marker.start.x} ${marker.start.y}`,
          `L ${marker.end.x} ${marker.end.y}`,
        ].join(" ")}
        vectorEffect="non-scaling-stroke"
      />
      <circle
        className="fill-current"
        cx={marker.end.x}
        cy={marker.end.y}
        r="2.5"
      />
    </g>
  )
})

export { MapFrontier, type MapFrontierProps }
