import type { WorldEdge, WorldNode } from "./investigation";

export type PositionedWorldNode = WorldNode & {
  x: number;
  y: number;
};

export type WorldLayout = {
  nodes: PositionedWorldNode[];
  edges: WorldEdge[];
  width: number;
  height: number;
};

export function layoutWorld(
  nodes: WorldNode[],
  edges: WorldEdge[],
  focus: string | null,
  neighbourhood: boolean,
): WorldLayout {
  const visibleIds = neighbourhood && focus
    ? new Set([
        focus,
        ...edges.flatMap((edge) => {
          if (edge.source === focus) return [edge.target];
          if (edge.target === focus) return [edge.source];
          return [];
        }),
      ])
    : new Set(nodes.map((node) => node.id));
  const visible = nodes
    .filter((node) => visibleIds.has(node.id))
    .sort((left, right) => left.first_seq - right.first_seq);
  const columns = Math.min(7, Math.max(1, Math.ceil(Math.sqrt(visible.length * 1.7))));
  const rows = Math.max(1, Math.ceil(visible.length / columns));
  const width = Math.max(620, columns * 150 + 80);
  const height = Math.max(350, rows * 112 + 80);
  const positioned = visible.map((node, index) => {
    const row = Math.floor(index / columns);
    const position = index % columns;
    const column = row % 2 === 0 ? position : columns - position - 1;
    return {
      ...node,
      x: 80 + column * 150,
      y: 62 + row * 112,
    };
  });
  return {
    nodes: positioned,
    edges: edges.filter(
      (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
    ),
    width,
    height,
  };
}
