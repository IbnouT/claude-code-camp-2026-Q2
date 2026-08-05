import {
  mapColumnGap,
  mapRoomHeight,
  mapRoomWidth,
  mapRowGap,
  type MapGraph,
  type MapPoint,
  type MapViewport,
} from "./mapModel";
import type { MapCameraMode } from "./mapPresentation";

export type MapExtentPoint = {
  source: string;
  point: MapPoint;
};

export type MapFrame = {
  width: number;
  height: number;
};

export type MapSafeInsets = {
  top: number;
  right: number;
  bottom: number;
  left: number;
};

export type MapCameraResolution = {
  viewport: MapViewport;
  panning: boolean;
};

export type MapCameraView = {
  center: MapPoint;
  scale: number;
};

export type MapCameraMotion = {
  center: MapPoint;
  velocity: MapPoint;
};

export type FollowMapCameraFocus = {
  agent: MapPoint;
  extent: MapViewport;
};

export type MapCameraInput = {
  activeExtent: MapViewport;
  camera: MapCameraMode;
  completeExtent: MapViewport;
  fitExtent: MapViewport;
  fitOnFollow?: boolean;
  frame: MapFrame;
  graph: MapGraph;
  manualCenter: MapPoint | null;
  zoom: number;
};

const defaultExtentPadding = 60;
const minimumReadableScale = 0.75;
export const minimumCameraScale = 0.1;
export const maximumCameraScale = 2;

export function mapContentExtent(
  graph: MapGraph,
  visibleRoomIds: ReadonlySet<string>,
  markerPoints: readonly MapExtentPoint[],
  padding = defaultExtentPadding,
): MapViewport {
  const points = graph.rooms.flatMap(({ node, point }) => {
    if (!visibleRoomIds.has(node.id)) return [];
    return [
      point,
      {
        x: point.x + mapRoomWidth,
        y: point.y + mapRoomHeight,
      },
    ];
  });
  points.push(
    ...markerPoints.flatMap(({ source, point }) => {
      return visibleRoomIds.has(source) ? [point] : [];
    }),
  );
  if (points.length === 0) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }

  const safePadding = Math.max(padding, 0);
  const minimumX = Math.min(...points.map(({ x }) => x));
  const minimumY = Math.min(...points.map(({ y }) => y));
  const maximumX = Math.max(...points.map(({ x }) => x));
  const maximumY = Math.max(...points.map(({ y }) => y));
  return {
    x: minimumX - safePadding,
    y: minimumY - safePadding,
    width: maximumX - minimumX + safePadding * 2,
    height: maximumY - minimumY + safePadding * 2,
  };
}

export function fitMapViewport(
  extent: MapViewport,
  frame: MapFrame,
): MapViewport {
  if (
    extent.width <= 0
    || extent.height <= 0
    || frame.width <= 0
    || frame.height <= 0
  ) {
    return extent;
  }

  const aspect = frame.width / frame.height;
  const width = Math.max(extent.width, extent.height * aspect);
  const height = width / aspect;
  const center = viewportCenter(extent);
  return {
    x: center.x - width / 2,
    y: center.y - height / 2,
    width,
    height,
  };
}

export function mapCameraViewport(
  view: MapCameraView,
  frame: MapFrame,
): MapViewport {
  const scale = clamp(
    Number.isFinite(view.scale) && view.scale > 0 ? view.scale : 1,
    minimumCameraScale,
    maximumCameraScale,
  );
  const width = frame.width / scale;
  const height = frame.height / scale;
  return {
    x: view.center.x - width / 2,
    y: view.center.y - height / 2,
    width,
    height,
  };
}

export function fitMapCamera(
  extent: MapViewport,
  frame: MapFrame,
): MapCameraView {
  const center = viewportCenter(extent);
  if (
    extent.width <= 0
    || extent.height <= 0
    || frame.width <= 0
    || frame.height <= 0
  ) {
    return { center, scale: 1 };
  }
  return {
    center,
    scale: clamp(
      Math.min(frame.width / extent.width, frame.height / extent.height),
      minimumCameraScale,
      maximumCameraScale,
    ),
  };
}

