import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react"

import type { LiveJourney } from "@/data/live-view"
import { cn } from "@/lib/utils"

import { CombatPanel } from "../combat-panel"
import { ThoughtDock } from "../thought-dock"
import { MapContinuation } from "./map-continuation"
import { MapFrontier } from "./map-frontier"
import { MapLegend } from "./map-legend"
import { MapRoom } from "./map-room"
import { MapToolbar } from "./map-toolbar"
import { RoomInspector } from "./room-inspector"
import {
  fitMapCameraToSafeFrame,
  keepSelectedRoomOutsidePanel,
  mapCameraViewport,
  mapContentExtent,
  mapOverlaySafeBand,
  resolveFollowMapCameraAnchor,
  roomCenter,
  isContinuousMapTransition,
  stepCriticallyDampedMapCenter,
  zoomMapCamera,
  clampFocusCamera,
  type MapCameraView,
  type MapFrame,
  type MapSafeInsets,
} from "./mapCamera"
import {
  buildMapGraph,
  canonicalNodeId,
  mapRoomHeight,
  mapRoomWidth,
  reflowMapGraph,
  type MapConnection,
  type MapGraph,
  type MapPoint,
} from "./mapModel"
import {
  automaticMapMode,
  maximumMapZoom,
  minimumMapZoom,
  projectLanternOpacities,
  projectMapPresentation,
  type MapCameraMode,
  type MapMode,
  type MapOverlayRect,
} from "./mapPresentation"
import { mapRoomFootprint } from "./mapRoomFootprint"
import { projectFocusContinuations } from "./focusContinuation"
import { projectMapEvidence } from "./markerProjection"
import { projectMapLegend } from "./mapLegend"
import { projectRoomInspector } from "./roomInspector"

type LiveMapProps = {
  view: LiveJourney | null
  reconnecting: boolean
  selectedRoomId: string | null
  onSelectRoom: (roomId: string | null) => void
}

const defaultFrame: MapFrame = { width: 1600, height: 900 }
const emptyIds = new Set<string>()
const defaultSafeInsets: MapSafeInsets = {
  top: 8,
  right: 8,
  bottom: 8,
  left: 8,
}

function bentPath(source: MapPoint, target: MapPoint): string {
  const midX = (source.x + target.x) / 2
  const midY = (source.y + target.y) / 2
  const dx = target.x - source.x
  const dy = target.y - source.y
  const length = Math.hypot(dx, dy) || 1
  const controlX = midX + (-dy / length) * 34
  const controlY = midY + (dx / length) * 34
  return `M ${source.x} ${source.y} Q ${controlX} ${controlY} ${target.x} ${target.y}`
}

const MapLink = memo(function MapLink({
  connection,
  points,
  opacity,
}: {
  connection: MapConnection
  points: ReadonlyMap<string, MapPoint>
  opacity: number
}) {
  const source = points.get(connection.source)
  const target = points.get(connection.target)
  if (source === undefined || target === undefined) return null
  const from = {
    x: source.x + mapRoomWidth / 2,
    y: source.y + mapRoomHeight / 2,
  }
  const to = { x: target.x + mapRoomWidth / 2, y: target.y + mapRoomHeight / 2 }
  return (
    <g
      opacity={opacity}
      className={cn(
        "[&>path]:fill-none [&>path]:stroke-(--map-link) [&>path]:stroke-2",
        connection.bent && "[&>path]:stroke-[#8a6d3b]",
        (connection.displacement || connection.vertical) &&
          "[&>path]:[stroke-dasharray:4_5]"
      )}
    >
      <path
        vectorEffect="non-scaling-stroke"
        d={
          connection.bent
            ? bentPath(from, to)
            : `M ${from.x} ${from.y} L ${to.x} ${to.y}`
        }
      />
    </g>
  )
})

/**
 * The learned world map: rooms placed by retained evidence, camera
 * follow, focus and lantern presentations, and the room inspector.
 */
