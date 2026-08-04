import {
  mapRoomHeight,
  mapRoomWidth,
  type MapGraph,
  type MapPoint,
  type MapViewport,
} from "./mapModel"
import type { MapFrame, MapSafeInsets } from "./mapCamera"
import type { MapOverlayRect } from "./mapPresentation"
import { mapRoomFootprint, type MapRoomFootprint } from "./mapRoomFootprint"

export type FocusContinuationEdge = "top" | "right" | "bottom" | "left"

export type FocusContinuation = {
  edge: FocusContinuationEdge
  hiddenRoomId: string
  point: MapPoint
}

export type FocusContinuationOverlayBox = {
  left: number
  top: number
  width: number
  height: number
}

const edgeOrder: FocusContinuationEdge[] = ["top", "right", "bottom", "left"]

export function projectFocusContinuations(
  graph: MapGraph,
  visibleRoomIds: ReadonlySet<string>,
  viewport: MapViewport
): FocusContinuation[] {
  const roomById = new Map(
    graph.rooms.map(({ node, point }) => [
      node.id,
      mapRoomFootprint(node, point, node.id === graph.currentRoomId),
    ])
  )
  const hiddenRoomIds = new Set<string>()
  for (const connection of graph.connections) {
    const sourceVisible = visibleRoomIds.has(connection.source)
    const targetVisible = visibleRoomIds.has(connection.target)
    if (sourceVisible === targetVisible) continue
    hiddenRoomIds.add(sourceVisible ? connection.target : connection.source)
  }

  const byEdge = new Map<
    FocusContinuationEdge,
    FocusContinuation & { overshoot: number }
  >()
  for (const hiddenRoomId of [...hiddenRoomIds].sort()) {
    const footprint = roomById.get(hiddenRoomId)
    if (footprint === undefined) continue
    const room = graph.rooms.find(({ node }) => node.id === hiddenRoomId)
    if (room === undefined) continue
    const point = {
      x: room.point.x + mapRoomWidth / 2,
      y: room.point.y + mapRoomHeight / 2,
    }
    const projection = projectFootprintToEdge(footprint, viewport)
    if (projection === null) continue
    const candidate = {
      edge: projection.edge,
      hiddenRoomId,
      point,
      overshoot: projection.overshoot,
    }
    const existing = byEdge.get(candidate.edge)
    if (
      existing === undefined ||
      candidate.overshoot < existing.overshoot ||
      (candidate.overshoot === existing.overshoot &&
        candidate.hiddenRoomId < existing.hiddenRoomId)
    ) {
      byEdge.set(candidate.edge, candidate)
    }
  }

  return edgeOrder.flatMap((edge) => {
    const marker = byEdge.get(edge)
    if (marker === undefined) return []
    return [
      {
        edge: marker.edge,
        hiddenRoomId: marker.hiddenRoomId,
        point: marker.point,
      },
    ]
  })
}

export function projectFocusContinuationOverlay(
  marker: FocusContinuation,
  viewport: MapViewport,
  frame: MapFrame,
  insets: MapSafeInsets,
  visibleRoomFootprints: readonly MapRoomFootprint[],
  overlayRects: readonly MapOverlayRect[] = []
): FocusContinuationOverlayBox | null {
  if (
    viewport.width <= 0 ||
    viewport.height <= 0 ||
    frame.width <= 0 ||
    frame.height <= 0
  ) {
    return null
  }
  const safe = {
    top: clamp(insets.top, 0, frame.height),
    right: clamp(frame.width - insets.right, 0, frame.width),
    bottom: clamp(frame.height - insets.bottom, 0, frame.height),
    left: clamp(insets.left, 0, frame.width),
  }
  if (safe.right <= safe.left || safe.bottom <= safe.top) return null
  const scale = {
    x: frame.width / viewport.width,
    y: frame.height / viewport.height,
  }
  const projectedPoint = {
    x: (marker.point.x - viewport.x) * scale.x,
    y: (marker.point.y - viewport.y) * scale.y,
  }
  const occupied = [
    ...visibleRoomFootprints.map((footprint) => ({
      left: (footprint.x - viewport.x) * scale.x,
      top: (footprint.y - viewport.y) * scale.y,
      width: footprint.width * scale.x,
      height: footprint.height * scale.y,
    })),
    ...overlayRects.map((rect) => ({
      left: rect.x,
      top: rect.y,
      width: rect.width,
      height: rect.height,
    })),
  ]
  const alongX = marker.edge === "top" || marker.edge === "bottom"
  const preferred = alongX ? projectedPoint.x : projectedPoint.y
  const minimum = (alongX ? safe.left : safe.top) + 12
  const maximum = (alongX ? safe.right : safe.bottom) - 12
  if (maximum < minimum) return null

  for (const cross of nearestEdgePositions(preferred, minimum, maximum)) {
    const box = continuationBox(marker.edge, cross, safe)
    if (occupied.every((room) => !rectanglesIntersect(box, room, 3))) {
      return box
    }
  }
  return null
}