export function fitMapCameraToSafeFrame(
  extent: MapViewport,
  frame: MapFrame,
  insets: MapSafeInsets,
): MapCameraView {
  const safeWidth = Math.max(frame.width - insets.left - insets.right, 1);
  const safeHeight = Math.max(frame.height - insets.top - insets.bottom, 1);
  const center = viewportCenter(extent);
  if (
    extent.width <= 0
    || extent.height <= 0
    || frame.width <= 0
    || frame.height <= 0
  ) {
    return { center, scale: 1 };
  }
  const scale = clamp(
    Math.min(safeWidth / extent.width, safeHeight / extent.height),
    minimumCameraScale,
    maximumCameraScale,
  );
  const safeCenter = {
    x: insets.left + safeWidth / 2,
    y: insets.top + safeHeight / 2,
  };
  const frameCenter = {
    x: frame.width / 2,
    y: frame.height / 2,
  };
  return {
    center: {
      x: center.x - (safeCenter.x - frameCenter.x) / scale,
      y: center.y - (safeCenter.y - frameCenter.y) / scale,
    },
    scale,
  };
}

export function zoomMapCamera(
  view: MapCameraView,
  direction: "in" | "out",
): MapCameraView {
  const nextScale = direction === "in"
    ? view.scale * 1.25
    : view.scale / 1.25;
  return {
    center: view.center,
    scale: clamp(nextScale, minimumCameraScale, maximumCameraScale),
  };
}

export function panMapCamera(
  view: MapCameraView,
  delta: MapPoint,
  worldUnitsPerPixel: MapPoint,
): MapCameraView {
  return {
    center: {
      x: view.center.x - delta.x * worldUnitsPerPixel.x,
      y: view.center.y - delta.y * worldUnitsPerPixel.y,
    },
    scale: view.scale,
  };
}

export function followMapCameraWithinDeadZone(
  view: MapCameraView,
  target: MapPoint,
  frame: MapFrame,
): MapCameraView {
  const scale = clamp(
    Number.isFinite(view.scale) && view.scale > 0 ? view.scale : 1,
    minimumCameraScale,
    maximumCameraScale,
  );
  const halfWidth = Math.min(
    mapColumnGap,
    Math.max(frame.width, 0) * 0.12 / scale,
  );
  const halfHeight = Math.min(
    mapRowGap,
    Math.max(frame.height, 0) * 0.12 / scale,
  );
  const offset = {
    x: target.x - view.center.x,
    y: target.y - view.center.y,
  };
  return {
    center: {
      x: view.center.x + overflowOutsideRange(offset.x, halfWidth),
      y: view.center.y + overflowOutsideRange(offset.y, halfHeight),
    },
    scale: view.scale,
  };
}

export function resolveFollowMapCameraAnchor(
  anchor: MapCameraView,
  target: MapPoint,
  frame: MapFrame,
  focus: FollowMapCameraFocus | null = null,
): MapCameraView {
  const followed = followMapCameraWithinDeadZone(
    anchor,
    target,
    frame,
  );
  return focus === null
    ? followed
    : clampFocusCamera(
      followed,
      focus.agent,
      focus.extent,
      frame,
    );
}

export function stepCriticallyDampedMapCenter(
  motion: MapCameraMotion,
  target: MapPoint,
  deltaSeconds: number,
  responseSeconds = 0.28,
): MapCameraMotion {
  const safeDelta = Math.max(
    Number.isFinite(deltaSeconds) ? deltaSeconds : 0,
    0,
  );
  const safeResponse = Math.max(
    Number.isFinite(responseSeconds) ? responseSeconds : 0.28,
    0.01,
  );
  const x = dampAxis(
    motion.center.x,
    motion.velocity.x,
    target.x,
    safeDelta,
    safeResponse,
  );
  const y = dampAxis(
    motion.center.y,
    motion.velocity.y,
    target.y,
    safeDelta,
    safeResponse,
  );
  return {
    center: {
      x: x.position,
      y: y.position,
    },
    velocity: {
      x: x.velocity,
      y: y.velocity,
    },
  };
}

export function clampMapCamera(
  view: MapCameraView,
  extent: MapViewport,
  frame: MapFrame,
): MapCameraView {
  const viewport = centerMapViewportInExtent(
    extent,
    {
      width: frame.width / view.scale,
      height: frame.height / view.scale,
    },
    view.center,
  );
  return {
    center: viewportCenter(viewport),
    scale: view.scale,
  };
}

