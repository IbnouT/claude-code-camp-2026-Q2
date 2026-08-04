import type {
  WorldEdge,
  WorldNode,
  WorldRoomDescription,
  WorldSighting,
} from "./world-types"

export type MapPoint = {
  x: number
  y: number
}

export type MapRoom = {
  node: WorldNode
  point: MapPoint
}

export type MapConnection = {
  id: string
  source: string
  target: string
  direction: string
  firstSequence: number
  displacement: boolean
  vertical: boolean
  bent: boolean
  oneWay: boolean
}

export type MapGraph = {
  rooms: MapRoom[]
  connections: MapConnection[]
  currentRoomId: string | null
  x: number
  y: number
  width: number
  height: number
}

export type MapViewport = {
  x: number
  y: number
  width: number
  height: number
}

export type InitialMapCamera = {
  viewport: MapViewport
  panning: boolean
}

type EdgeEvidence = WorldEdge & {
  firstSequence: number
}

type ConnectionEvidence = {
  id: string
  source: string
  target: string
  edges: EdgeEvidence[]
  firstSequence: number
}

export const mapRoomWidth = 64
export const mapRoomHeight = 64
export const mapColumnGap = 148
export const mapRowGap = 122
const inset = 92

const directionVectors: Record<string, MapPoint> = {
  north: { x: 0, y: -1 },
  northeast: { x: 1, y: -1 },
  east: { x: 1, y: 0 },
  southeast: { x: 1, y: 1 },
  south: { x: 0, y: 1 },
  southwest: { x: -1, y: 1 },
  west: { x: -1, y: 0 },
  northwest: { x: -1, y: -1 },
}

const directionAliases: Record<string, string> = {
  n: "north",
  ne: "northeast",
  e: "east",
  se: "southeast",
  s: "south",
  sw: "southwest",
  w: "west",
  nw: "northwest",
}

export function buildMapGraph(
  nodes: WorldNode[],
  edges: WorldEdge[]
): MapGraph {
  return buildMapGraphWithLayout(nodes, edges, "evidence")
}

export function reflowMapGraph(
  nodes: WorldNode[],
  edges: WorldEdge[]
): MapGraph {
  return buildMapGraphWithLayout(nodes, edges, "topology")
}

function buildMapGraphWithLayout(
  nodes: WorldNode[],
  edges: WorldEdge[],
  layout: "evidence" | "topology"
): MapGraph {
  const canonical = canonicalizeAtlasRooms(nodes, edges)
  const orderedNodes = [...canonical.nodes].sort(compareNodes)
  if (orderedNodes.length === 0) {
    return {
      rooms: [],
      connections: [],
      currentRoomId: null,
      x: 0,
      y: 0,
      width: 0,
      height: 0,
    }
  }

  const nodeIds = new Set(orderedNodes.map(({ id }) => id))
  const evidence = aggregateConnections(canonical.edges, nodeIds)
  const points =
    layout === "topology"
      ? reflowRooms(orderedNodes, evidence)
      : placeRooms(orderedNodes, evidence)
  const gridPoints = [...points.values()]
  const minimumX = Math.min(...gridPoints.map(({ x }) => x))
  const minimumY = Math.min(...gridPoints.map(({ y }) => y))
  const maximumX = Math.max(...gridPoints.map(({ x }) => x))
  const maximumY = Math.max(...gridPoints.map(({ y }) => y))
  const scaled = new Map(
    [...points].map(([id, point]) => [
      id,
      {
        x: point.x * mapColumnGap,
        y: point.y * mapRowGap,
      },
    ])
  )
  const connections = evidence.map((connection) => {
    const source = points.get(connection.source)
    const target = points.get(connection.target)
    const planarEdges = connection.edges.filter((edge) => {
      return vectorFor(edge.direction) !== null
    })
    const verticalEdges = connection.edges.filter((edge) => {
      return isVerticalDirection(edge.direction)
    })
    const vertical = verticalEdges.length > 0
    const displacement = planarEdges.length === 0 && verticalEdges.length === 0
    const bent =
      !displacement &&
      source !== undefined &&
      target !== undefined &&
      planarEdges.some((edge) => {
        const vector = vectorFor(edge.direction)
        if (vector === null) return false
        const followsAggregate = edge.source === connection.source
        const actualX = followsAggregate
          ? target.x - source.x
          : source.x - target.x
        const actualY = followsAggregate
          ? target.y - source.y
          : source.y - target.y
        return !preservesDirection({ x: actualX, y: actualY }, vector)
      })
    const directions = new Set(
      connection.edges.map((edge) => `${edge.source}:${edge.target}`)
    )
    return {
      id: connection.id,
      source: connection.source,
      target: connection.target,
      direction:
        verticalEdges[0]?.direction ??
        connection.edges[0]?.direction ??
        "unknown",
      firstSequence: connection.firstSequence,
      displacement,
      vertical,
      bent,
      oneWay: directions.size === 1,
    }
  })

  return {
    rooms: orderedNodes.map((node) => ({
      node,
      point: scaled.get(node.id) ?? { x: 0, y: 0 },
    })),
    connections,
    currentRoomId:
      orderedNodes.find(({ state }) => state === "current")?.id ?? null,
    x: minimumX * mapColumnGap - inset,
    y: minimumY * mapRowGap - inset,
    width: inset * 2 + (maximumX - minimumX) * mapColumnGap + mapRoomWidth,
    height: inset * 2 + (maximumY - minimumY) * mapRowGap + mapRoomHeight,
  }
}

