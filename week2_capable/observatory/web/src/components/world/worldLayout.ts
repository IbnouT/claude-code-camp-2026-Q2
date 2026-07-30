import type {
  WorldEdgeData,
  WorldNodeData,
} from "../../data/worldContracts";

export type WorldMode = "focus" | "grow" | "lantern";

export type WorldPoint = {
  node: WorldNodeData;
  x: number;
  y: number;
};

const offsets: Record<string, [number, number]> = {
  north: [0, -1],
  east: [1, 0],
  south: [0, 1],
  west: [-1, 0],
  up: [1, -1],
  down: [-1, 1],
};

export function visibleWorld(
  nodes: WorldNodeData[],
  edges: WorldEdgeData[],
  anchorId: string | null,
  mode: WorldMode,
): WorldNodeData[] {
  if (mode === "grow" || anchorId === null) return nodes;
  const radius = mode === "lantern" ? 2 : 1;
  const visible = new Set([anchorId]);
  for (let depth = 0; depth < radius; depth += 1) {
    const previous = new Set(visible);
    for (const edge of edges) {
      if (previous.has(edge.source)) visible.add(edge.target);
      if (previous.has(edge.target)) visible.add(edge.source);
    }
  }
  return nodes.filter((node) => visible.has(node.id));
}

export function layoutWorld(
  nodes: WorldNodeData[],
  edges: WorldEdgeData[],
): WorldPoint[] {
  if (nodes.length === 0) return [];
  const nodeIds = new Set(nodes.map((node) => node.id));
  const coordinates = new Map<string, [number, number]>();
  const occupied = new Set<string>();
  const ordered = [...nodes].sort(
    (left, right) => left.first_seq - right.first_seq,
  );
  coordinates.set(ordered[0].id, [0, 0]);
  occupied.add("0:0");

  let changed = true;
  while (changed) {
    changed = false;
    for (const edge of edges) {
      if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) continue;
      const source = coordinates.get(edge.source);
      const target = coordinates.get(edge.target);
      if (source === undefined && target === undefined) continue;
      if (source !== undefined && target === undefined) {
        const [dx, dy] = offsets[edge.direction] ?? [1, 0];
        coordinates.set(
          edge.target,
          freeCoordinate(source[0] + dx, source[1] + dy, occupied),
        );
        changed = true;
      } else if (source === undefined && target !== undefined) {
        const [dx, dy] = offsets[edge.direction] ?? [1, 0];
        coordinates.set(
          edge.source,
          freeCoordinate(target[0] - dx, target[1] - dy, occupied),
        );
        changed = true;
      }
    }
  }

  let disconnected = 0;
  for (const node of ordered) {
    if (coordinates.has(node.id)) continue;
    const point = freeCoordinate(disconnected % 5, 3 + Math.floor(disconnected / 5), occupied);
    coordinates.set(node.id, point);
    disconnected += 1;
  }

  const xs = [...coordinates.values()].map(([x]) => x);
  const ys = [...coordinates.values()].map(([, y]) => y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  return ordered.map((node) => {
    const [x, y] = coordinates.get(node.id) ?? [0, 0];
    return {
      node,
      x: 74 + (x - minX) * 126,
      y: 66 + (y - minY) * 102,
    };
  });
}

function freeCoordinate(
  startX: number,
  startY: number,
  occupied: Set<string>,
): [number, number] {
  let x = startX;
  let y = startY;
  let offset = 0;
  while (occupied.has(`${x}:${y}`)) {
    offset += 1;
    x = startX + offset;
    y = startY + (offset % 2);
  }
  occupied.add(`${x}:${y}`);
  return [x, y];
}
