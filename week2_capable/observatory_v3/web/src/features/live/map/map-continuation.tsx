import { memo, type CSSProperties } from "react"
import { ChevronsRightIcon } from "lucide-react"

import { cn } from "@/lib/utils"

import type { MapFrame, MapSafeInsets } from "./mapCamera"
import type { MapViewport } from "./mapModel"
import {
  projectFocusContinuationOverlay,
  type FocusContinuation,
  type FocusContinuationEdge,
} from "./focusContinuation"
import type { MapOverlayRect } from "./mapPresentation"
import type { MapRoomFootprint } from "./mapRoomFootprint"

type MapContinuationProps = {
  frame: MapFrame
  marker: FocusContinuation
  overlayRects: readonly MapOverlayRect[]
  safeInsets: MapSafeInsets
  viewport: MapViewport
  visibleRoomFootprints: readonly MapRoomFootprint[]
}

const edgeLabels = {
  top: "north",
  right: "east",
  bottom: "south",
  left: "west",
} as const

const chevronClass: Record<FocusContinuationEdge, string> = {
  top: "absolute top-0 left-[3px] -rotate-90",
  right: "absolute top-[3px] right-0",
  bottom: "absolute bottom-0 left-[3px] rotate-90",
  left: "absolute top-[3px] left-0 rotate-180",
}

const fadeClass: Record<FocusContinuationEdge, string> = {
  top: "absolute top-[18px] left-[10px] h-8 w-1 bg-[linear-gradient(to_bottom,rgb(185_156_255/34%),transparent)]",
  right:
    "absolute top-[10px] right-[18px] h-1 w-8 bg-[linear-gradient(to_left,rgb(185_156_255/34%),transparent)]",
  bottom:
    "absolute bottom-[18px] left-[10px] h-8 w-1 bg-[linear-gradient(to_top,rgb(185_156_255/34%),transparent)]",
  left: "absolute top-[10px] left-[18px] h-1 w-8 bg-[linear-gradient(to_right,rgb(185_156_255/34%),transparent)]",
}

/**
 * One focus-mode edge marker: the learned map continues past the visible
 * pane in this direction. Renders nothing when no unobstructed placement
 * exists.
 */
const MapContinuation = memo(function MapContinuation({
  frame,
  marker,
  overlayRects,
  safeInsets,
  viewport,
  visibleRoomFootprints,
}: MapContinuationProps) {
  const box = projectFocusContinuationOverlay(
    marker,
    viewport,
    frame,
    safeInsets,
    visibleRoomFootprints,
    overlayRects
  )
  if (box === null) return null
  return (
    // oxlint-disable jsx-a11y/prefer-tag-over-role -- the marker is a labeled inline graphic, there is no image file for an img tag
    <div
      aria-label={`Learned map continues ${edgeLabels[marker.edge]}`}
      className="pointer-events-none absolute text-[#b99cff] drop-shadow-[0_0_5px_rgb(185_156_255/28%)]"
      data-edge={marker.edge}
      role="img"
      style={
        {
          height: `${box.height}px`,
          left: `${box.left}px`,
          top: `${box.top}px`,
          width: `${box.width}px`,
        } as CSSProperties
      }
    >
      <span aria-hidden="true" className={fadeClass[marker.edge]} />
      <ChevronsRightIcon
        aria-hidden="true"
        className={cn("size-[18px]", chevronClass[marker.edge])}
      />
    </div>
    // oxlint-enable jsx-a11y/prefer-tag-over-role
  )
})

export { MapContinuation, type MapContinuationProps }