function projectFootprintToEdge(
  footprint: MapRoomFootprint,
  viewport: MapViewport
): { edge: FocusContinuationEdge; overshoot: number } | null {
  const candidates: {
    edge: FocusContinuationEdge
    overshoot: number
    vertical: boolean
  }[] = []
  if (footprint.y < viewport.y) {
    candidates.push({
      edge: "top",
      overshoot: viewport.y - footprint.y,
      vertical: true,
    })
  }
  if (footprint.x + footprint.width > viewport.x + viewport.width) {
    candidates.push({
      edge: "right",
      overshoot: footprint.x + footprint.width - viewport.x - viewport.width,
      vertical: false,
    })
  }
  if (footprint.y + footprint.height > viewport.y + viewport.height) {
    candidates.push({
      edge: "bottom",
      overshoot: footprint.y + footprint.height - viewport.y - viewport.height,
      vertical: true,
    })
  }
  if (footprint.x < viewport.x) {
    candidates.push({
      edge: "left",
      overshoot: viewport.x - footprint.x,
      vertical: false,
    })
  }
  if (candidates.length === 0) {
    const center = {
      x: viewport.x + viewport.width / 2,
      y: viewport.y + viewport.height / 2,
    }
    const delta = {
      x: footprint.x + footprint.width / 2 - center.x,
      y: footprint.y + footprint.height / 2 - center.y,
    }
    if (Math.abs(delta.y) >= Math.abs(delta.x)) {
      return {
        edge: delta.y < 0 ? "top" : "bottom",
        overshoot: 0,
      }
    }
    return {
      edge: delta.x < 0 ? "left" : "right",
      overshoot: 0,
    }
  }
  candidates.sort((left, right) => {
    return (
      left.overshoot - right.overshoot ||
      Number(right.vertical) - Number(left.vertical) ||
      edgeOrder.indexOf(left.edge) - edgeOrder.indexOf(right.edge)
    )
  })
  return candidates[0] ?? null
}

function nearestEdgePositions(
  preferred: number,
  minimum: number,
  maximum: number
): number[] {
  const origin = clamp(preferred, minimum, maximum)
  const positions = [origin]
  const maximumOffset = Math.max(origin - minimum, maximum - origin)
  for (let offset = 4; offset <= maximumOffset + 4; offset += 4) {
    if (origin - offset >= minimum) positions.push(origin - offset)
    if (origin + offset <= maximum) positions.push(origin + offset)
  }
  if (!positions.includes(minimum)) positions.push(minimum)
  if (!positions.includes(maximum)) positions.push(maximum)
  return positions
}

function continuationBox(
  edge: FocusContinuationEdge,
  cross: number,
  safe: { top: number; right: number; bottom: number; left: number }
): FocusContinuationOverlayBox {
  if (edge === "top") {
    return { left: cross - 12, top: safe.top, width: 24, height: 50 }
  }
  if (edge === "right") {
    return {
      left: safe.right - 50,
      top: cross - 12,
      width: 50,
      height: 24,
    }
  }
  if (edge === "bottom") {
    return {
      left: cross - 12,
      top: safe.bottom - 50,
      width: 24,
      height: 50,
    }
  }
  return { left: safe.left, top: cross - 12, width: 50, height: 24 }
}

function rectanglesIntersect(
  left: FocusContinuationOverlayBox,
  right: FocusContinuationOverlayBox,
  gap: number
): boolean {
  return (
    left.left < right.left + right.width + gap &&
    left.left + left.width + gap > right.left &&
    left.top < right.top + right.height + gap &&
    left.top + left.height + gap > right.top
  )
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum)
}
