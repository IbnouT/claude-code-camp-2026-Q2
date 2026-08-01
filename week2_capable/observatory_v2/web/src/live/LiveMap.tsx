import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  CSSProperties,
  PointerEvent as ReactPointerEvent,
} from "react";
import {
  type Snapshot,
} from "../contracts";
import type { LiveRouteIdentity } from "../routes";
import {
  buildMapGraph,
  canonicalNodeId,
  mapRoomHeight,
  mapRoomWidth,
  type MapConnection,
  type MapPoint,
} from "./mapModel";
import {
  fitMapCameraToSafeFrame,
  clampFocusCamera,
  isContinuousMapTransition,
  keepSelectedRoomOutsidePanel,
  mapCameraViewport,
  mapOverlaySafeBand,
  mapContentExtent,
  panMapCamera,
  resolveFollowMapCameraAnchor,
  roomCenter,
  stepCriticallyDampedMapCenter,
  viewportCenter,
  zoomMapCamera,
  type MapCameraView,
  type MapSafeInsets,
} from "./mapCamera";
import { projectFocusContinuations } from "./focusContinuation";
import { LiveMapContinuation } from "./LiveMapContinuation";
import { LiveMapFrontier } from "./LiveMapFrontier";
import { LiveMapLegend } from "./LiveMapLegend";
import { LiveMapRoom } from "./LiveMapRoom";
import { LiveMapToolbar } from "./LiveMapToolbar";
import { LiveRoomInspector } from "./LiveRoomInspector";
import { LiveThoughtDock } from "./LiveThoughtDock";
import { LiveCombatPanel } from "./LiveCombatPanel";
import type { LiveSnapshotState } from "./useLiveSnapshot";
import { projectMapLegend } from "./mapLegend";
import { projectMapEvidence } from "./markerProjection";
import {
  automaticMapMode,
  maximumMapZoom,
  minimumMapZoom,
  projectLanternOpacities,
  projectMapPresentation,
  roomFitsFocusLayout,
  visibleRoomComponentSize,
  type MapCameraMode,
  type MapFocusLayout,
  type MapMode,
  type MapOverlayRect,
} from "./mapPresentation";
import { mapRoomFootprint } from "./mapRoomFootprint";
import {
  projectRoomInspector,
  type RoomInspectorProjection,
} from "./roomInspector";
import {
  selectedRoomFromLocation,
  syncSelectedRoomToLocation,
} from "./selectionUrl";

type Props = {
  identity: LiveRouteIdentity;
  snapshot: Snapshot | null;
  state: LiveSnapshotState;
};

const defaultFrame = { width: 1_600, height: 900 };
const defaultSafeInsets: MapSafeInsets = {
  top: 8,
  right: 8,
  bottom: 8,
  left: 8,
};
const overlayExpandedByDefault = () => {
  return typeof window === "undefined" || window.innerWidth > 700;
};

type DragState = {
  pointerId: number;
  clientX: number;
  clientY: number;
  center: MapPoint;
  moved: boolean;
};