function reflowRooms(
  nodes: WorldNode[],
  connections: ConnectionEvidence[]
): Map<string, MapPoint> {
  const candidates = [
    improveLayout(placeRooms(nodes, connections), connections),
    improveLayout(directionalReflowRooms(nodes, connections), connections),
  ]
  candidates.sort((left, right) => {
    return layoutPenalty(left, connections) - layoutPenalty(right, connections)
  })
  return candidates[0] ?? new Map()
}

function improveLayout(
  initial: Map<string, MapPoint>,
  connections: ConnectionEvidence[]
): Map<string, MapPoint> {
  let current = new Map(initial)
  let currentPenalty = layoutPenalty(current, connections)
  const nodeIds = [...current.keys()].sort()
  for (let pass = 0; pass < nodeIds.length; pass += 1) {
    let best = current
    let bestPenalty = currentPenalty
    for (let leftIndex = 0; leftIndex < nodeIds.length; leftIndex += 1) {
      const leftId = nodeIds[leftIndex]
      if (leftId === undefined) continue
      for (
        let rightIndex = leftIndex + 1;
        rightIndex < nodeIds.length;
        rightIndex += 1
      ) {
        const rightId = nodeIds[rightIndex]
        if (rightId === undefined) continue
        const leftPoint = current.get(leftId)
        const rightPoint = current.get(rightId)
        if (leftPoint === undefined || rightPoint === undefined) continue
        const candidate = new Map(current)
        candidate.set(leftId, rightPoint)
        candidate.set(rightId, leftPoint)
        const penalty = layoutPenalty(candidate, connections)
        if (penalty < bestPenalty) {
          best = candidate
          bestPenalty = penalty
        }
      }
    }
    if (nodeIds.length <= 40) {
      const occupied = new Set(
        [...current.values()].map(({ x, y }) => `${x}:${y}`)
      )
      for (const nodeId of nodeIds) {
        const point = current.get(nodeId)
        if (point === undefined) continue
        for (const candidatePoint of relocationPoints(current)) {
          if (occupied.has(`${candidatePoint.x}:${candidatePoint.y}`)) {
            continue
          }
          const candidate = new Map(current)
          candidate.set(nodeId, candidatePoint)
          const penalty = layoutPenalty(candidate, connections)
          if (penalty < bestPenalty) {
            best = candidate
            bestPenalty = penalty
          }
        }
      }
    }
    if (bestPenalty >= currentPenalty) break
    current = best
    currentPenalty = bestPenalty
  }
  return current
}

