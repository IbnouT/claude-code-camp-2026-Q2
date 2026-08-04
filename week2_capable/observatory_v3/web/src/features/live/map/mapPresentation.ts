import type { MapConnection, MapGraph, MapViewport } from "./mapModel"
import type { MapFrame } from "./mapCamera"
import { mapRoomFootprint } from "./mapRoomFootprint"

export type MapMode = "grow" | "focus" | "lantern"
export type MapCameraMode = "follow" | "manual" | "fit"

export type MapPresentation = {
  visibleRoomIds: ReadonlySet<string>
  visibleConnectionIds: ReadonlySet<string>
  selectionPathRoomIds: readonly string[]
  focusShellRoomCount: number
  focusFillRoomCount: number
}

export type MapOverlayRect = {
  x: number
  y: number
  width: number
  height: number
}

export type MapFocusLayout = {
  frame: MapFrame
  overlayRects: readonly MapOverlayRect[]
  viewport: MapViewport
}

export type MapCameraEvent =
  | "session-change"
  | "drag"
  | "follow"
  | "fit"
  | "room-select"
  | "zoom"
  | "snapshot"

export const focusMaximumRoomCount = 18
export const focusAutoThreshold = 12
export const minimumMapZoom = 0.1
export const maximumMapZoom = 2

export function automaticMapMode(
  roomCount: number,
  chosenMode: MapMode | null
): MapMode {
  if (chosenMode !== null) return chosenMode
  return roomCount > focusAutoThreshold ? "focus" : "grow"
}

export function transitionMapCamera(
  current: MapCameraMode,
  event: MapCameraEvent
): MapCameraMode {
  if (event === "session-change" || event === "follow") return "follow"
  if (event === "drag") return "manual"
  if (event === "fit") return "fit"
  return current
}

export function changeMapZoom(
  current: number,
  direction: "in" | "out"
): number {
  const next = direction === "in" ? current * 1.25 : current / 1.25
  return clamp(next, minimumMapZoom, maximumMapZoom)
}

export function projectMapPresentation(
  graph: MapGraph,
  mode: MapMode,
  selectedRoomId: string | null,
  focusLayout?: MapFocusLayout
): MapPresentation {
  const everyRoom = new Set(graph.rooms.map(({ node }) => node.id))
  const adjacency = buildAdjacency(graph.connections)
  const selectionPathRoomIds =
    selectedRoomId === null ||
    graph.currentRoomId === null ||
    !everyRoom.has(selectedRoomId)
      ? []
      : (shortestPath(adjacency, graph.currentRoomId, selectedRoomId) ??
        (mode === "focus" ? [] : [selectedRoomId]))
  if (mode !== "focus" || graph.currentRoomId === null) {
    return {
      visibleRoomIds: everyRoom,
      visibleConnectionIds: new Set(graph.connections.map(({ id }) => id)),
      selectionPathRoomIds,
      focusShellRoomCount: 0,
      focusFillRoomCount: 0,
    }
  }

  const distances = graphDistances(adjacency, graph.currentRoomId)
  const baseVisible = focusRoomIds(graph, everyRoom, distances, focusLayout)
  const visibleRoomIds = new Set(baseVisible)
  if (
    selectedRoomId !== null &&
    everyRoom.has(selectedRoomId) &&
    selectionPathFitsFocusLayout(graph, selectionPathRoomIds, focusLayout)
  ) {
    addFocusSelectionPath(
      graph,
      baseVisible,
      visibleRoomIds,
      selectionPathRoomIds
    )
  }
  const shellRoomCount = [...baseVisible].filter((roomId) => {
    return visibleRoomIds.has(roomId)
  }).length
  const beforeFill = visibleRoomIds.size
  if (focusLayout !== undefined) {
    fillConnectedFocusRooms(graph, adjacency, visibleRoomIds, focusLayout)
  }
  pruneToCurrentComponent(adjacency, graph.currentRoomId, visibleRoomIds)

  const visibleConnectionIds = new Set(
    graph.connections.flatMap((connection) => {
      return visibleRoomIds.has(connection.source) &&
        visibleRoomIds.has(connection.target)
        ? [connection.id]
        : []
    })
  )
  return {
    visibleRoomIds,
    visibleConnectionIds,
    selectionPathRoomIds,
    focusShellRoomCount: shellRoomCount,
    focusFillRoomCount: visibleRoomIds.size - beforeFill,
  }
}

