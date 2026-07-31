import {
  describe,
  expect,
  it,
} from "vitest";
import type {
  WorldEdge,
  WorldFrontier,
  WorldNode,
} from "../contracts";
import type { MapRoom } from "./mapModel";
import {
  frontierGeometry,
  normalizeDirection,
  projectMapEvidence,
} from "./markerProjection";

describe("map evidence marker projection", () => {
  it.each([
    ["n", "north"],
    ["ne", "northeast"],
    ["e", "east"],
    ["se", "southeast"],
    ["s", "south"],
    ["sw", "southwest"],
    ["w", "west"],
    ["nw", "northwest"],
    ["u", "up"],
    ["d", "down"],
  ])("normalizes %s to %s", (alias, expected) => {
    expect(normalizeDirection(alias)).toBe(expected);
  });

  it("starts every planar frontier at the correct room edge", () => {
    expect(frontierGeometry({ x: 100, y: 200 }, "north").start)
      .toEqual({ x: 132, y: 200 });
    expect(frontierGeometry({ x: 100, y: 200 }, "east").start)
      .toEqual({ x: 164, y: 232 });
    expect(frontierGeometry({ x: 100, y: 200 }, "southwest").start)
      .toEqual({ x: 100, y: 264 });
  });

  it("canonicalizes duplicate rooms and de-duplicates source directions", () => {
    const first = room("place:1", 3001, ["n"]);
    const repeated = room("place:2", 3001, ["n"]);
    const rooms = [mapRoom({ ...first, id: "vnum:3001" })];
    const projection = projectMapEvidence(
      [first, repeated],
      [],
      [
        frontier("place:1", "n", [10]),
        frontier("place:2", "north", [12]),
      ],
      rooms,
    );

    expect(projection.frontiers).toHaveLength(1);
    expect(projection.frontiers[0]).toMatchObject({
      source: "vnum:3001",
      direction: "north",
      evidence: [10, 12],
    });
  });

  it("renders vertical exits as glyph state and never as planar stubs", () => {
    const source = room("place:1", 3001, ["u", "d"]);
    const target = room("place:2", 3002, ["u"]);
    const rooms = [mapRoom(source), mapRoom(target, 148)];
    const projection = projectMapEvidence(
      [source, target],
      [edge("place:1", "place:2", "down")],
      [frontier("place:1", "up", [11])],
      rooms,
    );

    expect(projection.frontiers).toEqual([]);
    expect(projection.verticalByRoom.get("vnum:3001")).toEqual([
      { direction: "up", state: "frontier" },
      { direction: "down", state: "traversed" },
    ]);
    expect(projection.verticalByRoom.get("vnum:3002")).toEqual([
      { direction: "up", state: "traversed" },
    ]);
    expect(projection.markerKinds).toContain("vertical");
  });

  it("exposes only marker kinds produced by current evidence", () => {
    const visited = { ...room("place:1", 3001, ["e"]), visits: 4 };
    const projection = projectMapEvidence(
      [visited],
      [],
      [frontier("place:1", "e", [20])],
      [mapRoom(visited)],
    );

    expect([...projection.markerKinds].sort()).toEqual([
      "frontier",
      "visits",
    ]);
  });
});

function room(
  id: string,
  vnum: number,
  exits: string[],
): WorldNode {
  return {
    id,
    place: vnum,
    title: `Room ${vnum}`,
    atlas: {
      vnum,
      zone_id: 30,
      zone_label: "Midgaard",
      sector: "urban",
      atlas_digest: "fixture",
      confidence: "high",
      evidence: ["fixture"],
    },
    exits,
    visits: 1,
    evidence: [1],
    first_seq: 1,
    last_seq: 1,
    state: "observed",
    confidence: "tracked",
    method: "fixture",
  };
}

function mapRoom(node: WorldNode, x = 0): MapRoom {
  return {
    node: { ...node, id: `vnum:${node.atlas?.vnum ?? node.place}` },
    point: { x, y: 0 },
  };
}

function frontier(
  source: string,
  direction: string,
  evidence: number[],
): WorldFrontier {
  return {
    id: `frontier:${source}:${direction}`,
    source,
    direction,
    evidence,
  };
}

function edge(
  source: string,
  target: string,
  direction: string,
): WorldEdge {
  return {
    id: `${source}:${target}:${direction}`,
    source,
    target,
    direction,
    traversals: 1,
    evidence: [20],
  };
}