function relocationPoints(points: Map<string, MapPoint>): MapPoint[] {
  const occupied = [...points.values()]
  const minimumX = Math.min(...occupied.map(({ x }) => x)) - 1
  const maximumX = Math.max(...occupied.map(({ x }) => x)) + 1
  const minimumY = Math.min(...occupied.map(({ y }) => y)) - 1
  const maximumY = Math.max(...occupied.map(({ y }) => y)) + 1
  const candidates: MapPoint[] = []
  for (let y = minimumY; y <= maximumY; y += 1) {
    for (let x = minimumX; x <= maximumX; x += 1) {
      candidates.push({ x, y })
    }
  }
  return candidates
}

function directionalReflowRooms(
  nodes: WorldNode[],
  connections: ConnectionEvidence[]
): Map<string, MapPoint> {
  const points = new Map<string, MapPoint>()
  const adjacency = new Map<string, ConnectionEvidence[]>()
  for (const connection of connections) {
    adjacency.set(connection.source, [
      ...(adjacency.get(connection.source) ?? []),
      connection,
    ])
    adjacency.set(connection.target, [
      ...(adjacency.get(connection.target) ?? []),
      connection,
    ])
  }
  for (const grouped of adjacency.values()) {
    grouped.sort((left, right) => {
      return (
        left.firstSequence - right.firstSequence ||
        left.id.localeCompare(right.id)
      )
    })
  }

  for (const root of nodes) {
    if (points.has(root.id)) continue
    const rootPoint =
      points.size === 0
        ? { x: 0, y: 0 }
        : {
            x: Math.max(...[...points.values()].map(({ x }) => x)) + 3,
            y: 0,
          }
    points.set(root.id, rootPoint)
    const queue = [root.id]
    while (queue.length > 0) {
      const sourceId = queue.shift()
      if (sourceId === undefined) break
      const source = points.get(sourceId)
      if (source === undefined) continue
      for (const connection of adjacency.get(sourceId) ?? []) {
        const targetId =
          connection.source === sourceId ? connection.target : connection.source
        if (points.has(targetId)) continue
        const vector = connectionVector(connection, sourceId, targetId)
        const target =
          vector === null
            ? nearestFree(source, [...points.values()])
            : nearestDirectionalFree(source, vector, [...points.values()])
        points.set(targetId, target)
        queue.push(targetId)
      }
    }
  }
  return points
}

function layoutPenalty(
  points: Map<string, MapPoint>,
  connections: ConnectionEvidence[]
): number {
  let crossings = 0
  for (let leftIndex = 0; leftIndex < connections.length; leftIndex += 1) {
    const left = connections[leftIndex]
    if (left === undefined) continue
    for (
      let rightIndex = leftIndex + 1;
      rightIndex < connections.length;
      rightIndex += 1
    ) {
      const right = connections[rightIndex]
      if (
        right === undefined ||
        left.source === right.source ||
        left.source === right.target ||
        left.target === right.source ||
        left.target === right.target
      ) {
        continue
      }
      const leftSource = points.get(left.source)
      const leftTarget = points.get(left.target)
      const rightSource = points.get(right.source)
      const rightTarget = points.get(right.target)
      if (
        leftSource !== undefined &&
        leftTarget !== undefined &&
        rightSource !== undefined &&
        rightTarget !== undefined &&
        segmentsCross(leftSource, leftTarget, rightSource, rightTarget)
      ) {
        crossings += 1
      }
    }
  }
  const edgeSpan = connections.reduce((total, connection) => {
    const source = points.get(connection.source)
    const target = points.get(connection.target)
    if (source === undefined || target === undefined) return total
    return total + (target.x - source.x) ** 2 + (target.y - source.y) ** 2
  }, 0)
  const directionViolations = connections.reduce((total, connection) => {
    const source = points.get(connection.source)
    const target = points.get(connection.target)
    if (source === undefined || target === undefined) return total
    return (
      total +
      connection.edges.filter((edge) => {
        const vector = vectorFor(edge.direction)
        if (vector === null) return false
        const followsAggregate = edge.source === connection.source
        return !preservesDirection(
          {
            x: (target.x - source.x) * (followsAggregate ? 1 : -1),
            y: (target.y - source.y) * (followsAggregate ? 1 : -1),
          },
          vector
        )
      }).length
    )
  }, 0)
  const occupied = [...points.values()]
  const minimumX = Math.min(...occupied.map(({ x }) => x))
  const maximumX = Math.max(...occupied.map(({ x }) => x))
  const minimumY = Math.min(...occupied.map(({ y }) => y))
  const maximumY = Math.max(...occupied.map(({ y }) => y))
  const area = (maximumX - minimumX + 1) * (maximumY - minimumY + 1)
  return (
    crossings * 1_000_000 + directionViolations * 10_000 + edgeSpan * 10 + area
  )
}