function addFocusSelectionPath(
  graph: MapGraph,
  baseVisible: ReadonlySet<string>,
  visibleRoomIds: Set<string>,
  selectionPathRoomIds: readonly string[]
): void {
  const union = new Set([...visibleRoomIds, ...selectionPathRoomIds])
  if (union.size <= focusMaximumRoomCount) {
    for (const roomId of selectionPathRoomIds) visibleRoomIds.add(roomId)
    return
  }
  if (selectionPathRoomIds.length > focusMaximumRoomCount) return

  visibleRoomIds.clear()
  for (const roomId of selectionPathRoomIds) visibleRoomIds.add(roomId)
  if (graph.currentRoomId === null) return
  const distances = graphDistances(
    buildAdjacency(graph.connections),
    graph.currentRoomId
  )
  const shells = new Map<number, string[]>()
  for (const { node } of graph.rooms) {
    if (!baseVisible.has(node.id)) continue
    const distance = distances.get(node.id)
    if (distance === undefined) continue
    const shell = shells.get(distance) ?? []
    shell.push(node.id)
    shells.set(distance, shell)
  }
  for (const distance of [...shells.keys()].sort((left, right) => {
    return left - right
  })) {
    const missing = (shells.get(distance) ?? []).filter((roomId) => {
      return !visibleRoomIds.has(roomId)
    })
    if (visibleRoomIds.size + missing.length > focusMaximumRoomCount) break
    for (const roomId of missing) visibleRoomIds.add(roomId)
  }
}

function selectionPathFitsFocusLayout(
  graph: MapGraph,
  selectionPathRoomIds: readonly string[],
  layout?: MapFocusLayout
): boolean {
  if (selectionPathRoomIds.length === 0) return false
  if (layout === undefined) return true
  const pathRoomIds = new Set(selectionPathRoomIds)
  return graph.rooms.every(({ node, point }) => {
    return (
      !pathRoomIds.has(node.id) ||
      roomFitsFocusPane(node, point, node.id === graph.currentRoomId, layout)
    )
  })
}

function fillConnectedFocusRooms(
  graph: MapGraph,
  adjacency: ReadonlyMap<string, Neighbor[]>,
  visibleRoomIds: Set<string>,
  layout: MapFocusLayout
): void {
  if (graph.currentRoomId === null) return
  const paneRoomIds = new Set(
    graph.rooms.flatMap(({ node, point }) => {
      return roomFitsFocusPane(
        node,
        point,
        node.id === graph.currentRoomId,
        layout
      )
        ? [node.id]
        : []
    })
  )
  paneRoomIds.add(graph.currentRoomId)
  const permittedRoomIds = new Set(visibleRoomIds)
  for (const { node, point } of graph.rooms) {
    if (
      !roomFitsFocusLayout(node, point, node.id === graph.currentRoomId, layout)
    ) {
      continue
    }
    const path = shortestPathWithin(
      adjacency,
      graph.currentRoomId,
      node.id,
      paneRoomIds
    )
    if (path === null) continue
    for (const roomId of path) permittedRoomIds.add(roomId)
  }

  let changed = true
  while (changed && visibleRoomIds.size < focusMaximumRoomCount) {
    changed = false
    for (const { node } of graph.rooms) {
      if (
        visibleRoomIds.size >= focusMaximumRoomCount ||
        visibleRoomIds.has(node.id) ||
        !permittedRoomIds.has(node.id)
      ) {
        continue
      }
      const adjacentToVisible = (adjacency.get(node.id) ?? []).some(
        ({ roomId }) => visibleRoomIds.has(roomId)
      )
      if (!adjacentToVisible) continue
      visibleRoomIds.add(node.id)
      changed = true
    }
  }
}

function pruneToCurrentComponent(
  adjacency: ReadonlyMap<string, Neighbor[]>,
  currentRoomId: string,
  visibleRoomIds: Set<string>
): void {
  const component = new Set<string>()
  const queue = visibleRoomIds.has(currentRoomId) ? [currentRoomId] : []
  while (queue.length > 0) {
    const roomId = queue.shift()
    if (roomId === undefined || component.has(roomId)) continue
    component.add(roomId)
    for (const neighbor of adjacency.get(roomId) ?? []) {
      if (
        visibleRoomIds.has(neighbor.roomId) &&
        !component.has(neighbor.roomId)
      ) {
        queue.push(neighbor.roomId)
      }
    }
  }
  for (const roomId of visibleRoomIds) {
    if (!component.has(roomId)) visibleRoomIds.delete(roomId)
  }
}

