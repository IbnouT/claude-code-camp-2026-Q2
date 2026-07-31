import type {
  MapConnection,
  MapGraph,
} from "./mapModel";

export type MapMode = "grow" | "focus" | "lantern";
export type MapCameraMode = "follow" | "manual" | "fit";

export type FocusBoundary = {
  roomId: string;
  count: number;
  expanded: boolean;
};

export type MapPresentation = {
  visibleRoomIds: ReadonlySet<string>;
  visibleConnectionIds: ReadonlySet<string>;
  boundaries: FocusBoundary[];
  selectionPathRoomIds: readonly string[];
};

export type MapCameraEvent =
  | "session-change"
  | "drag"
  | "follow"
  | "fit"
  | "room-select"
  | "zoom"
  | "snapshot";

export const focusRadius = 2;
export const focusAutoThreshold = 12;
export const minimumMapZoom = 0.1;
export const maximumMapZoom = 2;

export function automaticMapMode(
  roomCount: number,
  chosenMode: MapMode | null,
): MapMode {
  if (chosenMode !== null) return chosenMode;
  return roomCount > focusAutoThreshold ? "focus" : "grow";
}

export function transitionMapCamera(
  current: MapCameraMode,
  event: MapCameraEvent,
): MapCameraMode {
  if (event === "session-change" || event === "follow") return "follow";
  if (event === "drag") return "manual";
  if (event === "fit") return "fit";
  return current;
}

export function changeMapZoom(
  current: number,
  direction: "in" | "out",
): number {
  const next = direction === "in" ? current * 1.25 : current / 1.25;
  return clamp(next, minimumMapZoom, maximumMapZoom);
}

export function projectMapPresentation(
  graph: MapGraph,
  mode: MapMode,
  selectedRoomId: string | null,
  expandedRoomIds: ReadonlySet<string>,
): MapPresentation {
  const everyRoom = new Set(graph.rooms.map(({ node }) => node.id));
  const adjacency = buildAdjacency(graph.connections);
  const selectionPathRoomIds = selectedRoomId === null
    || graph.currentRoomId === null
    || !everyRoom.has(selectedRoomId)
    ? []
    : shortestPath(adjacency, graph.currentRoomId, selectedRoomId)
      ?? [selectedRoomId];
  if (mode !== "focus" || graph.currentRoomId === null) {
    return {
      visibleRoomIds: everyRoom,
      visibleConnectionIds: new Set(
        graph.connections.map(({ id }) => id),
      ),
      boundaries: [],
      selectionPathRoomIds,
    };
  }

  const distances = graphDistances(adjacency, graph.currentRoomId);
  const baseVisible = new Set(
    [...everyRoom].filter((roomId) => {
      return (distances.get(roomId) ?? Number.POSITIVE_INFINITY)
        <= focusRadius;
    }),
  );
  const boundaryNeighbors = new Map<string, string[]>();
  for (const roomId of baseVisible) {
    if (distances.get(roomId) !== focusRadius) continue;
    const hidden = unique(
      (adjacency.get(roomId) ?? [])
        .map(({ roomId: neighbor }) => neighbor)
        .filter((neighbor) => !baseVisible.has(neighbor)),
    );
    if (hidden.length > 0) boundaryNeighbors.set(roomId, hidden);
  }

  const visibleRoomIds = new Set(baseVisible);
  for (const roomId of expandedRoomIds) {
    for (const neighbor of boundaryNeighbors.get(roomId) ?? []) {
      visibleRoomIds.add(neighbor);
    }
  }
  if (selectedRoomId !== null && everyRoom.has(selectedRoomId)) {
    for (const roomId of selectionPathRoomIds) visibleRoomIds.add(roomId);
  }

  const visibleConnectionIds = new Set(
    graph.connections.flatMap((connection) => {
      return visibleRoomIds.has(connection.source)
          && visibleRoomIds.has(connection.target)
        ? [connection.id]
        : [];
    }),
  );
  const boundaries = [...boundaryNeighbors]
    .map(([roomId, hidden]) => ({
      roomId,
      count: hidden.length,
      expanded: expandedRoomIds.has(roomId),
    }))
    .sort((left, right) => left.roomId.localeCompare(right.roomId));

  return {
    visibleRoomIds,
    visibleConnectionIds,
    boundaries,
    selectionPathRoomIds,
  };
}

export function lanternOpacity(
  graph: MapGraph,
  roomId: string,
  radius = 280,
): number {
  const current = graph.rooms.find(({ node }) => {
    return node.id === graph.currentRoomId;
  });
  const room = graph.rooms.find(({ node }) => node.id === roomId);
  if (current === undefined || room === undefined || radius <= 0) return 1;
  const distance = Math.hypot(
    room.point.x - current.point.x,
    room.point.y - current.point.y,
  );
  return clamp(1 - distance / radius, 0, 1);
}

type Neighbor = {
  roomId: string;
  firstSequence: number;
  connectionId: string;
};

function buildAdjacency(
  connections: MapConnection[],
): Map<string, Neighbor[]> {
  const adjacency = new Map<string, Neighbor[]>();
  const add = (roomId: string, neighbor: Neighbor) => {
    const neighbors = adjacency.get(roomId) ?? [];
    neighbors.push(neighbor);
    adjacency.set(roomId, neighbors);
  };
  for (const connection of connections) {
    add(connection.source, {
      roomId: connection.target,
      firstSequence: connection.firstSequence,
      connectionId: connection.id,
    });
    add(connection.target, {
      roomId: connection.source,
      firstSequence: connection.firstSequence,
      connectionId: connection.id,
    });
  }
  for (const neighbors of adjacency.values()) {
    neighbors.sort((left, right) => {
      return left.firstSequence - right.firstSequence
        || left.connectionId.localeCompare(right.connectionId)
        || left.roomId.localeCompare(right.roomId);
    });
  }
  return adjacency;
}

function graphDistances(
  adjacency: Map<string, Neighbor[]>,
  source: string,
): Map<string, number> {
  const distances = new Map([[source, 0]]);
  const queue = [source];
  while (queue.length > 0) {
    const current = queue.shift();
    if (current === undefined) break;
    const distance = distances.get(current);
    if (distance === undefined) continue;
    for (const { roomId } of adjacency.get(current) ?? []) {
      if (distances.has(roomId)) continue;
      distances.set(roomId, distance + 1);
      queue.push(roomId);
    }
  }
  return distances;
}

function shortestPath(
  adjacency: Map<string, Neighbor[]>,
  source: string,
  target: string,
): string[] | null {
  if (source === target) return [source];
  const previous = new Map<string, string | null>([[source, null]]);
  const queue = [source];
  while (queue.length > 0) {
    const current = queue.shift();
    if (current === undefined) break;
    for (const { roomId } of adjacency.get(current) ?? []) {
      if (previous.has(roomId)) continue;
      previous.set(roomId, current);
      if (roomId === target) {
        const path = [target];
        let cursor: string | null = current;
        while (cursor !== null) {
          path.push(cursor);
          cursor = previous.get(cursor) ?? null;
        }
        return path.reverse();
      }
      queue.push(roomId);
    }
  }
  return null;
}

function unique(values: string[]): string[] {
  return [...new Set(values)].sort();
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}