function segmentsCross(
  a: MapPoint,
  b: MapPoint,
  c: MapPoint,
  d: MapPoint
): boolean {
  const orientation = (first: MapPoint, second: MapPoint, third: MapPoint) =>
    Math.sign(
      (second.x - first.x) * (third.y - first.y) -
        (second.y - first.y) * (third.x - first.x)
    )
  return (
    orientation(a, b, c) !== orientation(a, b, d) &&
    orientation(c, d, a) !== orientation(c, d, b)
  )
}

function connectionVector(
  connection: ConnectionEvidence,
  sourceId: string,
  targetId: string
): MapPoint | null {
  for (const edge of connection.edges) {
    const vector = vectorFor(edge.direction)
    if (vector === null) continue
    const followsTraversal =
      edge.source === sourceId && edge.target === targetId
    return {
      x: vector.x * (followsTraversal ? 1 : -1),
      y: vector.y * (followsTraversal ? 1 : -1),
    }
  }
  const vertical = connection.edges.find(({ direction }) => {
    return isVerticalDirection(direction)
  })
  if (vertical === undefined) return null
  return verticalPlacementVectors(vertical, targetId)[0]
}

function nearestDirectionalFree(
  anchor: MapPoint,
  vector: MapPoint,
  occupied: MapPoint[]
): MapPoint {
  const wanted = {
    x: anchor.x + vector.x,
    y: anchor.y + vector.y,
  }
  if (isFree(wanted, occupied)) return wanted
  for (let radius = 1; radius < 80; radius += 1) {
    const candidates: MapPoint[] = []
    for (let y = -radius; y <= radius; y += 1) {
      for (let x = -radius; x <= radius; x += 1) {
        if (Math.max(Math.abs(x), Math.abs(y)) !== radius) continue
        candidates.push({ x: wanted.x + x, y: wanted.y + y })
      }
    }
    candidates.sort((left, right) => {
      const leftDistance = Math.hypot(left.x - anchor.x, left.y - anchor.y)
      const rightDistance = Math.hypot(right.x - anchor.x, right.y - anchor.y)
      return (
        leftDistance - rightDistance || left.y - right.y || left.x - right.x
      )
    })
    const candidate = candidates.find((point) => {
      return (
        preservesDirection(
          {
            x: point.x - anchor.x,
            y: point.y - anchor.y,
          },
          vector
        ) && isFree(point, occupied)
      )
    })
    if (candidate !== undefined) return candidate
  }
  return nearestFree(wanted, occupied)
}

export function canonicalNodeId(node: WorldNode): string {
  return node.atlas === null || node.atlas === undefined
    ? node.id
    : `vnum:${node.atlas.vnum}`
}