export function LiveMap({
  identity,
  snapshot,
  state,
}: Props) {
  const [frame, setFrame] = useState(defaultFrame);
  const [cameraView, setCameraView] = useState<MapCameraView>({
    center: { x: 0, y: 0 },
    scale: 1,
  });
  const [cameraMode, setCameraMode] = useState<MapCameraMode>("follow");
  const [chosenMode, setChosenMode] = useState<MapMode | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(
    selectedRoomFromLocation,
  );
  const [thoughtExpanded, setThoughtExpanded] = useState(
    overlayExpandedByDefault,
  );
  const [legendExpanded, setLegendExpanded] = useState(
    false,
  );
  const [panHintVisible, setPanHintVisible] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [safeInsets, setSafeInsets] = useState(defaultSafeInsets);
  const [focusOverlayRects, setFocusOverlayRects] = useState<MapOverlayRect[]>(
    [],
  );
  const [markerOverlayRects, setMarkerOverlayRects] = useState<MapOverlayRect[]>(
    [],
  );
  const stageRef = useRef<HTMLElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const suppressClickRef = useRef(false);
  const cameraViewRef = useRef(cameraView);
  const followVelocityRef = useRef<MapPoint>({ x: 0, y: 0 });
  const followAnchorRef = useRef<MapPoint | null>(null);
  const followInitializedRef = useRef(false);
  const previousCurrentRoomIdRef = useRef<string | null>(null);

  const graph = useMemo(() => {
    return buildMapGraph(
      snapshot?.world.nodes ?? [],
      snapshot?.world.edges ?? [],
    );
  }, [snapshot]);
  const evidenceMarkers = useMemo(() => {
    return projectMapEvidence(
      snapshot?.world.nodes ?? [],
      snapshot?.world.edges ?? [],
      snapshot?.world.frontier ?? [],
      graph.rooms,
    );
  }, [graph.rooms, snapshot]);
  const mode = automaticMapMode(graph.rooms.length, chosenMode);
  const currentCenter = roomCenter(graph, graph.currentRoomId) ?? {
    x: graph.x + graph.width / 2,
    y: graph.y + graph.height / 2,
  };
  const focusLayout: MapFocusLayout = {
    frame,
    overlayRects: focusOverlayRects,
    viewport: mapCameraViewport({
      center: currentCenter,
      scale: cameraView.scale,
    }, frame),
  };
  const presentation = useMemo(() => {
    return projectMapPresentation(
      graph,
      mode,
      selectedRoomId,
      focusLayout,
    );
  }, [
    focusLayout.frame.height,
    focusLayout.frame.width,
    focusLayout.overlayRects,
    focusLayout.viewport.height,
    focusLayout.viewport.width,
    focusLayout.viewport.x,
    focusLayout.viewport.y,
    graph,
    mode,
    selectedRoomId,
  ]);
  const focusHiddenInsideCount = useMemo(() => {
    if (mode !== "focus") return 0;
    return graph.rooms.filter(({ node, point }) => {
      return !presentation.visibleRoomIds.has(node.id)
        && roomFitsFocusLayout(
          node,
          point,
          node.id === graph.currentRoomId,
          focusLayout,
        );
    }).length;
  }, [
    focusLayout.frame.height,
    focusLayout.frame.width,
    focusLayout.overlayRects,
    focusLayout.viewport.height,
    focusLayout.viewport.width,
    focusLayout.viewport.x,
    focusLayout.viewport.y,
    graph.rooms,
    mode,
    presentation.visibleRoomIds,
  ]);
  const focusComponentRoomCount = useMemo(() => {
    return mode === "focus"
      ? visibleRoomComponentSize(graph, presentation.visibleRoomIds)
      : 0;
  }, [graph, mode, presentation.visibleRoomIds]);
  const lanternOpacities = useMemo(() => {
    return projectLanternOpacities(graph);
  }, [graph]);
  const markerPoints = useMemo(() => {
    return evidenceMarkers.frontiers.map(({ source, end }) => ({
      source,
      point: end,
    }));
  }, [evidenceMarkers.frontiers]);
  const completeRoomIds = useMemo(() => {
    return new Set(graph.rooms.map(({ node }) => node.id));
  }, [graph.rooms]);
  const completeExtent = useMemo(() => {
    return mapContentExtent(graph, completeRoomIds, markerPoints);
  }, [completeRoomIds, graph, markerPoints]);
  const activeExtent = useMemo(() => {
    return mapContentExtent(
      graph,
      presentation.visibleRoomIds,
      markerPoints,
    );
  }, [graph, markerPoints, presentation.visibleRoomIds]);
  const focusRawExtent = useMemo(() => {
    return mapContentExtent(
      graph,
      presentation.visibleRoomIds,
      [],
      0,
    );
  }, [graph, presentation.visibleRoomIds]);
  const fitExtent = useMemo(() => {
    if (
      selectedRoomId === null
      || presentation.selectionPathRoomIds.length === 0
    ) {
      return activeExtent;
    }
    return mapContentExtent(
      graph,
      new Set(presentation.selectionPathRoomIds),
      markerPoints,
    );
  }, [
    activeExtent,
    graph,
    markerPoints,
    presentation.selectionPathRoomIds,
    selectedRoomId,
  ]);
  const beaconRoomIds = useMemo(() => {
    const rawNodes = new Map(
      (snapshot?.world.nodes ?? []).map((node) => [node.id, node]),
    );
    return new Set(
      (snapshot?.world.objective_beacons ?? []).flatMap((beacon) => {
        const node = rawNodes.get(beacon.node_id);
        return node === undefined ? [] : [canonicalNodeId(node)];
      }),
    );
  }, [snapshot]);
  const selectedMapRoom = useMemo(() => {
    return graph.rooms.find(({ node }) => node.id === selectedRoomId) ?? null;
  }, [graph.rooms, selectedRoomId]);
  const inspector = useMemo<RoomInspectorProjection | null>(() => {
    if (selectedMapRoom === null || snapshot === null) return null;
    return projectRoomInspector(
      selectedMapRoom.node,
      snapshot.world.nodes,
      snapshot.world.frontier,
      snapshot.room_economics,
    );
  }, [selectedMapRoom, snapshot]);
  const baseViewport = mapCameraViewport(cameraView, frame);
  const panelInset = frame.width <= 700
    ? { right: 0, bottom: Math.min(frame.height * 0.55, 420) + 14 }
    : { right: 318, bottom: 0 };
  const projectedViewport = keepSelectedRoomOutsidePanel(
    baseViewport,
    frame,
    selectedMapRoom?.point ?? null,
    inspector === null
      ? { right: 0, bottom: 0 }
      : {
        right: panelInset.right,
        bottom: panelInset.bottom,
      },
  );
  const focusContinuations = useMemo(() => {
    if (mode !== "focus") return [];
    return projectFocusContinuations(
      graph,
      presentation.visibleRoomIds,
      projectedViewport,
    );
  }, [graph, mode, presentation.visibleRoomIds, projectedViewport]);
  const visibleRoomFootprints = useMemo(() => {
    return graph.rooms.flatMap(({ node, point }) => {
      return presentation.visibleRoomIds.has(node.id)
        ? [mapRoomFootprint(node, point, node.id === graph.currentRoomId)]
        : [];
    });
  }, [
    graph.currentRoomId,
    graph.rooms,
    presentation.visibleRoomIds,
  ]);
  const legendEntries = useMemo(() => {
    return projectMapLegend({
      rooms: graph.rooms.map(({ node }) => node),
      visibleRoomIds: presentation.visibleRoomIds,
      currentRoomId: graph.currentRoomId,
      selectedRoomId,
      combat: Boolean(snapshot?.combat),
      beaconRoomIds,
      evidence: evidenceMarkers,
      focusContinuationCount: focusContinuations.length,
    });
  }, [
    beaconRoomIds,
    evidenceMarkers,
    focusContinuations.length,
    graph.currentRoomId,
    graph.rooms,
    presentation.visibleRoomIds,
    selectedRoomId,
    snapshot?.combat,
  ]);
  const overlayBand = mapOverlaySafeBand({
    thoughtVisible: snapshot?.agent_thought !== null
      && snapshot?.agent_thought !== undefined,
    thoughtExpanded,
    legendExpanded,
    legendEntries: legendEntries.length,
  });
  const handleSelectRoom = useCallback((nodeId: string) => {
    setSelectedRoomId((current) => {
      const next = current === nodeId ? null : nodeId;
      syncSelectedRoomToLocation(next);
      return next;
    });
  }, []);
  const closeSelectedRoom = useCallback(() => {
    setSelectedRoomId(null);
    syncSelectedRoomToLocation(null);
  }, []);
  useEffect(() => {
    cameraViewRef.current = cameraView;
  }, [cameraView]);

  useEffect(() => {
    if (cameraMode !== "follow" || graph.currentRoomId === null) {
      followVelocityRef.current = { x: 0, y: 0 };
      followAnchorRef.current = null;
      return;
    }
    const currentRoomId = graph.currentRoomId;
    const previousRoomId = previousCurrentRoomIdRef.current;
    if (!followInitializedRef.current) {
      followInitializedRef.current = true;
      followVelocityRef.current = { x: 0, y: 0 };
      followAnchorRef.current = currentCenter;
      cameraViewRef.current = {
        center: currentCenter,
        scale: cameraViewRef.current.scale,
      };
      setCameraView((current) => ({
        center: currentCenter,
        scale: current.scale,
      }));
      return;
    }
    const start = cameraViewRef.current.center;
    const connectedMovement = isContinuousMapTransition(
      graph,
      previousRoomId,
      currentRoomId,
    );
    const anchor = {
      center: followAnchorRef.current ?? cameraViewRef.current.center,
      scale: cameraViewRef.current.scale,
    };
    const targetView = connectedMovement
      ? resolveFollowMapCameraAnchor(
        anchor,
        currentCenter,
        frame,
        mode === "focus"
          ? { agent: currentCenter, extent: focusRawExtent }
          : null,
      )
      : { center: currentCenter, scale: anchor.scale };
    const target = targetView.center;
    followAnchorRef.current = target;
    if (
      Math.abs(start.x - target.x) < 0.01
      && Math.abs(start.y - target.y) < 0.01
    ) {
      followVelocityRef.current = { x: 0, y: 0 };
      return;
    }
    if (!connectedMovement) {
      followVelocityRef.current = { x: 0, y: 0 };
      followAnchorRef.current = target;
      cameraViewRef.current = {
        center: target,
        scale: cameraViewRef.current.scale,
      };
      setCameraView((current) => ({
        center: target,
        scale: current.scale,
      }));
      return;
    }
    const reducedMotion = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    ).matches ?? false;
    if (reducedMotion || typeof requestAnimationFrame === "undefined") {
      followVelocityRef.current = { x: 0, y: 0 };
      followAnchorRef.current = target;
      cameraViewRef.current = {
        center: target,
        scale: cameraViewRef.current.scale,
      };
      setCameraView((current) => ({
        center: target,
        scale: current.scale,
      }));
      return;
    }
    followVelocityRef.current = {
      x: (target.x - start.x) * followVelocityRef.current.x < 0
        ? 0
        : followVelocityRef.current.x,
      y: (target.y - start.y) * followVelocityRef.current.y < 0
        ? 0
        : followVelocityRef.current.y,
    };
    let previousFrameAt = performance.now();
    let animationFrame = 0;
    const update = (now: number) => {
      const deltaSeconds = Math.min(
        Math.max((now - previousFrameAt) / 1_000, 0),
        0.1,
      );
      previousFrameAt = now;
      const motion = stepCriticallyDampedMapCenter({
        center: cameraViewRef.current.center,
        velocity: followVelocityRef.current,
      }, target, deltaSeconds);
      const settled = (
        Math.hypot(
          motion.center.x - target.x,
          motion.center.y - target.y,
        ) < 0.05
        && Math.hypot(motion.velocity.x, motion.velocity.y) < 0.05
      );
      const nextCenter = settled ? target : motion.center;
      followVelocityRef.current = settled
        ? { x: 0, y: 0 }
        : motion.velocity;
      cameraViewRef.current = {
        center: nextCenter,
        scale: cameraViewRef.current.scale,
      };
      setCameraView((current) => ({
        center: nextCenter,
        scale: current.scale,
      }));
      if (!settled) {
        animationFrame = requestAnimationFrame(update);
      }
    };
    animationFrame = requestAnimationFrame(update);
    return () => cancelAnimationFrame(animationFrame);
  }, [
    cameraMode,
    cameraView.scale,
    currentCenter.x,
    currentCenter.y,
    focusRawExtent.height,
    focusRawExtent.width,
    focusRawExtent.x,
    focusRawExtent.y,
    frame.height,
    frame.width,
    graph.connections,
    graph.currentRoomId,
    mode,
  ]);

  useLayoutEffect(() => {
    const stage = stageRef.current;
    if (stage === null || typeof ResizeObserver === "undefined") return;
    const updateGeometry = () => {
      const bounds = stage.getBoundingClientRect();
      if (bounds.width <= 0 || bounds.height <= 0) return;
      setFrame((current) => {
        if (
          Math.abs(current.width - bounds.width) < 1
          && Math.abs(current.height - bounds.height) < 1
        ) {
          return current;
        }
        return { width: bounds.width, height: bounds.height };
      });
      const focusOccluders = [...stage.querySelectorAll<HTMLElement>(
        "[data-map-focus-occluder]",
      )];
      const markerOccluders = [...stage.querySelectorAll<HTMLElement>(
        "[data-map-focus-occluder], [data-map-marker-occluder]",
      )];
      const nextInsets = { ...defaultSafeInsets };
      const projectOverlay = (overlay: HTMLElement): MapOverlayRect => {
        const overlayBounds = overlay.getBoundingClientRect();
        const left = Math.max(overlayBounds.left - bounds.left - 8, 0);
        const top = Math.max(overlayBounds.top - bounds.top - 8, 0);
        const right = Math.min(
          overlayBounds.right - bounds.left + 8,
          bounds.width,
        );
        const bottom = Math.min(
          overlayBounds.bottom - bounds.top + 8,
          bounds.height,
        );
        return {
          x: left,
          y: top,
          width: Math.max(right - left, 0),
          height: Math.max(bottom - top, 0),
        };
      };
      const nextFocusOverlayRects = focusOccluders.map(projectOverlay);
      const nextMarkerOverlayRects = markerOccluders.map(projectOverlay);
      for (const overlay of focusOccluders) {
        const overlayBounds = overlay.getBoundingClientRect();
        const edge = overlay.dataset.mapOverlayEdge;
        if (edge === "top") {
          nextInsets.top = Math.max(
            nextInsets.top,
            overlayBounds.bottom - bounds.top + 8,
          );
        } else if (edge === "right") {
          nextInsets.right = Math.max(
            nextInsets.right,
            bounds.right - overlayBounds.left + 8,
          );
        } else if (edge === "bottom") {
          nextInsets.bottom = Math.max(
            nextInsets.bottom,
            bounds.bottom - overlayBounds.top + 8,
          );
        } else if (edge === "left") {
          nextInsets.left = Math.max(
            nextInsets.left,
            overlayBounds.right - bounds.left + 8,
          );
        }
      }
      setFocusOverlayRects((current) => {
        return overlayRectsEqual(current, nextFocusOverlayRects)
          ? current
          : nextFocusOverlayRects;
      });
      setMarkerOverlayRects((current) => {
        return overlayRectsEqual(current, nextMarkerOverlayRects)
          ? current
          : nextMarkerOverlayRects;
      });
      setSafeInsets((current) => {
        if (
          Math.abs(current.top - nextInsets.top) < 1
          && Math.abs(current.right - nextInsets.right) < 1
          && Math.abs(current.bottom - nextInsets.bottom) < 1
          && Math.abs(current.left - nextInsets.left) < 1
        ) {
          return current;
        }
        return nextInsets;
      });
    };
    const observer = new ResizeObserver(updateGeometry);
    observer.observe(stage);
    for (const overlay of stage.querySelectorAll<HTMLElement>(
      "[data-map-focus-occluder], [data-map-marker-occluder]",
    )) {
      observer.observe(overlay);
    }
    updateGeometry();
    return () => observer.disconnect();
  }, [
    graph.rooms.length,
    inspector,
    legendEntries.length,
    legendExpanded,
    mode,
    snapshot?.agent_thought,
    thoughtExpanded,
  ]);

  useEffect(() => {
    const previousRoomId = previousCurrentRoomIdRef.current;
    const currentRoomId = graph.currentRoomId;
    previousCurrentRoomIdRef.current = currentRoomId;
    if (
      mode === "focus"
      && cameraMode === "manual"
      && previousRoomId !== null
      && currentRoomId !== null
      && previousRoomId !== currentRoomId
    ) {
      setCameraMode("follow");
    }
  }, [cameraMode, graph.currentRoomId, mode]);

  useEffect(() => {
    setCameraView({ center: { x: 0, y: 0 }, scale: 1 });
    followVelocityRef.current = { x: 0, y: 0 };
    followAnchorRef.current = null;
    followInitializedRef.current = false;
    previousCurrentRoomIdRef.current = null;
    setSafeInsets(defaultSafeInsets);
    setFocusOverlayRects([]);
    setMarkerOverlayRects([]);
    setCameraMode("follow");
    setChosenMode(null);
    setSelectedRoomId(selectedRoomFromLocation());
    setThoughtExpanded(overlayExpandedByDefault());
    setLegendExpanded(false);
    setPanHintVisible(true);
  }, [identity.sessionId]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (selectedRoomId !== null) {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeSelectedRoom();
        return;
      }
      if (document.querySelector('[role="dialog"]') !== null) return;
      if (!legendExpanded) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      setLegendExpanded(false);
    };
    const handleOutsidePointer = (event: PointerEvent) => {
      if (selectedRoomId === null) return;
      if (!(event.target instanceof Element)) return;
      if (
        event.target.closest(".live-room-inspector") !== null
        || event.target.closest(".live-map-room") !== null
        || event.target.closest(".live-map-dock") !== null
        || event.target.closest(".live-map-toolbar") !== null
      ) {
        return;
      }
      closeSelectedRoom();
    };
    window.addEventListener("keydown", handleEscape, { capture: true });
    document.addEventListener("pointerdown", handleOutsidePointer, {
      capture: true,
    });
    return () => {
      window.removeEventListener("keydown", handleEscape, { capture: true });
      document.removeEventListener("pointerdown", handleOutsidePointer, {
        capture: true,
      });
    };
  }, [closeSelectedRoom, legendExpanded, selectedRoomId]);

  if (snapshot === null) {
    return (
      <div className="live-map-message" role="status">
        {state === "reconnecting"
          ? "World evidence is reconnecting."
          : "Loading learned world…"}
      </div>
    );
  }

  if (graph.rooms.length === 0) {
    return (
      <div className="live-map-message" role="status">
        Waiting for the first observed room.
      </div>
    );
  }

  const roomById = new Map(
    graph.rooms.map((room) => [room.node.id, room.point]),
  );
  const effectiveCameraView = cameraView;
  const camera = {
    viewport: projectedViewport,
    panning: mode !== "lantern",
  };
  const viewport = projectedViewport;
  const currentPoint = graph.currentRoomId === null
    ? undefined
    : roomById.get(graph.currentRoomId);
  const roomOpacity = (roomId: string): number => {
    if (
      mode !== "lantern"
      || roomId === graph.currentRoomId
      || roomId === selectedRoomId
    ) {
      return 1;
    }
    return lanternOpacities.get(roomId) ?? 0.12;
  };
  const handlePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    suppressClickRef.current = false;
    dragRef.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      center: viewportCenter(viewport),
      moved: false,
    };
  };
  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    const svg = svgRef.current;
    if (
      drag === null
      || drag.pointerId !== event.pointerId
      || svg === null
    ) {
      return;
    }
    const bounds = svg.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) return;
    const deltaX = event.clientX - drag.clientX;
    const deltaY = event.clientY - drag.clientY;
    if (!drag.moved && Math.hypot(deltaX, deltaY) < 4) return;
    if (!drag.moved) {
      drag.moved = true;
      suppressClickRef.current = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      setDragging(true);
      setPanHintVisible(false);
      if (mode === "lantern") setChosenMode("grow");
      setCameraMode("manual");
      drag.clientX = event.clientX;
      drag.clientY = event.clientY;
      drag.center = viewportCenter(viewport);
      event.preventDefault();
      return;
    }
    event.preventDefault();
    const panned = panMapCamera({
      center: drag.center,
      scale: effectiveCameraView.scale,
    }, {
      x: deltaX,
      y: deltaY,
    }, {
      x: viewport.width / bounds.width,
      y: viewport.height / bounds.height,
    });
    if (mode === "focus") {
      const clamped = clampFocusCamera(
        panned,
        currentCenter,
        focusRawExtent,
        frame,
      );
      setCameraView({
        center: {
          x: deltaX === 0 ? drag.center.x : clamped.center.x,
          y: deltaY === 0 ? drag.center.y : clamped.center.y,
        },
        scale: clamped.scale,
      });
    } else {
      setCameraView(panned);
    }
  };
  const stopDragging = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (drag?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setDragging(false);
    if (drag.moved && event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };
  const handleMapClickCapture = (
    event: ReactPointerEvent<SVGSVGElement>,
  ) => {
    if (!suppressClickRef.current) return;
    suppressClickRef.current = false;
    event.preventDefault();
    event.stopPropagation();
  };
  const handleCameraChange = (next: MapCameraMode) => {
    followVelocityRef.current = { x: 0, y: 0 };
    followAnchorRef.current = next === "follow"
      ? viewportCenter(viewport)
      : null;
    if (mode === "lantern" && next !== "follow") {
      setChosenMode("grow");
    }
    if (next === "fit") {
      setCameraView(fitMapCameraToSafeFrame(
        fitExtent,
        frame,
        safeInsets,
      ));
    } else {
      setCameraView((current) => ({
        center: viewportCenter(viewport),
        scale: current.scale,
      }));
    }
    setCameraMode(next);
  };
  const handleModeChange = (next: MapMode) => {
    if (next === "focus") {
      followInitializedRef.current = true;
      followVelocityRef.current = { x: 0, y: 0 };
      followAnchorRef.current = currentCenter;
      setCameraView((current) => ({
        center: currentCenter,
        scale: current.scale,
      }));
      setCameraMode("follow");
    } else if (next === "lantern") {
      followInitializedRef.current = true;
      followVelocityRef.current = { x: 0, y: 0 };
      followAnchorRef.current = currentCenter;
      setCameraView((current) => ({
        center: currentCenter,
        scale: current.scale,
      }));
      setCameraMode("follow");
    }
    setChosenMode(next);
  };
  const handleZoom = (direction: "in" | "out") => {
    setCameraView((current) => {
      return zoomMapCamera({
        center: viewportCenter(viewport),
        scale: current.scale,
      }, direction);
    });
  };
  return (
    <section
      ref={stageRef}
      className={[
        "live-map-stage",
        mode === "lantern" ? "is-lantern" : "",
        inspector === null ? "" : "has-inspector",
      ].filter(Boolean).join(" ")}
      aria-label="Learned world map"
      data-focus-fill-count={mode === "focus"
        ? presentation.focusFillRoomCount
        : undefined}
      data-focus-component-count={mode === "focus"
        ? focusComponentRoomCount
        : undefined}
      data-focus-hidden-inside-count={mode === "focus"
        ? focusHiddenInsideCount
        : undefined}
      data-focus-overlay-count={mode === "focus"
        ? focusOverlayRects.length
        : undefined}
      data-focus-pane-height={mode === "focus" ? frame.height : undefined}
      data-focus-pane-width={mode === "focus" ? frame.width : undefined}
      data-focus-shell-count={mode === "focus"
        ? presentation.focusShellRoomCount
        : undefined}
      style={{
        "--live-map-overlay-safe-band": `${overlayBand}px`,
      } as CSSProperties}
    >
      <LiveMapToolbar
        camera={cameraMode}
        mode={mode}
        selectedRoomId={selectedRoomId}
        zoom={effectiveCameraView.scale}
        minimumZoom={minimumMapZoom}
        maximumZoom={maximumMapZoom}
        onCameraChange={handleCameraChange}
        onModeChange={handleModeChange}
        onZoom={handleZoom}
      />
      <svg
        className={[
          "live-map",
          camera.panning ? "is-pannable" : "",
          dragging ? "is-dragging" : "",
        ].filter(Boolean).join(" ")}
        ref={svgRef}
        role="img"
        aria-label={`Learned world, ${graph.rooms.length} rooms`}
        style={{
          height: "100%",
        }}
        viewBox={`${viewport.x} ${viewport.y} ${viewport.width} ${viewport.height}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
        onClickCapture={handleMapClickCapture}
        onDragStart={(event) => event.preventDefault()}
      >
        <defs>
          <radialGradient id="live-current-room-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#4fd6c9" stopOpacity=".55" />
            <stop offset="100%" stopColor="#4fd6c9" stopOpacity="0" />
          </radialGradient>
          {mode === "lantern" && currentPoint !== undefined ? (
            <radialGradient
              id="live-map-lantern-gradient"
              cx={currentPoint.x + mapRoomWidth / 2}
              cy={currentPoint.y + mapRoomHeight / 2}
              gradientUnits="userSpaceOnUse"
              r="280"
            >
              <stop
                className="live-map-lantern-center"
                offset="0%"
              />
              <stop
                className="live-map-lantern-edge"
                offset="100%"
              />
            </radialGradient>
          ) : null}
        </defs>
        {mode === "lantern" && currentPoint !== undefined ? (
          <rect
            className="live-map-lantern-field"
            fill="url(#live-map-lantern-gradient)"
            height={viewport.height}
            pointerEvents="none"
            width={viewport.width}
            x={viewport.x}
            y={viewport.y}
          />
        ) : null}
        <g className="live-map-connections">
          {graph.connections.flatMap((connection) => {
            if (!presentation.visibleConnectionIds.has(connection.id)) {
              return [];
            }
            return [(
              <MapLink
                key={connection.id}
                connection={connection}
                source={roomById.get(connection.source)}
                target={roomById.get(connection.target)}
                opacity={Math.max(
                  roomOpacity(connection.source),
                  roomOpacity(connection.target),
                )}
              />
            )];
          })}
        </g>
        <g className="live-map-frontiers">
          {evidenceMarkers.frontiers.flatMap((marker) => {
            if (!presentation.visibleRoomIds.has(marker.source)) return [];
            return [(
              <g key={marker.id} opacity={roomOpacity(marker.source)}>
                <LiveMapFrontier marker={marker} />
              </g>
            )];
          })}
        </g>
        <g className="live-map-rooms">
          {graph.rooms.flatMap(({ node, point }) => {
            if (!presentation.visibleRoomIds.has(node.id)) return [];
            return [(
              <g key={node.id} opacity={roomOpacity(node.id)}>
                <LiveMapRoom
                  node={node}
                  point={point}
                  current={node.id === graph.currentRoomId}
                  selected={node.id === selectedRoomId}
                  combat={Boolean(
                    snapshot.combat && node.id === graph.currentRoomId,
                  )}
                  beacon={beaconRoomIds.has(node.id)}
                  verticalMarkers={
                    evidenceMarkers.verticalByRoom.get(node.id) ?? []
                  }
                  onSelect={handleSelectRoom}
                />
              </g>
            )];
          })}
        </g>
      </svg>
      {mode === "focus" ? (
        <div
          aria-label="Learned map continuations"
          className="live-map-continuations"
        >
          {focusContinuations.map((marker) => (
            <LiveMapContinuation
              frame={frame}
              key={marker.edge}
              marker={marker}
              overlayRects={markerOverlayRects}
              safeInsets={defaultSafeInsets}
              viewport={viewport}
              visibleRoomFootprints={visibleRoomFootprints}
            />
          ))}
        </div>
      ) : null}
      {inspector === null ? null : (
        <LiveRoomInspector
          room={inspector}
          onClose={closeSelectedRoom}
        />
      )}
      <LiveCombatPanel episode={snapshot.combat_episode} />
      <LiveThoughtDock
        expanded={thoughtExpanded}
        thought={snapshot.agent_thought}
        onToggle={() => setThoughtExpanded((current) => !current)}
      />
      <LiveMapLegend
        entries={legendEntries}
        expanded={legendExpanded}
        onToggle={() => setLegendExpanded((current) => !current)}
      />
      {camera.panning && panHintVisible ? (
        <p className="live-map-pan-hint">
          Drag to explore the learned world.
        </p>
      ) : null}
      {state === "reconnecting" ? (
        <p className="live-map-connection-state" role="status">
          Showing the latest world while evidence reconnects.
        </p>
      ) : null}
    </section>
  );
}

function MapLink({
  connection,
  opacity,
  source,
  target,
}: {
  connection: MapConnection;
  opacity: number;
  source: MapPoint | undefined;
  target: MapPoint | undefined;
}) {
  if (source === undefined || target === undefined) {
    return null;
  }
  const start = {
    x: source.x + mapRoomWidth / 2,
    y: source.y + mapRoomHeight / 2,
  };
  const end = {
    x: target.x + mapRoomWidth / 2,
    y: target.y + mapRoomHeight / 2,
  };
  const path = connection.bent
    ? bentPath(start, end)
    : `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
  const className = [
    "live-map-link",
    connection.bent ? "is-bent" : "",
    connection.displacement ? "is-displacement" : "",
    connection.vertical ? "is-vertical" : "",
  ].filter(Boolean).join(" ");
  return (
    <g className={className} opacity={opacity}>
      <path d={path} />
    </g>
  );
}

function bentPath(source: MapPoint, target: MapPoint): string {
  const middleX = (source.x + target.x) / 2;
  const middleY = (source.y + target.y) / 2;
  const deltaX = target.x - source.x;
  const deltaY = target.y - source.y;
  const length = Math.max(Math.hypot(deltaX, deltaY), 1);
  const controlX = middleX - (deltaY / length) * 34;
  const controlY = middleY + (deltaX / length) * 34;
  return `M ${source.x} ${source.y} Q ${controlX} ${controlY} ${target.x} ${target.y}`;
}

function overlayRectsEqual(
  left: readonly MapOverlayRect[],
  right: readonly MapOverlayRect[],
): boolean {
  return left.length === right.length
    && left.every((rect, index) => {
      const candidate = right[index];
      return candidate !== undefined
        && Math.abs(rect.x - candidate.x) < 1
        && Math.abs(rect.y - candidate.y) < 1
        && Math.abs(rect.width - candidate.width) < 1
        && Math.abs(rect.height - candidate.height) < 1;
    });
}