export function clampFocusCamera(
  view: MapCameraView,
  agent: MapPoint,
  focusExtent: MapViewport,
  frame: MapFrame,
): MapCameraView {
  const viewport = mapCameraViewport(view, frame);
  const leftDistance = agent.x - focusExtent.x;
  const rightDistance = focusExtent.x + focusExtent.width - agent.x;
  const topDistance = agent.y - focusExtent.y;
  const bottomDistance = focusExtent.y + focusExtent.height - agent.y;
  const maximumXOffset = Math.max(
    0,
    Math.min(
      viewport.width / 4,
      rightDistance + mapRoomWidth,
    ),
  );
  const minimumXOffset = -Math.max(
    0,
    Math.min(
      viewport.width / 4,
      leftDistance + mapRoomWidth,
    ),
  );
  const maximumYOffset = Math.max(
    0,
    Math.min(
      viewport.height / 4,
      bottomDistance + mapRoomHeight,
    ),
  );
  const minimumYOffset = -Math.max(
    0,
    Math.min(
      viewport.height / 4,
      topDistance + mapRoomHeight,
    ),
  );
  return {
    center: {
      x: agent.x + clamp(
        view.center.x - agent.x,
        minimumXOffset,
        maximumXOffset,
      ),
      y: agent.y + clamp(
        view.center.y - agent.y,
        minimumYOffset,
        maximumYOffset,
      ),
    },
    scale: view.scale,
  };
}

export function mapSafeViewport(
  viewport: MapViewport,
  frame: MapFrame,
  insets: MapSafeInsets,
): MapViewport {
  if (frame.width <= 0 || frame.height <= 0) return viewport;
  const horizontalScale = viewport.width / frame.width;
  const verticalScale = viewport.height / frame.height;
  return {
    x: viewport.x + insets.left * horizontalScale,
    y: viewport.y + insets.top * verticalScale,
    width: Math.max(
      viewport.width - (insets.left + insets.right) * horizontalScale,
      0,
    ),
    height: Math.max(
      viewport.height - (insets.top + insets.bottom) * verticalScale,
      0,
    ),
  };
}

export function zoomMapViewport(
  viewport: MapViewport,
  zoom: number,
): MapViewport {
  const safeZoom = Number.isFinite(zoom) && zoom > 0 ? zoom : 1;
  const center = viewportCenter(viewport);
  const width = viewport.width / safeZoom;
  const height = viewport.height / safeZoom;
  return {
    x: center.x - width / 2,
    y: center.y - height / 2,
    width,
    height,
  };
}

export function centerMapViewportInExtent(
  extent: MapViewport,
  size: Pick<MapViewport, "width" | "height">,
  center: MapPoint,
): MapViewport {
  const x = extent.width <= size.width
    ? extent.x - (size.width - extent.width) / 2
    : clamp(
      center.x - size.width / 2,
      extent.x,
      extent.x + extent.width - size.width,
    );
  const y = extent.height <= size.height
    ? extent.y - (size.height - extent.height) / 2
    : clamp(
      center.y - size.height / 2,
      extent.y,
      extent.y + extent.height - size.height,
    );
  return { x, y, width: size.width, height: size.height };
}

export function roomCenter(
  graph: MapGraph,
  roomId: string | null,
): MapPoint | null {
  const point = graph.rooms.find(({ node }) => node.id === roomId)?.point;
  return point === undefined
    ? null
    : {
      x: point.x + mapRoomWidth / 2,
      y: point.y + mapRoomHeight / 2,
    };
}

export function isContinuousMapTransition(
  graph: MapGraph,
  previousRoomId: string | null,
  currentRoomId: string,
): boolean {
  if (previousRoomId === null || previousRoomId === currentRoomId) return true;
  return graph.connections.some((connection) => {
    if (connection.displacement) return false;
    return (
      connection.source === previousRoomId
      && connection.target === currentRoomId
    ) || (
      connection.target === previousRoomId
      && connection.source === currentRoomId
    );
  });
}