function canonicalizeAtlasRooms(
  nodes: WorldNode[],
  edges: WorldEdge[]
): { nodes: WorldNode[]; edges: WorldEdge[] } {
  const canonicalIds = new Map<string, string>()
  const canonicalNodes = new Map<string, WorldNode>()
  for (const node of [...nodes].sort(compareNodes)) {
    const canonicalId = canonicalNodeId(node)
    canonicalIds.set(node.id, canonicalId)
    const existing = canonicalNodes.get(canonicalId)
    if (existing === undefined) {
      canonicalNodes.set(canonicalId, { ...node, id: canonicalId })
      continue
    }
    canonicalNodes.set(canonicalId, {
      ...existing,
      description: latestDescription(existing, node),
      exits: [...new Set([...existing.exits, ...node.exits])].sort(),
      mobs: [...new Set([...existing.mobs, ...node.mobs])].sort(),
      objects: [...new Set([...existing.objects, ...node.objects])].sort(),
      mob_sightings: mergeSightings(existing.mob_sightings, node.mob_sightings),
      object_sightings: mergeSightings(
        existing.object_sightings,
        node.object_sightings
      ),
      visits: existing.visits + node.visits,
      evidence: [...new Set([...existing.evidence, ...node.evidence])].sort(
        (left, right) => left - right
      ),
      first_seq: Math.min(existing.first_seq, node.first_seq),
      last_seq: Math.max(existing.last_seq, node.last_seq),
      state: mergedState(existing.state, node.state),
      confidence: existing.confidence,
      method: "atlas-vnum-canonical",
    })
  }
  const canonicalEdges = edges.flatMap((edge) => {
    const source = canonicalIds.get(edge.source)
    const target = canonicalIds.get(edge.target)
    if (source === undefined || target === undefined || source === target) {
      return []
    }
    return [
      {
        ...edge,
        id: `${source}:${target}:${edge.direction}:${edge.id}`,
        source,
        target,
      },
    ]
  })
  return {
    nodes: [...canonicalNodes.values()],
    edges: canonicalEdges,
  }
}

function latestDescription(
  existing: WorldNode,
  candidate: WorldNode
): WorldRoomDescription | null {
  if (candidate.description === null) return existing.description
  if (existing.description === null) return candidate.description
  return candidate.last_seq >= existing.last_seq
    ? candidate.description
    : existing.description
}

function mergeSightings(
  existing: WorldSighting[],
  candidate: WorldSighting[]
): WorldSighting[] {
  const merged = new Map<string, WorldSighting>()
  for (const sighting of [...existing, ...candidate]) {
    const current = merged.get(sighting.name)
    if (current === undefined) {
      merged.set(sighting.name, sighting)
      continue
    }
    merged.set(sighting.name, {
      name: sighting.name,
      count: current.count + sighting.count,
      first_seq: Math.min(current.first_seq, sighting.first_seq),
      last_seq: Math.max(current.last_seq, sighting.last_seq),
      evidence: [...new Set([...current.evidence, ...sighting.evidence])].sort(
        (left, right) => left - right
      ),
    })
  }
  return [...merged.values()].sort((left, right) => {
    return (
      left.first_seq - right.first_seq || left.name.localeCompare(right.name)
    )
  })
}

function mergedState(
  left: WorldNode["state"],
  right: WorldNode["state"]
): WorldNode["state"] {
  if (left === "current" || right === "current") return "current"
  if (left === "candidate" || right === "candidate") return "candidate"
  return "observed"
}

export function initialMapCamera(
  graph: MapGraph,
  frameWidth = 1_600,
  frameHeight = 900,
  minimumReadableScale = 0.75
): InitialMapCamera {
  const width = Math.min(
    Math.max(graph.width, frameWidth),
    frameWidth / minimumReadableScale
  )
  const height = Math.min(
    Math.max(graph.height, frameHeight),
    frameHeight / minimumReadableScale
  )
  const current = graph.rooms.find(({ node }) => {
    return node.id === graph.currentRoomId
  })?.point
  const center =
    current === undefined
      ? {
          x: graph.x + graph.width / 2,
          y: graph.y + graph.height / 2,
        }
      : {
          x: current.x + mapRoomWidth / 2,
          y: current.y + mapRoomHeight / 2,
        }
  return {
    viewport: centerMapViewport(graph, { width, height }, center),
    panning: graph.width > width || graph.height > height,
  }
}

export function centerMapViewport(
  graph: MapGraph,
  size: Pick<MapViewport, "width" | "height">,
  center: MapPoint
): MapViewport {
  const x =
    graph.width <= size.width
      ? graph.x - (size.width - graph.width) / 2
      : clamp(
          center.x - size.width / 2,
          graph.x,
          graph.x + graph.width - size.width
        )
  const y =
    graph.height <= size.height
      ? graph.y - (size.height - graph.height) / 2
      : clamp(
          center.y - size.height / 2,
          graph.y,
          graph.y + graph.height - size.height
        )
  return { x, y, width: size.width, height: size.height }
}

