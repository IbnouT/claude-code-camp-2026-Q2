import type {
  LiveSnapshot,
  LiveTimelineItem,
} from "../../data/liveContracts";
import type {
  WorldEdgeData,
  WorldNodeData,
} from "../../data/worldContracts";

/* ---------------------------------------------------------------- layout --
 * Direction-aware deterministic map layout.
 * Cardinal exits map to stable vectors (north up, south down, east right,
 * west left); diagonals combine them; up/down are explicit vertical-layer
 * transitions; unknown exits use a labeled fallback. Coordinates derive from
 * an anchored breadth-first traversal. Collisions and contradictory
 * constraints are surfaced, never silently rotated. */

export const GRID_X = 140;
export const GRID_Y = 110;

const CARDINAL_VECTORS: Record<string, readonly [number, number]> = {
  north: [0, -1],
  south: [0, 1],
  east: [1, 0],
  west: [-1, 0],
  northeast: [1, -1],
  northwest: [-1, -1],
  southeast: [1, 1],
  southwest: [-1, 1],
  ne: [1, -1],
  nw: [-1, -1],
  se: [1, 1],
  sw: [-1, 1],
};

/** Vertical-layer transitions: rendered as labeled edges, offset on a
 * distinct short diagonal so they never masquerade as compass moves. */
const LAYER_VECTORS: Record<string, readonly [number, number]> = {
  up: [0.55, -0.65],
  down: [-0.55, 0.65],
};

const UNKNOWN_VECTOR: readonly [number, number] = [0.85, 0.5];

export type LayoutEdgeKind = "planar" | "layer" | "unknown";

export type LiveMapNode = WorldNodeData & {
  x: number;
  y: number;
  collision: boolean;
};

export type LiveMapEdge = WorldEdgeData & {
  sourceNode: LiveMapNode;
  targetNode: LiveMapNode;
  kind: LayoutEdgeKind;
  label: string | null;
};

export type LayoutConflict = {
  node_id: string;
  via_direction: string;
  kept: readonly [number, number];
  contradicted: readonly [number, number];
};

export type LiveMapLayout = {
  nodes: LiveMapNode[];
  edges: LiveMapEdge[];
  conflicts: LayoutConflict[];
};

function edgeKind(direction: string): LayoutEdgeKind {
  const key = direction.toLowerCase();
  if (key in CARDINAL_VECTORS) return "planar";
  if (key in LAYER_VECTORS) return "layer";
  return "unknown";
}

function directionVector(direction: string): readonly [number, number] {
  const key = direction.toLowerCase();
  return CARDINAL_VECTORS[key] ?? LAYER_VECTORS[key] ?? UNKNOWN_VECTOR;
}

export function liveMapLayout(snapshot: LiveSnapshot | null): LiveMapLayout {
  return worldMapLayout(
    snapshot?.world.nodes ?? [],
    snapshot?.world.edges ?? [],
  );
}

/** Layout over any world projection (Live snapshot or recorded session). */
export function worldMapLayout(
  worldNodes: readonly WorldNodeData[],
  worldEdges: readonly WorldEdgeData[],
): LiveMapLayout {
  if (worldNodes.length === 0) return { nodes: [], edges: [], conflicts: [] };

  const conflicts: LayoutConflict[] = [];
  const cells = new Map<string, readonly [number, number]>();
  const occupied = new Map<string, string>();
  const collided = new Set<string>();

  const anchor = worldNodes.find((node) => node.state === "current")
    ?? worldNodes[0];

  // Deterministic traversal order: edges sorted by evidence order then id.
  const sortedEdges = [...worldEdges].sort((a, b) =>
    (a.evidence[0] ?? 0) - (b.evidence[0] ?? 0) || a.id.localeCompare(b.id),
  );
  // Bidirectional traversal steps: the recorded source→target direction uses
  // +v; walking target→source uses −v. Edge orientation itself is preserved
  // for rendering and provenance — this adjacency only solves coordinates.
  type Step = {
    to: string;
    vector: readonly [number, number];
    direction: string;
  };
  const steps = new Map<string, Step[]>();
  const addStep = (from: string, step: Step): void => {
    const list = steps.get(from);
    if (list) list.push(step);
    else steps.set(from, [step]);
  };
  for (const edge of sortedEdges) {
    const vector = directionVector(edge.direction);
    addStep(edge.source, {
      to: edge.target,
      vector,
      direction: edge.direction,
    });
    addStep(edge.target, {
      to: edge.source,
      vector: [-vector[0], -vector[1]],
      direction: edge.direction,
    });
  }

  const place = (id: string, cell: readonly [number, number]): void => {
    cells.set(id, cell);
    const key = `${cell[0]},${cell[1]}`;
    const holder = occupied.get(key);
    if (holder !== undefined && holder !== id) {
      collided.add(id);
      collided.add(holder);
    } else {
      occupied.set(key, id);
    }
  };

  place(anchor.id, [0, 0]);
  const queue: string[] = [anchor.id];
  while (queue.length > 0) {
    const fromId = queue.shift() as string;
    const from = cells.get(fromId);
    if (!from) continue;
    for (const step of steps.get(fromId) ?? []) {
      const target: readonly [number, number] = [
        from[0] + step.vector[0],
        from[1] + step.vector[1],
      ];
      const existing = cells.get(step.to);
      if (existing === undefined) {
        place(step.to, target);
        queue.push(step.to);
      } else if (
        edgeKind(step.direction) === "planar"
        && (existing[0] !== target[0] || existing[1] !== target[1])
      ) {
        conflicts.push({
          node_id: step.to,
          via_direction: step.direction,
          kept: existing,
          contradicted: target,
        });
      }
    }
  }

  // Unreached nodes (no evidence path from anchor): rank below the graph,
  // explicitly, in evidence order.
  let overflow = 0;
  for (const node of worldNodes) {
    if (!cells.has(node.id)) {
      place(node.id, [overflow, Math.max(
        ...[...cells.values()].map((cell) => cell[1]),
        0,
      ) + 2]);
      overflow += 1;
    }
  }

  // Center the grid inside the 900x620 viewBox.
  const placed = [...cells.values()];
  const xs = placed.map((cell) => cell[0]);
  const ys = placed.map((cell) => cell[1]);
  const midX = (Math.min(...xs) + Math.max(...xs)) / 2;
  const midY = (Math.min(...ys) + Math.max(...ys)) / 2;

  const nodes: LiveMapNode[] = worldNodes.map((node) => {
    const cell = cells.get(node.id) as readonly [number, number];
    return {
      ...node,
      x: 450 - 18 + (cell[0] - midX) * GRID_X,
      y: 310 - 18 + (cell[1] - midY) * GRID_Y,
      collision: collided.has(node.id),
    };
  });

  const byId = new Map(nodes.map((node) => [node.id, node]));
  const edges: LiveMapEdge[] = worldEdges.flatMap((edge) => {
    const sourceNode = byId.get(edge.source);
    const targetNode = byId.get(edge.target);
    if (!sourceNode || !targetNode) return [];
    const kind = edgeKind(edge.direction);
    return [{
      ...edge,
      sourceNode,
      targetNode,
      kind,
      label: kind === "planar" ? null : edge.direction,
    }];
  });

  return { nodes, edges, conflicts };
}