export function projectLanternOpacities(
  graph: MapGraph
): ReadonlyMap<string, number> {
  if (graph.currentRoomId === null) {
    return new Map(graph.rooms.map(({ node }) => [node.id, 1]))
  }
  const distances = graphDistances(
    buildAdjacency(graph.connections),
    graph.currentRoomId
  )
  return new Map(
    graph.rooms.map(({ node }) => {
      const distance = distances.get(node.id)
      if (distance === undefined) return [node.id, 0.12]
      if (distance === 0) return [node.id, 1]
      if (distance === 1) return [node.id, 0.8]
      if (distance === 2) return [node.id, 0.5]
      return [node.id, 0.12]
    })
  )
}

export function visibleRoomComponentSize(
  graph: MapGraph,
  visibleRoomIds: ReadonlySet<string>
): number {
  if (
    graph.currentRoomId === null ||
    !visibleRoomIds.has(graph.currentRoomId)
  ) {
    return 0
  }
  const adjacency = buildAdjacency(graph.connections)
  const component = new Set<string>()
  const queue = [graph.currentRoomId]
  while (queue.length > 0) {
    const roomId = queue.shift()
    if (roomId === undefined || component.has(roomId)) continue
    component.add(roomId)
    for (const neighbor of adjacency.get(roomId) ?? []) {
      if (
        visibleRoomIds.has(neighbor.roomId) &&
        !component.has(neighbor.roomId)
      ) {
        queue.push(neighbor.roomId)
      }
    }
  }
  return component.size
}

type Neighbor = {
  roomId: string
  firstSequence: number
  connectionId: string
}

function buildAdjacency(connections: MapConnection[]): Map<string, Neighbor[]> {
  const adjacency = new Map<string, Neighbor[]>()
  const add = (roomId: string, neighbor: Neighbor) => {
    const neighbors = adjacency.get(roomId) ?? []
    neighbors.push(neighbor)
    adjacency.set(roomId, neighbors)
  }
  for (const connection of connections) {
    add(connection.source, {
      roomId: connection.target,
      firstSequence: connection.firstSequence,
      connectionId: connection.id,
    })
    add(connection.target, {
      roomId: connection.source,
      firstSequence: connection.firstSequence,
      connectionId: connection.id,
    })
  }
  for (const neighbors of adjacency.values()) {
    neighbors.sort((left, right) => {
      return (
        left.firstSequence - right.firstSequence ||
        left.connectionId.localeCompare(right.connectionId) ||
        left.roomId.localeCompare(right.roomId)
      )
    })
  }
  return adjacency
}

function graphDistances(
  adjacency: Map<string, Neighbor[]>,
  source: string
): Map<string, number> {
  const distances = new Map([[source, 0]])
  const queue = [source]
  while (queue.length > 0) {
    const current = queue.shift()
    if (current === undefined) break
    const distance = distances.get(current)
    if (distance === undefined) continue
    for (const { roomId } of adjacency.get(current) ?? []) {
      if (distances.has(roomId)) continue
      distances.set(roomId, distance + 1)
      queue.push(roomId)
    }
  }
  return distances
}

function focusRoomIds(
  graph: MapGraph,
  everyRoom: ReadonlySet<string>,
  distances: ReadonlyMap<string, number>,
  focusLayout?: MapFocusLayout
): Set<string> {
  const visible = new Set<string>()
  const shells = new Map<number, string[]>()
  for (const roomId of everyRoom) {
    const distance = distances.get(roomId)
    if (distance === undefined) continue
    const shell = shells.get(distance) ?? []
    shell.push(roomId)
    shells.set(distance, shell)
  }
  for (const distance of [...shells.keys()].sort((left, right) => {
    return left - right
  })) {
    const shell = shells.get(distance) ?? []
    if (visible.size + shell.length > focusMaximumRoomCount) break
    if (focusLayout !== undefined) {
      const candidate = new Set(visible)
      for (const roomId of shell) candidate.add(roomId)
      if (
        visible.size > 0 &&
        !roomSetFitsFocusLayout(graph, candidate, focusLayout)
      ) {
        break
      }
    }
    for (const roomId of shell.sort()) visible.add(roomId)
  }
  if (visible.size === 0 && graph.currentRoomId !== null) {
    visible.add(graph.currentRoomId)
  }
  return visible
}