export function mapDragScale(
  contentExtent: number,
  viewportExtent: number
): number {
  if (viewportExtent <= 0) return 1
  const completeRangeFromCenter =
    (2 * Math.max(contentExtent - viewportExtent, 0)) / viewportExtent
  return Math.max(completeRangeFromCenter * 1.05, 1)
}

function aggregateConnections(
  edges: WorldEdge[],
  nodeIds: Set<string>
): ConnectionEvidence[] {
  const pairs = new Map<string, EdgeEvidence[]>()
  for (const edge of edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) continue
    const pair = [edge.source, edge.target].sort()
    const id = `${pair[0]}|${pair[1]}`
    const grouped = pairs.get(id) ?? []
    grouped.push({
      ...edge,
      direction: normalizeDirection(edge.direction),
      firstSequence: firstEvidence(edge),
    })
    pairs.set(id, grouped)
  }

  return [...pairs]
    .map(([id, grouped]) => {
      grouped.sort(compareEdges)
      const first = grouped[0]
      return {
        id,
        source: first?.source ?? "",
        target: first?.target ?? "",
        edges: grouped,
        firstSequence: first?.firstSequence ?? Number.MAX_SAFE_INTEGER,
      }
    })
    .sort((left, right) => {
      return (
        left.firstSequence - right.firstSequence ||
        left.id.localeCompare(right.id)
      )
    })
}

function placeRooms(
  nodes: WorldNode[],
  connections: ConnectionEvidence[]
): Map<string, MapPoint> {
  const points = new Map<string, MapPoint>()
  const place = (id: string, point: MapPoint) => {
    points.set(id, point)
  }

  place(nodes[0].id, { x: 0, y: 0 })
  for (const node of nodes.slice(1)) {
    const candidates = connections.filter((connection) => {
      return (
        connection.firstSequence <= node.first_seq &&
        (connection.source === node.id || connection.target === node.id)
      )
    })
    const planar = candidates.find((connection) => {
      const other =
        connection.source === node.id ? connection.target : connection.source
      return (
        points.has(other) &&
        connection.edges.some((edge) => vectorFor(edge.direction) !== null)
      )
    })
    if (planar !== undefined) {
      const edge = planar.edges.find((candidate) => {
        return vectorFor(candidate.direction) !== null
      })
      const otherId = planar.source === node.id ? planar.target : planar.source
      const other = points.get(otherId)
      if (edge !== undefined && other !== undefined) {
        const vector = vectorFor(edge.direction)
        if (vector !== null) {
          const nodeIsTarget = edge.target === node.id
          const placementVector = {
            x: vector.x * (nodeIsTarget ? 1 : -1),
            y: vector.y * (nodeIsTarget ? 1 : -1),
          }
          const wanted = {
            x: other.x + placementVector.x,
            y: other.y + placementVector.y,
          }
          openInsertionSlot(
            wanted,
            otherId,
            placementVector,
            points,
            connections,
            node.first_seq
          )
          place(node.id, wanted)
          continue
        }
      }
    }

    const vertical = candidates.find((connection) => {
      const other =
        connection.source === node.id ? connection.target : connection.source
      return (
        points.has(other) &&
        connection.edges.every(({ direction }) => {
          return isVerticalDirection(direction)
        })
      )
    })
    if (vertical !== undefined) {
      const edge = vertical.edges.find(({ direction }) => {
        return isVerticalDirection(direction)
      })
      const otherId =
        vertical.source === node.id ? vertical.target : vertical.source
      const other = points.get(otherId)
      if (edge !== undefined && other !== undefined) {
        const vectors = verticalPlacementVectors(edge, node.id)
        let placed = false
        for (const vector of vectors) {
          const wanted = {
            x: other.x + vector.x,
            y: other.y + vector.y,
          }
          try {
            openInsertionSlot(
              wanted,
              otherId,
              vector,
              points,
              connections,
              node.first_seq
            )
            place(node.id, wanted)
            placed = true
            break
          } catch (error) {
            if (
              !(error instanceof Error) ||
              !error.message.startsWith("Foreign map component occupies")
            ) {
              throw error
            }
          }
        }
        if (placed) continue
        place(
          node.id,
          nearestVerticalFree(other, vectors, [...points.values()])
        )
        continue
      }
    }

    const displacement = candidates.find((connection) => {
      const other =
        connection.source === node.id ? connection.target : connection.source
      return (
        points.has(other) &&
        connection.edges.every(({ direction }) => {
          return (
            vectorFor(direction) === null && !isVerticalDirection(direction)
          )
        })
      )
    })
    if (displacement !== undefined) {
      const otherId =
        displacement.source === node.id
          ? displacement.target
          : displacement.source
      const other = points.get(otherId)
      if (other !== undefined) {
        place(node.id, nearestFree(other, [...points.values()]))
        continue
      }
    }

    const maximumX = Math.max(...[...points.values()].map(({ x }) => x))
    const clusterIndex = points.size
    const target = {
      x: maximumX + 3,
      y: (clusterIndex % 3) - 1,
    }
    place(node.id, nearestFree(target, [...points.values()]))
  }
  return points
}