function LiveMap({
  view,
  reconnecting,
  selectedRoomId,
  onSelectRoom,
}: LiveMapProps) {
  const stageRef = useRef<HTMLDivElement>(null)
  const [frame, setFrame] = useState<MapFrame>(defaultFrame)
  const [cameraView, setCameraView] = useState<MapCameraView>({
    center: { x: 0, y: 0 },
    scale: 1,
  })
  const [cameraMode, setCameraMode] = useState<MapCameraMode>("follow")
  const [chosenMode, setChosenMode] = useState<MapMode | null>(null)
  const [thoughtExpanded, setThoughtExpanded] = useState(
    () => typeof window === "undefined" || window.innerWidth > 700
  )
  const [legendExpanded, setLegendExpanded] = useState(false)
  const [panHintVisible, setPanHintVisible] = useState(true)
  const [dragging, setDragging] = useState(false)
  const [safeInsets, setSafeInsets] = useState<MapSafeInsets>(defaultSafeInsets)
  const [focusOverlayRects, setFocusOverlayRects] = useState<MapOverlayRect[]>(
    []
  )
  const [markerOverlayRects, setMarkerOverlayRects] = useState<
    MapOverlayRect[]
  >([])
  const [reflowRevision, setReflowRevision] = useState(0)

  const dragRef = useRef<{
    pointerId: number
    clientX: number
    clientY: number
    center: MapPoint
    moved: boolean
  } | null>(null)
  const suppressClickRef = useRef(false)
  const cameraViewRef = useRef(cameraView)
  cameraViewRef.current = cameraView
  const selectedRoomIdRef = useRef(selectedRoomId)
  selectedRoomIdRef.current = selectedRoomId
  const followVelocityRef = useRef<MapPoint>({ x: 0, y: 0 })
  const previousRoomRef = useRef<string | null>(null)
  const followInitializedRef = useRef(false)

  const world = view?.world ?? null
  const graph: MapGraph | null = useMemo(() => {
    if (world === null) return null
    return reflowRevision > 0
      ? reflowMapGraph(world.nodes, world.edges)
      : buildMapGraph(world.nodes, world.edges)
  }, [world, reflowRevision])

  const points = useMemo(() => {
    const map = new Map<string, MapPoint>()
    for (const room of graph?.rooms ?? []) map.set(room.node.id, room.point)
    return map
  }, [graph])

  const mode = automaticMapMode(graph?.rooms.length ?? 0, chosenMode)
  const baseViewport = mapCameraViewport(cameraView, frame)
  const inspectorOpen = selectedRoomId !== null
  const selectedPoint =
    selectedRoomId === null ? undefined : points.get(selectedRoomId)
  const viewport =
    inspectorOpen && selectedPoint !== undefined
      ? keepSelectedRoomOutsidePanel(
          baseViewport,
          frame,
          selectedPoint,
          typeof window !== "undefined" && window.innerWidth <= 700
            ? {
                right: 0,
                bottom: Math.min(frame.height * 0.55, 420) + 14,
              }
            : { right: 318, bottom: 0 }
        )
      : baseViewport

  const presentation = useMemo(() => {
    if (graph === null) return null
    const currentCenter = roomCenter(graph, graph.currentRoomId ?? "") ?? {
      x: graph.x + graph.width / 2,
      y: graph.y + graph.height / 2,
    }
    return projectMapPresentation(graph, mode, selectedRoomId, {
      frame,
      overlayRects: focusOverlayRects,
      viewport: mapCameraViewport(
        { center: currentCenter, scale: cameraView.scale },
        frame
      ),
    })
  }, [graph, mode, selectedRoomId, frame, focusOverlayRects, cameraView.scale])
  const lanternOpacities = useMemo(
    () => (graph === null ? new Map() : projectLanternOpacities(graph)),
    [graph]
  )
  const evidence = useMemo(
    () =>
      world === null || graph === null
        ? null
        : projectMapEvidence(
            world.nodes,
            world.edges,
            world.frontier,
            graph.rooms
          ),
    [world, graph]
  )
  const beaconRoomIds = useMemo(() => {
    const ids = new Set<string>()
    for (const beacon of world?.objective_beacons ?? []) {
      const node = world?.nodes.find((entry) => entry.id === beacon.node_id)
      if (node !== undefined) ids.add(canonicalNodeId(node))
    }
    return ids
  }, [world])

  const visibleRoomIds = presentation?.visibleRoomIds ?? emptyIds
  const visibleConnectionIds = presentation?.visibleConnectionIds ?? emptyIds

  const inspector = useMemo(() => {
    if (world === null || selectedRoomId === null) return null
    const node = world.nodes.find(
      (entry) => canonicalNodeId(entry) === selectedRoomId
    )
    if (node === undefined) return null
    return projectRoomInspector(
      node,
      world.nodes,
      world.frontier,
      view?.room_economics ?? []
    )
  }, [world, selectedRoomId, view?.room_economics])

  const legendEntries = useMemo(() => {
    if (graph === null) return []
    if (evidence === null) return []
    return projectMapLegend({
      rooms: graph.rooms.map((room) => room.node),
      visibleRoomIds,
      currentRoomId: graph.currentRoomId,
      selectedRoomId,
      combat: Boolean(view?.combat),
      beaconRoomIds,
      evidence,
    })
  }, [graph, visibleRoomIds, selectedRoomId, beaconRoomIds, evidence, view])

  const overlayBand = mapOverlaySafeBand({
    thoughtVisible: view?.agent_thought != null,
    thoughtExpanded,
    legendExpanded,
    legendEntries: legendEntries.length,
  })

  const visibleFootprints = useMemo(() => {
    if (graph === null) return []
    return graph.rooms
      .filter((room) => visibleRoomIds.has(room.node.id))
      .map((room) =>
        mapRoomFootprint(
          room.node,
          room.point,
          room.node.id === graph.currentRoomId
        )
      )
  }, [graph, visibleRoomIds])

  const focusContinuations = useMemo(() => {
    if (graph === null || mode !== "focus") return []
    return projectFocusContinuations(graph, visibleRoomIds, viewport)
  }, [graph, mode, visibleRoomIds, viewport])

  // Stable identity keeps every memoized room from re-rendering when the
  // selection toggles; the ref carries the current selection for the toggle.
  const selectRoom = useCallback(
    (roomId: string) => {
      onSelectRoom(roomId === selectedRoomIdRef.current ? null : roomId)
    },
    [onSelectRoom]
  )

  const fitCamera = useCallback(() => {
    if (graph === null) return
    const markerPoints = (evidence?.frontiers ?? []).map((marker) => ({
      point: marker.end,
      source: marker.source,
    }))
    const pathIds = presentation?.selectionPathRoomIds ?? []
    const ids =
      pathIds.length > 1 ? new Set(pathIds) : (visibleRoomIds as Set<string>)
    const extent = mapContentExtent(graph, ids, markerPoints)
    setCameraView(fitMapCameraToSafeFrame(extent, frame, safeInsets))
  }, [graph, evidence, presentation, visibleRoomIds, frame, safeInsets])

  // Camera follow: snap on entry, damped glide between connected rooms.
  useEffect(() => {
    if (graph === null || cameraMode !== "follow") return
    const currentId = graph.currentRoomId
    if (currentId === null) return
    const target = roomCenter(graph, currentId)
    if (target === null) return
    const previous = previousRoomRef.current
    previousRoomRef.current = currentId
    if (!followInitializedRef.current) {
      followInitializedRef.current = true
      setCameraView((current) => ({ ...current, center: target }))
      return
    }
    if (previous === currentId) return
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    if (
      reduced ||
      typeof requestAnimationFrame === "undefined" ||
      !isContinuousMapTransition(graph, previous, currentId)
    ) {
      followVelocityRef.current = { x: 0, y: 0 }
      setCameraView((current) => ({ ...current, center: target }))
      return
    }
    const anchor = resolveFollowMapCameraAnchor(
      cameraViewRef.current,
      target,
      frame,
      null
    )
    let raf = 0
    let last = performance.now()
    const stepFrame = (now: number) => {
      const dt = Math.min(Math.max((now - last) / 1000, 0), 0.1)
      last = now
      const motion = stepCriticallyDampedMapCenter(
        {
          center: cameraViewRef.current.center,
          velocity: followVelocityRef.current,
        },
        anchor.center,
        dt
      )
      followVelocityRef.current = motion.velocity
      setCameraView((current) => ({ ...current, center: motion.center }))
      const distance = Math.hypot(
        motion.center.x - anchor.center.x,
        motion.center.y - anchor.center.y
      )
      const speed = Math.hypot(motion.velocity.x, motion.velocity.y)
      if (distance > 0.05 || speed > 0.05) {
        raf = requestAnimationFrame(stepFrame)
      }
    }
    raf = requestAnimationFrame(stepFrame)
    return () => cancelAnimationFrame(raf)
  }, [graph, cameraMode, frame])

  // Frame measurement and overlay occluders, split per family.
  const measureStage = useCallback(() => {
    const stage = stageRef.current
    if (stage === null) return
    const bounds = stage.getBoundingClientRect()
    setFrame((current) =>
      Math.abs(current.width - bounds.width) < 1 &&
      Math.abs(current.height - bounds.height) < 1
        ? current
        : { width: bounds.width, height: bounds.height }
    )
    const insets = { ...defaultSafeInsets }
    const collect = (selector: string): MapOverlayRect[] => {
      const rects: MapOverlayRect[] = []
      for (const occluder of stage.querySelectorAll<HTMLElement>(selector)) {
        const rect = occluder.getBoundingClientRect()
        rects.push({
          x: Math.max(rect.left - bounds.left - 8, 0),
          y: Math.max(rect.top - bounds.top - 8, 0),
          width: rect.width + 16,
          height: rect.height + 16,
        })
        const edge = occluder.getAttribute("data-map-overlay-edge")
        if (edge === "top") {
          insets.top = Math.max(insets.top, rect.bottom - bounds.top + 8)
        }
        if (edge === "right") {
          insets.right = Math.max(insets.right, bounds.right - rect.left + 8)
        }
        if (edge === "bottom") {
          insets.bottom = Math.max(insets.bottom, bounds.bottom - rect.top + 8)
        }
        if (edge === "left") {
          insets.left = Math.max(insets.left, rect.right - bounds.left + 8)
        }
      }
      return rects
    }
    const sameRects = (
      current: MapOverlayRect[],
      next: MapOverlayRect[]
    ): boolean =>
      current.length === next.length &&
      current.every(
        (rect, index) =>
          Math.abs(rect.x - next[index].x) < 1 &&
          Math.abs(rect.y - next[index].y) < 1 &&
          Math.abs(rect.width - next[index].width) < 1 &&
          Math.abs(rect.height - next[index].height) < 1
      )
    const focusRects = collect("[data-map-focus-occluder]")
    const markerRects = collect("[data-map-marker-occluder]")
    setSafeInsets((current) =>
      current.top === insets.top &&
      current.right === insets.right &&
      current.bottom === insets.bottom &&
      current.left === insets.left
        ? current
        : insets
    )
    setFocusOverlayRects((current) =>
      sameRects(current, focusRects) ? current : focusRects
    )
    setMarkerOverlayRects((current) =>
      sameRects(current, markerRects) ? current : markerRects
    )
  }, [])
  useLayoutEffect(() => {
    const stage = stageRef.current
    if (stage === null) return
    measureStage()
    const observer = new ResizeObserver(measureStage)
    observer.observe(stage)
    return () => observer.disconnect()
  }, [measureStage])
  useLayoutEffect(() => {
    measureStage()
  }, [measureStage, inspectorOpen, legendExpanded, thoughtExpanded, mode])

  // Escape closes the selection first, then collapses the legend.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return
      if (selectedRoomId !== null) {
        event.preventDefault()
        event.stopImmediatePropagation()
        onSelectRoom(null)
        return
      }
      if (
        legendExpanded &&
        document.querySelector('[role="dialog"]') === null
      ) {
        event.preventDefault()
        event.stopImmediatePropagation()
        setLegendExpanded(false)
      }
    }
    const onPointerDown = (event: PointerEvent) => {
      if (selectedRoomId === null) return
      const target = event.target as Element | null
      if (
        target?.closest(
          '[aria-label^="Room inspector"], [data-room-id], [data-map-focus-occluder], [data-map-marker-occluder]'
        )
      ) {
        return
      }
      onSelectRoom(null)
    }
    window.addEventListener("keydown", onKeyDown, true)
    window.addEventListener("pointerdown", onPointerDown, true)
    return () => {
      window.removeEventListener("keydown", onKeyDown, true)
      window.removeEventListener("pointerdown", onPointerDown, true)
    }
  }, [selectedRoomId, legendExpanded, onSelectRoom])

  // Focus keeps the agent framed: a manual camera re-follows when the
  // current room changes.
  const manualRoomRef = useRef<string | null>(null)
  useEffect(() => {
    if (graph === null) return
    const currentId = graph.currentRoomId
    if (cameraMode !== "manual" || mode !== "focus") {
      manualRoomRef.current = currentId
      return
    }
    if (manualRoomRef.current !== null && manualRoomRef.current !== currentId) {
      setCameraMode("follow")
    }
    manualRoomRef.current = currentId
  }, [graph, cameraMode, mode])

  const panning = mode !== "lantern"

  const onPointerDown = (event: React.PointerEvent) => {
    suppressClickRef.current = false
    dragRef.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      center: cameraViewRef.current.center,
      moved: false,
    }
  }
  const onPointerMove = (event: React.PointerEvent) => {
    const drag = dragRef.current
    if (drag === null || event.pointerId !== drag.pointerId) return
    const dx = event.clientX - drag.clientX
    const dy = event.clientY - drag.clientY
    if (!drag.moved && Math.hypot(dx, dy) < 4) return
    if (!drag.moved) {
      drag.moved = true
      drag.clientX = event.clientX
      drag.clientY = event.clientY
      drag.center = cameraViewRef.current.center
      ;(event.currentTarget as Element).setPointerCapture?.(event.pointerId)
      setDragging(true)
      setPanHintVisible(false)
      setCameraMode("manual")
      if (mode === "lantern") setChosenMode("grow")
      return
    }
    const bounds = stageRef.current?.getBoundingClientRect()
    if (bounds === undefined || bounds.width === 0) return
    const unitsPerPixel = viewport.width / bounds.width
    const next = {
      x: drag.center.x - dx * unitsPerPixel,
      y: drag.center.y - dy * unitsPerPixel,
    }
    setCameraView((current) => {
      let candidate = { ...current, center: next }
      if (mode === "focus" && graph?.currentRoomId != null) {
        const agent = roomCenter(graph, graph.currentRoomId)
        if (agent !== null && presentation !== null) {
          const extent = mapContentExtent(
            graph,
            presentation.visibleRoomIds,
            []
          )
          candidate = clampFocusCamera(candidate, agent, extent, frame)
        }
      }
      return candidate
    })
  }
  const onPointerUp = (event: React.PointerEvent) => {
    const drag = dragRef.current
    if (drag === null || event.pointerId !== drag.pointerId) return
    if (drag.moved) suppressClickRef.current = true
    dragRef.current = null
    setDragging(false)
  }

  const roomOpacity = (roomId: string): number => {
    if (mode !== "lantern") return 1
    if (roomId === graph?.currentRoomId || roomId === selectedRoomId) return 1
    return (lanternOpacities.get(roomId) as number | undefined) ?? 0.12
  }

  if (view === null || graph === null) {
    return (
      <output className="place-self-center text-[13px] text-content-muted">
        {reconnecting
          ? "World evidence is reconnecting."
          : "Loading learned world…"}
      </output>
    )
  }
  if (graph.rooms.length === 0) {
    return (
      <output className="place-self-center text-[13px] text-content-muted">
        Waiting for the first observed room.
      </output>
    )
  }

  return (
    <div
      ref={stageRef}
      className="relative grid min-h-0 min-w-0 overflow-hidden"
      style={{ ["--live-map-overlay-safe-band" as string]: `${overlayBand}px` }}
    >
      <MapToolbar
        camera={cameraMode}
        mode={mode}
        selectedRoomId={selectedRoomId}
        zoom={cameraView.scale}
        minimumZoom={minimumMapZoom}
        maximumZoom={maximumMapZoom}
        onCameraChange={(camera) => {
          if (mode === "lantern" && camera !== "follow") {
            setChosenMode("grow")
          }
          followVelocityRef.current = { x: 0, y: 0 }
          if (camera === "fit") {
            fitCamera()
            setCameraMode("fit")
            return
          }
          setCameraMode(camera)
        }}
        onModeChange={(nextMode) => {
          setChosenMode(nextMode)
          if (
            (nextMode === "focus" || nextMode === "lantern") &&
            graph.currentRoomId !== null
          ) {
            const center = roomCenter(graph, graph.currentRoomId)
            if (center !== null) {
              setCameraView((current) => ({ ...current, center }))
            }
            setCameraMode("follow")
          }
        }}
        onReflow={() => {
          if (world === null) return
          const next = reflowMapGraph(world.nodes, world.edges)
          const ids = new Set(next.rooms.map((room) => room.node.id))
          const extent = mapContentExtent(next, ids, [])
          setCameraView(fitMapCameraToSafeFrame(extent, frame, safeInsets))
          setCameraMode("fit")
          setPanHintVisible(false)
          setReflowRevision((revision) => revision + 1)
        }}
        onZoom={(direction) =>
          setCameraView((current) => zoomMapCamera(current, direction))
        }
      />
      {/* oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- the svg is the pan surface, native drag starts must be suppressed on it */}
      <svg
        role="application"
        aria-label={`Learned world, ${graph.rooms.length} rooms`}
        preserveAspectRatio="xMidYMid meet"
        viewBox={`${viewport.x} ${viewport.y} ${viewport.width} ${viewport.height}`}
        className={cn(
          "h-full min-h-0 w-full place-self-center select-none",
          panning && "cursor-grab touch-none",
          dragging && "cursor-grabbing"
        )}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClickCapture={(event) => {
          if (suppressClickRef.current) {
            suppressClickRef.current = false
            event.preventDefault()
            event.stopPropagation()
          }
        }}
        onDragStart={(event) => event.preventDefault()}
      >
        <defs>
          <radialGradient id="live-current-room-glow">
            <stop offset="0%" stopColor="#4fd6c9" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#4fd6c9" stopOpacity="0" />
          </radialGradient>
          {mode === "lantern" && graph.currentRoomId !== null ? (
            <radialGradient
              id="live-map-lantern-gradient"
              gradientUnits="userSpaceOnUse"
              cx={(roomCenter(graph, graph.currentRoomId)?.x ?? 0).toString()}
              cy={(roomCenter(graph, graph.currentRoomId)?.y ?? 0).toString()}
              r="280"
            >
              <stop
                offset="0%"
                className="[stop-color:var(--content-primary)]"
                stopOpacity="0.07"
              />
              <stop
                offset="100%"
                className="[stop-color:var(--content-primary)]"
                stopOpacity="0"
              />
            </radialGradient>
          ) : null}
        </defs>
        {mode === "lantern" && graph.currentRoomId !== null ? (
          <rect
            x={viewport.x}
            y={viewport.y}
            width={viewport.width}
            height={viewport.height}
            fill="url(#live-map-lantern-gradient)"
            pointerEvents="none"
          />
        ) : null}
        <g>
          {graph.connections
            .filter((connection) => visibleConnectionIds.has(connection.id))
            .map((connection) => (
              <MapLink
                key={connection.id}
                connection={connection}
                points={points}
                opacity={Math.max(
                  roomOpacity(connection.source),
                  roomOpacity(connection.target)
                )}
              />
            ))}
        </g>
        <g>
          {(evidence?.frontiers ?? [])
            .filter((marker) => visibleRoomIds.has(marker.source))
            .map((marker) => (
              <g key={marker.id} opacity={roomOpacity(marker.source)}>
                <MapFrontier marker={marker} />
              </g>
            ))}
        </g>
        <g>
          {graph.rooms
            .filter((room) => visibleRoomIds.has(room.node.id))
            .map((room) => (
              <g key={room.node.id} opacity={roomOpacity(room.node.id)}>
                <MapRoom
                  node={room.node}
                  point={room.point}
                  current={room.node.id === graph.currentRoomId}
                  selected={room.node.id === selectedRoomId}
                  combat={
                    Boolean(view.combat) && room.node.id === graph.currentRoomId
                  }
                  beacon={beaconRoomIds.has(room.node.id)}
                  verticalMarkers={
                    evidence?.verticalByRoom.get(room.node.id) ?? []
                  }
                  onSelect={selectRoom}
                />
              </g>
            ))}
        </g>
      </svg>
      {mode === "focus" && focusContinuations.length > 0 ? (
        <div
          aria-label="Learned map continuations"
          className="pointer-events-none absolute inset-0 z-[4]"
        >
          {focusContinuations.map((marker) => (
            <MapContinuation
              key={`${marker.edge}:${marker.hiddenRoomId}`}
              frame={frame}
              marker={marker}
              overlayRects={markerOverlayRects}
              safeInsets={defaultSafeInsets}
              viewport={viewport}
              visibleRoomFootprints={visibleFootprints}
            />
          ))}
        </div>
      ) : null}
      {inspector !== null ? (
        <RoomInspector room={inspector} onClose={() => onSelectRoom(null)} />
      ) : null}
      <CombatPanel episode={view.combat_episode} />
      <ThoughtDock
        expanded={thoughtExpanded}
        thought={view.agent_thought}
        onToggle={() => setThoughtExpanded((current) => !current)}
      />
      <MapLegend
        entries={legendEntries}
        expanded={legendExpanded}
        inspectorOpen={inspector !== null}
        onToggle={() => setLegendExpanded((current) => !current)}
      />
      {panning && panHintVisible && !dragging ? (
        <p className="pointer-events-none absolute bottom-[68px] left-1/2 -translate-x-1/2 rounded-[9px] border border-line bg-surface px-2.5 py-[7px] text-[10px] text-content-muted">
          Drag to explore the learned world.
        </p>
      ) : null}
      {reconnecting ? (
        <output className="absolute right-[18px] bottom-[calc(var(--live-map-overlay-safe-band,0px)+10px)] rounded-[9px] border border-line bg-surface px-2.5 py-[7px] text-[10px] text-warning">
          Showing the latest world while evidence reconnects.
        </output>
      ) : null}
    </div>
  )
}

export { LiveMap, type LiveMapProps }
