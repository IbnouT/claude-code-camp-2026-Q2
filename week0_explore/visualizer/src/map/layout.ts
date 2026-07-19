// Grid layout: BFS from the first room, north up. Deterministic for a given
// (rooms, links) graph so frames are stable while the map grows. MUD maps are
// non-Euclidean, so collisions are expected: the colliding room is placed on
// the nearest free cell (spiral probe) and its connector marked "bent".
// Rooms unreachable from the first room form floating clusters to the right.
import type { LinkC, RoomC } from "../state";

export const DIR_VEC: Record<string, [number, number]> = {
  north: [0, -1],
  south: [0, 1],
  east: [1, 0],
  west: [-1, 0],
  northeast: [1, -1],
  northwest: [-1, -1],
  southeast: [1, 1],
  southwest: [-1, 1],
};

export interface Layout {
  pos: Map<string, { x: number; y: number }>;
  bent: Set<number>; // indexes into links whose geometry != direction vector
}

export function layoutMap(rooms: Record<string, RoomC>, links: LinkC[]): Layout {
  const keys = Object.keys(rooms);
  const pos = new Map<string, { x: number; y: number }>();
  const occupied = new Set<string>();
  const cellKey = (x: number, y: number) => `${x},${y}`;

  const out = new Map<string, LinkC[]>();
  for (const l of links) {
    if (!out.has(l.from)) out.set(l.from, []);
    out.get(l.from)!.push(l);
  }

  const place = (key: string, x: number, y: number) => {
    pos.set(key, { x, y });
    occupied.add(cellKey(x, y));
  };

  const nearestFree = (x: number, y: number): [number, number] => {
    if (!occupied.has(cellKey(x, y))) return [x, y];
    for (let r = 1; r < 40; r++) {
      for (let dy = -r; dy <= r; dy++) {
        for (let dx = -r; dx <= r; dx++) {
          if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
          if (!occupied.has(cellKey(x + dx, y + dy))) return [x + dx, y + dy];
        }
      }
    }
    return [x, y + 40];
  };

  const bfsFrom = (seed: string, sx: number, sy: number) => {
    place(seed, sx, sy);
    const queue = [seed];
    while (queue.length) {
      const cur = queue.shift()!;
      const p = pos.get(cur)!;
      for (const l of out.get(cur) ?? []) {
        if (pos.has(l.to) || !rooms[l.to]) continue;
        const v = DIR_VEC[l.dir];
        const want: [number, number] = v ? [p.x + v[0], p.y + v[1]] : [p.x + 1, p.y + 1];
        const [x, y] = nearestFree(want[0], want[1]);
        place(l.to, x, y);
        queue.push(l.to);
      }
    }
  };

  // main component from the first-discovered room
  if (keys.length) bfsFrom(keys[0], 0, 0);

  // floating clusters for rooms never reached through a known link
  let clusterX = 0;
  for (const k of keys) {
    if (pos.has(k)) continue;
    const xs = [...pos.values()].map((p) => p.x);
    clusterX = Math.max(clusterX, xs.length ? Math.max(...xs) + 3 : 0);
    bfsFrom(k, clusterX, 0);
  }

  // a link is bent when its endpoints don't sit one direction-vector apart
  const bent = new Set<number>();
  links.forEach((l, i) => {
    const a = pos.get(l.from);
    const b = pos.get(l.to);
    const v = DIR_VEC[l.dir];
    if (!a || !b || !v) return;
    if (a.x + v[0] !== b.x || a.y + v[1] !== b.y) bent.add(i);
  });

  return { pos, bent };
}