function openInsertionSlot(
  wanted: MapPoint,
  anchor: string,
  vector: MapPoint,
  points: Map<string, MapPoint>,
  connections: ConnectionEvidence[],
  throughSequence: number
): void {
  const occupant = [...points].find(([, point]) => {
    return samePoint(point, wanted)
  })?.[0]
  if (occupant === undefined) return

  const shiftVector =
    vector.x !== 0 && vector.y !== 0 ? { x: 0, y: vector.y } : vector
  const shiftedIds = dependentSet(
    anchor,
    wanted,
    shiftVector,
    points,
    connections,
    throughSequence
  )
  if (!shiftedIds.has(occupant)) {
    throw new Error(`Foreign map component occupies ${wanted.x}:${wanted.y}`)
  }
  const maximumBlockedDistances =
    shiftedIds.size * (points.size - shiftedIds.size)
  for (
    let distance = 1;
    distance <= maximumBlockedDistances + 1;
    distance += 1
  ) {
    if (!shiftIsFree(shiftedIds, shiftVector, distance, points)) continue
    const shifted = [...shiftedIds].sort().map((id) => {
      const point = points.get(id)
      if (point === undefined) {
        throw new Error(`Missing placed room ${id}`)
      }
      return [
        id,
        {
          x: point.x + shiftVector.x * distance,
          y: point.y + shiftVector.y * distance,
        },
      ] as const
    })
    for (const [id, point] of shifted) points.set(id, point)
    return
  }

  throw new Error(`Unable to open map cell ${wanted.x}:${wanted.y}`)
}

function dependentSet(
  anchor: string,
  wanted: MapPoint,
  shiftVector: MapPoint,
  points: Map<string, MapPoint>,
  connections: ConnectionEvidence[],
  throughSequence: number
): Set<string> {
  const adjacency = new Map<string, string[]>()
  for (const connection of connections) {
    if (
      connection.firstSequence > throughSequence ||
      !points.has(connection.source) ||
      !points.has(connection.target)
    ) {
      continue
    }
    const sourceNeighbors = adjacency.get(connection.source) ?? []
    sourceNeighbors.push(connection.target)
    adjacency.set(connection.source, sourceNeighbors)
    const targetNeighbors = adjacency.get(connection.target) ?? []
    targetNeighbors.push(connection.source)
    adjacency.set(connection.target, targetNeighbors)
  }
  for (const neighbors of adjacency.values()) neighbors.sort()

  const component = new Set([anchor])
  const queue = [anchor]
  while (queue.length > 0) {
    const current = queue.shift()
    if (current === undefined) break
    for (const neighbor of adjacency.get(current) ?? []) {
      if (component.has(neighbor)) continue
      component.add(neighbor)
      queue.push(neighbor)
    }
  }
  return new Set(
    [...component].filter((id) => {
      const point = points.get(id)
      return point !== undefined && atOrBeyond(point, wanted, shiftVector)
    })
  )
}

