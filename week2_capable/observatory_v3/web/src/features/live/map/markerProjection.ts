import type { WorldEdge, WorldFrontier, WorldNode } from "./world-types"
import {
  canonicalNodeId,
  mapRoomHeight,
  mapRoomWidth,
  type MapPoint,
  type MapRoom,
} from "./mapModel"

export type PlanarDirection =
  | "north"
  | "northeast"
  | "east"
  | "southeast"
  | "south"
  | "southwest"
  | "west"
  | "northwest"

export type VerticalDirection = "up" | "down"
export type VerticalMarkerState = "traversed" | "frontier"
export type MapMarkerKind = "frontier" | "vertical" | "visits"

export type FrontierMarker = {
  id: string
  source: string
  direction: PlanarDirection
  start: MapPoint
  end: MapPoint
  evidence: number[]
}

export type VerticalMarker = {
  direction: VerticalDirection
  state: VerticalMarkerState
}

export type MapEvidenceProjection = {
  frontiers: FrontierMarker[]
  verticalByRoom: ReadonlyMap<string, VerticalMarker[]>
  markerKinds: ReadonlySet<MapMarkerKind>
}

const frontierLength = 26

const planarVectors: Record<PlanarDirection, MapPoint> = {
  north: { x: 0, y: -1 },
  northeast: { x: 1, y: -1 },
  east: { x: 1, y: 0 },
  southeast: { x: 1, y: 1 },
  south: { x: 0, y: 1 },
  southwest: { x: -1, y: 1 },
  west: { x: -1, y: 0 },
  northwest: { x: -1, y: -1 },
}

const directionAliases: Record<string, PlanarDirection | VerticalDirection> = {
  n: "north",
  north: "north",
  ne: "northeast",
  northeast: "northeast",
  e: "east",
  east: "east",
  se: "southeast",
  southeast: "southeast",
  s: "south",
  south: "south",
  sw: "southwest",
  southwest: "southwest",
  w: "west",
  west: "west",
  nw: "northwest",
  northwest: "northwest",
  u: "up",
  up: "up",
  d: "down",
  down: "down",
}

export function projectMapEvidence(
  nodes: WorldNode[],
  edges: WorldEdge[],
  frontier: WorldFrontier[],
  rooms: MapRoom[]
): MapEvidenceProjection {
  const canonicalIds = new Map(
    nodes.map((node) => [node.id, canonicalNodeId(node)])
  )
  const roomPoints = new Map(rooms.map(({ node, point }) => [node.id, point]))
  const frontierEvidence = new Map<string, number[]>()
  const verticalFrontier = new Set<string>()

  for (const item of frontier) {
    const source = canonicalIds.get(item.source)
    const direction = normalizeDirection(item.direction)
    if (source === undefined || direction === null) continue
    if (isVertical(direction)) {
      verticalFrontier.add(verticalKey(source, direction))
      continue
    }
    const point = roomPoints.get(source)
    if (point === undefined) continue
    const key = `${source}:${direction}`
    frontierEvidence.set(
      key,
      mergeEvidence(frontierEvidence.get(key) ?? [], item.evidence)
    )
  }

  const frontiers = [...frontierEvidence]
    .map(([key, evidence]) => {
      const separator = key.lastIndexOf(":")
      const source = key.slice(0, separator)
      const direction = key.slice(separator + 1) as PlanarDirection
      const point = roomPoints.get(source)
      if (point === undefined) {
        throw new Error(`Missing map point for frontier source ${source}`)
      }
      const { start, end } = frontierGeometry(point, direction)
      return {
        id: `frontier:${source}:${direction}`,
        source,
        direction,
        start,
        end,
        evidence,
      }
    })
    .sort((left, right) => left.id.localeCompare(right.id))

  const traversedVertical = verticalTraversals(nodes, edges, canonicalIds)
  const verticalByRoom = new Map<string, VerticalMarker[]>()
  for (const { node } of rooms) {
    const directions = new Set(
      node.exits
        .map(normalizeDirection)
        .filter((direction): direction is VerticalDirection => {
          return direction !== null && isVertical(direction)
        })
    )
    const markers = [...directions].sort(verticalOrder).map((direction) => {
      const key = verticalKey(node.id, direction)
      return {
        direction,
        state:
          verticalFrontier.has(key) || !traversedVertical.has(key)
            ? "frontier"
            : "traversed",
      } satisfies VerticalMarker
    })
    if (markers.length > 0) verticalByRoom.set(node.id, markers)
  }

  const markerKinds = new Set<MapMarkerKind>()
  if (frontiers.length > 0) markerKinds.add("frontier")
  if (verticalByRoom.size > 0) markerKinds.add("vertical")
  if (rooms.some(({ node }) => node.visits > 1)) markerKinds.add("visits")

  return { frontiers, verticalByRoom, markerKinds }
}

export function normalizeDirection(
  direction: string
): PlanarDirection | VerticalDirection | null {
  return directionAliases[direction.trim().toLowerCase()] ?? null
}

export function frontierGeometry(
  room: MapPoint,
  direction: PlanarDirection
): { start: MapPoint; end: MapPoint } {
  const vector = planarVectors[direction]
  const center = {
    x: room.x + mapRoomWidth / 2,
    y: room.y + mapRoomHeight / 2,
  }
  const start = {
    x: center.x + (vector.x * mapRoomWidth) / 2,
    y: center.y + (vector.y * mapRoomHeight) / 2,
  }
  const length = Math.hypot(vector.x, vector.y)
  return {
    start,
    end: {
      x: start.x + (vector.x / length) * frontierLength,
      y: start.y + (vector.y / length) * frontierLength,
    },
  }
}

function verticalTraversals(
  nodes: WorldNode[],
  edges: WorldEdge[],
  canonicalIds: ReadonlyMap<string, string>
): Set<string> {
  const exits = new Map(
    nodes.map((node) => [node.id, new Set(node.exits.map(normalizeDirection))])
  )
  const traversed = new Set<string>()
  for (const edge of edges) {
    const direction = normalizeDirection(edge.direction)
    const source = canonicalIds.get(edge.source)
    const target = canonicalIds.get(edge.target)
    if (
      direction === null ||
      !isVertical(direction) ||
      source === undefined ||
      target === undefined
    ) {
      continue
    }
    traversed.add(verticalKey(source, direction))
    const reverse = direction === "up" ? "down" : "up"
    if (exits.get(edge.target)?.has(reverse)) {
      traversed.add(verticalKey(target, reverse))
    }
  }
  return traversed
}

function verticalKey(source: string, direction: VerticalDirection): string {
  return `${source}:${direction}`
}

function isVertical(
  direction: PlanarDirection | VerticalDirection
): direction is VerticalDirection {
  return direction === "up" || direction === "down"
}

function verticalOrder(
  left: VerticalDirection,
  right: VerticalDirection
): number {
  if (left === right) return 0
  return left === "up" ? -1 : 1
}

function mergeEvidence(left: number[], right: number[]): number[] {
  return [...new Set([...left, ...right])].sort(
    (first, second) => first - second
  )
}
