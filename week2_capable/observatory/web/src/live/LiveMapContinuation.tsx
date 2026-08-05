import {
  memo,
  type CSSProperties,
} from "react";
import { ChevronsRight } from "lucide-react";
import type {
  MapFrame,
  MapSafeInsets,
} from "./mapCamera";
import type {
  MapViewport,
} from "./mapModel";
import {
  projectFocusContinuationOverlay,
  type FocusContinuation,
} from "./focusContinuation";
import type { MapOverlayRect } from "./mapPresentation";
import type { MapRoomFootprint } from "./mapRoomFootprint";

type Props = {
  frame: MapFrame;
  marker: FocusContinuation;
  overlayRects: readonly MapOverlayRect[];
  safeInsets: MapSafeInsets;
  viewport: MapViewport;
  visibleRoomFootprints: readonly MapRoomFootprint[];
};

const edgeLabels = {
  top: "north",
  right: "east",
  bottom: "south",
  left: "west",
} as const;

export const LiveMapContinuation = memo(function LiveMapContinuation({
  frame,
  marker,
  overlayRects,
  safeInsets,
  viewport,
  visibleRoomFootprints,
}: Props) {
  const box = projectFocusContinuationOverlay(
    marker,
    viewport,
    frame,
    safeInsets,
    visibleRoomFootprints,
    overlayRects,
  );
  if (box === null) return null;
  return (
    <div
      aria-label={`Learned map continues ${edgeLabels[marker.edge]}`}
      className="live-map-continuation"
      data-edge={marker.edge}
      role="img"
      style={{
        height: `${box.height}px`,
        left: `${box.left}px`,
        top: `${box.top}px`,
        width: `${box.width}px`,
      } as CSSProperties}
    >
      <span
        aria-hidden="true"
        className="live-map-continuation-fade"
      />
      <ChevronsRight
        aria-hidden="true"
        className="live-map-continuation-chevron"
        size={18}
      />
    </div>
  );
});