function shiftIsFree(
  shiftedIds: Set<string>,
  vector: MapPoint,
  distance: number,
  points: Map<string, MapPoint>
): boolean {
  const fixed = [...points].filter(([id]) => !shiftedIds.has(id))
  return [...shiftedIds].every((id) => {
    const point = points.get(id)
    if (point === undefined) return false
    const target = {
      x: point.x + vector.x * distance,
      y: point.y + vector.y * distance,
    }
    return fixed.every(([, fixedPoint]) => !samePoint(target, fixedPoint))
  })
}

function atOrBeyond(
  point: MapPoint,
  boundary: MapPoint,
  vector: MapPoint
): boolean {
  if (vector.x !== 0) {
    return (point.x - boundary.x) * vector.x >= 0
  }
  return (point.y - boundary.y) * vector.y >= 0
}

function samePoint(left: MapPoint, right: MapPoint): boolean {
  return left.x === right.x && left.y === right.y
}

function nearestFree(target: MapPoint, occupied: MapPoint[]): MapPoint {
  if (isFree(target, occupied)) return target
  for (let radius = 1; radius < 80; radius += 1) {
    for (let y = -radius; y <= radius; y += 1) {
      for (let x = -radius; x <= radius; x += 1) {
        if (Math.max(Math.abs(x), Math.abs(y)) !== radius) continue
        const candidate = { x: target.x + x, y: target.y + y }
        if (isFree(candidate, occupied)) return candidate
      }
    }
  }
  return { x: target.x, y: target.y + 80 }
}

function nearestVerticalFree(
  anchor: MapPoint,
  vectors: MapPoint[],
  occupied: MapPoint[]
): MapPoint {
  for (let distance = 1; distance < 80; distance += 1) {
    for (const vector of vectors) {
      const candidate = {
        x: anchor.x + vector.x,
        y: anchor.y + vector.y * distance,
      }
      if (isFree(candidate, occupied)) return candidate
    }
  }
  return {
    x: anchor.x + vectors[0].x,
    y: anchor.y + vectors[0].y * 80,
  }
}

function isFree(candidate: MapPoint, occupied: MapPoint[]): boolean {
  const horizontalClearance = mapRoomWidth + 20
  const verticalClearance = mapRoomHeight + 20
  return occupied.every((point) => {
    const horizontal = Math.abs(candidate.x - point.x) * mapColumnGap
    const vertical = Math.abs(candidate.y - point.y) * mapRowGap
    return horizontal >= horizontalClearance || vertical >= verticalClearance
  })
}

function preservesDirection(actual: MapPoint, expected: MapPoint): boolean {
  if (expected.x === 0) {
    return actual.y * expected.y > 0
  }
  if (expected.y === 0) {
    return actual.x * expected.x > 0
  }
  return actual.x * expected.x > 0 && actual.y * expected.y > 0
}

function vectorFor(direction: string): MapPoint | null {
  return directionVectors[normalizeDirection(direction)] ?? null
}

function verticalPlacementVectors(
  edge: EdgeEvidence,
  nodeId: string
): [MapPoint, MapPoint] {
  const targetDirection = edge.direction === "down" ? 1 : -1
  const nodeIsTarget = edge.target === nodeId
  const vertical = targetDirection * (nodeIsTarget ? 1 : -1)
  const horizontal = nodeIsTarget ? 1 : -1
  return [
    { x: horizontal, y: vertical },
    { x: -horizontal, y: vertical },
  ]
}

function isVerticalDirection(direction: string): boolean {
  const normalized = normalizeDirection(direction)
  return normalized === "up" || normalized === "down"
}

function normalizeDirection(direction: string): string {
  const normalized = direction.trim().toLowerCase()
  return directionAliases[normalized] ?? normalized
}

function firstEvidence(edge: WorldEdge): number {
  return edge.evidence.length > 0
    ? Math.min(...edge.evidence)
    : Number.MAX_SAFE_INTEGER
}

function compareEdges(left: EdgeEvidence, right: EdgeEvidence): number {
  return (
    left.firstSequence - right.firstSequence || left.id.localeCompare(right.id)
  )
}

function compareNodes(left: WorldNode, right: WorldNode): number {
  return left.first_seq - right.first_seq || left.id.localeCompare(right.id)
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum)
}