export function resolveMapViewport({
  activeExtent,
  camera,
  completeExtent,
  fitExtent,
  fitOnFollow = false,
  frame,
  graph,
  manualCenter,
  zoom,
}: MapCameraInput): MapCameraResolution {
  const currentCenter = roomCenter(graph, graph.currentRoomId)
    ?? viewportCenter(activeExtent);
  let viewport: MapViewport;
  if (camera === "fit" || (camera === "follow" && fitOnFollow)) {
    viewport = zoomMapViewport(
      fitMapViewport(camera === "fit" ? fitExtent : activeExtent, frame),
      zoom,
    );
  } else {
    const extent = camera === "manual" ? completeExtent : activeExtent;
    const center = camera === "manual"
      ? manualCenter ?? currentCenter
      : currentCenter;
    const width = Math.min(
      Math.max(extent.width, frame.width),
      frame.width / minimumReadableScale,
    ) / zoom;
    const height = Math.min(
      Math.max(extent.height, frame.height),
      frame.height / minimumReadableScale,
    ) / zoom;
    viewport = camera === "manual"
      ? centerMapViewportInExtent(
        completeExtent,
        { width, height },
        center,
      )
      : {
        x: center.x - width / 2,
        y: center.y - height / 2,
        width,
        height,
      };
  }
  return {
    viewport,
    panning: completeExtent.width > viewport.width
      || completeExtent.height > viewport.height,
  };
}

export function viewportCenter(viewport: MapViewport): MapPoint {
  return {
    x: viewport.x + viewport.width / 2,
    y: viewport.y + viewport.height / 2,
  };
}

export function keepSelectedRoomOutsidePanel(
  viewport: MapViewport,
  frame: MapFrame,
  roomPoint: MapPoint | null,
  panelInset: { right: number; bottom: number },
  screenMargin = 18,
): MapViewport {
  if (
    roomPoint === null
    || frame.width <= 0
    || frame.height <= 0
  ) {
    return viewport;
  }
  const horizontalScale = viewport.width / frame.width;
  const verticalScale = viewport.height / frame.height;
  const selectedRight = roomPoint.x + mapRoomWidth + 38 * horizontalScale;
  const selectedBottom = roomPoint.y + mapRoomHeight + 30 * verticalScale;
  const safeRight = panelInset.right <= 0
    ? Number.POSITIVE_INFINITY
    : viewport.x
      + (frame.width - panelInset.right - screenMargin) * horizontalScale;
  const safeBottom = panelInset.bottom <= 0
    ? Number.POSITIVE_INFINITY
    : viewport.y
      + (frame.height - panelInset.bottom - screenMargin) * verticalScale;
  const deltaX = Math.max(selectedRight - safeRight, 0);
  const deltaY = Math.max(selectedBottom - safeBottom, 0);
  if (deltaX === 0 && deltaY === 0) return viewport;
  return {
    ...viewport,
    x: viewport.x + deltaX,
    y: viewport.y + deltaY,
  };
}

export function mapOverlaySafeBand({
  thoughtVisible,
  thoughtExpanded,
  legendExpanded,
  legendEntries,
}: {
  thoughtVisible: boolean;
  thoughtExpanded: boolean;
  legendExpanded: boolean;
  legendEntries: number;
}): number {
  const collapsedHeight = 36;
  const thoughtHeight = !thoughtVisible
    ? 0
    : thoughtExpanded ? 121 : collapsedHeight;
  const legendHeight = legendExpanded
    ? Math.ceil(26 + Math.max(legendEntries, 1) * 19.2)
    : collapsedHeight;
  return Math.max(thoughtHeight, legendHeight) + 18;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function overflowOutsideRange(value: number, halfRange: number): number {
  if (value < -halfRange) return value + halfRange;
  if (value > halfRange) return value - halfRange;
  return 0;
}

function dampAxis(
  position: number,
  velocity: number,
  target: number,
  deltaSeconds: number,
  responseSeconds: number,
): { position: number; velocity: number } {
  if (deltaSeconds === 0 || position === target) {
    return {
      position,
      velocity: position === target ? 0 : velocity,
    };
  }
  const omega = 2 / responseSeconds;
  const displacement = position - target;
  const exponential = Math.exp(-omega * deltaSeconds);
  const timeScaled = (velocity + omega * displacement) * deltaSeconds;
  const nextDisplacement = (displacement + timeScaled) * exponential;
  const nextVelocity = (velocity - omega * timeScaled) * exponential;
  const nextPosition = target + nextDisplacement;
  const crossedTarget = (
    target - position > 0 && nextPosition > target
  ) || (
    target - position < 0 && nextPosition < target
  );
  return crossedTarget
    ? { position: target, velocity: 0 }
    : { position: nextPosition, velocity: nextVelocity };
}