export function frontierVector(
  direction: string,
): readonly [number, number] {
  const vector = directionVector(direction);
  return [vector[0] * GRID_X, vector[1] * GRID_Y];
}

/** Undirected BFS hop distances from the anchor room over evidence edges. */
export function graphDistances(
  snapshot: LiveSnapshot | null,
  anchorId: string | null,
): Map<string, number> {
  const distances = new Map<string, number>();
  if (snapshot === null || anchorId === null) return distances;
  const adjacent = new Map<string, string[]>();
  const link = (from: string, to: string): void => {
    const list = adjacent.get(from);
    if (list) list.push(to);
    else adjacent.set(from, [to]);
  };
  for (const edge of snapshot.world.edges) {
    link(edge.source, edge.target);
    link(edge.target, edge.source);
  }
  distances.set(anchorId, 0);
  const queue = [anchorId];
  while (queue.length > 0) {
    const id = queue.shift() as string;
    const base = distances.get(id) as number;
    for (const next of adjacent.get(id) ?? []) {
      if (!distances.has(next)) {
        distances.set(next, base + 1);
        queue.push(next);
      }
    }
  }
  return distances;
}

export type MapMode = "grow" | "focus" | "lantern";
export const FOCUS_RADIUS = 2;

/* ------------------------------------------------------------- formatting */

export function liveTokenTotal(snapshot: LiveSnapshot | null): number {
  return snapshot === null
    ? 0
    : Object.values(snapshot.usage).reduce((total, value) => total + value, 0);
}

export function liveInputTokens(snapshot: LiveSnapshot | null): number {
  if (snapshot === null) return 0;
  return Object.entries(snapshot.usage)
    .filter(([key]) => key.includes("input") || key.includes("context"))
    .reduce((total, [, value]) => total + value, 0);
}

export function liveOutputTokens(snapshot: LiveSnapshot | null): number {
  if (snapshot === null) return 0;
  return Object.entries(snapshot.usage)
    .filter(([key]) => key.includes("output"))
    .reduce((total, [, value]) => total + value, 0);
}

export function latestTimelineItem(
  snapshot: LiveSnapshot | null,
): LiveTimelineItem | null {
  return snapshot?.timeline.at(-1) ?? null;
}

export function formatLiveUsd(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "capture gap"
    : `$${value.toFixed(value >= 0.1 ? 3 : 4)}`;
}

export function formatLiveCount(value: number): string {
  return value >= 1_000 ? `${(value / 1_000).toFixed(1)}k` : String(value);
}

export function shortLiveId(value: string): string {
  return value.length > 8 ? value.slice(0, 8) : value;
}

export function liveTimelineColor(item: LiveTimelineItem): string {
  if (item.kind.includes("combat") || item.kind.includes("damage")) {
    return "var(--live-rose)";
  }
  if (item.kind.includes("level") || item.kind.includes("milestone")) {
    return "var(--live-amber)";
  }
  if (item.kind.includes("position") || item.kind.includes("room")) {
    return "var(--live-aqua)";
  }
  return "#2f5680";
}