function roomSetFitsFocusLayout(
  graph: MapGraph,
  roomIds: ReadonlySet<string>,
  layout: MapFocusLayout
): boolean {
  return graph.rooms.every(({ node, point }) => {
    return (
      !roomIds.has(node.id) ||
      roomFitsFocusLayout(node, point, node.id === graph.currentRoomId, layout)
    )
  })
}

export function roomFitsFocusLayout(
  node: MapGraph["rooms"][number]["node"],
  point: { x: number; y: number },
  current: boolean,
  layout: MapFocusLayout
): boolean {
  const room = projectedRoomFootprint(node, point, current, layout)
  return (
    room !== null &&
    roomFitsFrame(room, layout.frame) &&
    layout.overlayRects.every((overlay) => {
      return !rectanglesIntersect(room, overlay)
    })
  )
}

export function roomFitsFocusPane(
  node: MapGraph["rooms"][number]["node"],
  point: { x: number; y: number },
  current: boolean,
  layout: MapFocusLayout
): boolean {
  const room = projectedRoomFootprint(node, point, current, layout)
  return room !== null && roomFitsFrame(room, layout.frame)
}

function projectedRoomFootprint(
  node: MapGraph["rooms"][number]["node"],
  point: { x: number; y: number },
  current: boolean,
  layout: MapFocusLayout
): MapOverlayRect | null {
  const { frame, viewport } = layout
  if (
    frame.width <= 0 ||
    frame.height <= 0 ||
    viewport.width <= 0 ||
    viewport.height <= 0
  ) {
    return null
  }
  const footprint = mapRoomFootprint(node, point, current)
  return {
    x: ((footprint.x - viewport.x) * frame.width) / viewport.width,
    y: ((footprint.y - viewport.y) * frame.height) / viewport.height,
    width: (footprint.width * frame.width) / viewport.width,
    height: (footprint.height * frame.height) / viewport.height,
  }
}

function roomFitsFrame(room: MapOverlayRect, frame: MapFrame): boolean {
  return (
    room.x >= 0 &&
    room.y >= 0 &&
    room.x + room.width <= frame.width &&
    room.y + room.height <= frame.height
  )
}

function rectanglesIntersect(
  left: MapOverlayRect,
  right: MapOverlayRect
): boolean {
  return (
    left.x < right.x + right.width &&
    left.x + left.width > right.x &&
    left.y < right.y + right.height &&
    left.y + left.height > right.y
  )
}

function shortestPath(
  adjacency: Map<string, Neighbor[]>,
  source: string,
  target: string
): string[] | null {
  if (source === target) return [source]
  const previous = new Map<string, string | null>([[source, null]])
  const queue = [source]
  while (queue.length > 0) {
    const current = queue.shift()
    if (current === undefined) break
    for (const { roomId } of adjacency.get(current) ?? []) {
      if (previous.has(roomId)) continue
      previous.set(roomId, current)
      if (roomId === target) {
        const path = [target]
        let cursor: string | null = current
        while (cursor !== null) {
          path.push(cursor)
          cursor = previous.get(cursor) ?? null
        }
        return path.reverse()
      }
      queue.push(roomId)
    }
  }
  return null
}

function shortestPathWithin(
  adjacency: ReadonlyMap<string, Neighbor[]>,
  source: string,
  target: string,
  allowedRoomIds: ReadonlySet<string>
): string[] | null {
  if (!allowedRoomIds.has(source) || !allowedRoomIds.has(target)) return null
  if (source === target) return [source]
  const previous = new Map<string, string | null>([[source, null]])
  const queue = [source]
  while (queue.length > 0) {
    const current = queue.shift()
    if (current === undefined) break
    for (const { roomId } of adjacency.get(current) ?? []) {
      if (!allowedRoomIds.has(roomId) || previous.has(roomId)) continue
      previous.set(roomId, current)
      if (roomId !== target) {
        queue.push(roomId)
        continue
      }
      const path = [target]
      let cursor: string | null = current
      while (cursor !== null) {
        path.push(cursor)
        cursor = previous.get(cursor) ?? null
      }
      return path.reverse()
    }
  }
  return null
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum)
}
