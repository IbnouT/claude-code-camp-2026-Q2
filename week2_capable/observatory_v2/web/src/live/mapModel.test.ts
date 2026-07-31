import {
  describe,
  expect,
  it,
} from "vitest";
import type {
  WorldEdge,
  WorldNode,
} from "../contracts";
import {
  buildMapGraph,
  centerMapViewport,
  initialMapCamera,
  mapColumnGap,
  mapDragScale,
  mapRowGap,
} from "./mapModel";

describe("structural map model", () => {
  it("replays the same integer lattice from the same evidence", () => {
    const nodes = [
      room("a", 10),
      room("b", 20),
      room("c", 30),
      room("d", 40),
    ];
    const edges = [
      link("a", "b", "north", 20),
      link("b", "a", "south", 22),
      link("b", "c", "east", 30),
      link("c", "d", "south", 40),
    ];

    const first = buildMapGraph(nodes, edges);
    const replay = buildMapGraph(nodes, edges);
    expect(replay.rooms).toEqual(first.rooms);
    for (const { point } of first.rooms) {
      expect(Math.abs(point.x % mapColumnGap)).toBe(0);
      expect(Math.abs(point.y % mapRowGap)).toBe(0);
    }
  });

  it("collapses reverse evidence into one two-way connection", () => {
    const graph = buildMapGraph(
      [room("a", 10), room("b", 20)],
      [
        link("a", "b", "north", 20),
        link("b", "a", "south", 21),
      ],
    );

    expect(graph.connections).toHaveLength(1);
    expect(graph.connections[0]).toMatchObject({
      bent: false,
      displacement: false,
      oneWay: false,
    });
  });

  it("opens an occupied slot by shifting its far-side dependent block", () => {
    const graph = buildMapGraph(
      [
        room("a", 10),
        room("b", 20),
        room("c", 30),
        room("d", 40),
      ],
      [
        link("a", "b", "north", 20),
        link("b", "c", "east", 30),
        link("a", "d", "north", 40),
      ],
    );

    const points = graph.rooms.map(({ point }) => `${point.x}:${point.y}`);
    expect(new Set(points).size).toBe(4);
    expect(graph.connections.find(({ target }) => target === "d")?.bent)
      .toBe(false);
    expect(graph.rooms.find(({ node }) => node.id === "d")?.point)
      .toEqual({ x: 0, y: -mapRowGap });
    expect(graph.rooms.find(({ node }) => node.id === "b")?.point)
      .toEqual({ x: 0, y: -2 * mapRowGap });
    expect(graph.rooms.find(({ node }) => node.id === "c")?.point)
      .toEqual({ x: mapColumnGap, y: -2 * mapRowGap });
  });

  it("replays exact whole-row shifts for synthetic insertions", () => {
    const nodes = [
      room("anchor", 10),
      room("first", 20),
      room("second", 30),
      room("third", 40),
    ];
    const edges = [
      link("anchor", "first", "east", 20),
      link("anchor", "second", "east", 30),
      link("anchor", "third", "east", 40),
    ];
    const secondInsertion = buildMapGraph(nodes.slice(0, 3), edges.slice(0, 2));
    const thirdInsertion = buildMapGraph(nodes, edges);

    expect(
      secondInsertion.rooms.find(({ node }) => node.id === "first")?.point,
    ).toEqual({ x: 2 * mapColumnGap, y: 0 });
    expect(
      secondInsertion.rooms.find(({ node }) => node.id === "second")?.point,
    ).toEqual({ x: mapColumnGap, y: 0 });
    expect(
      thirdInsertion.rooms.find(({ node }) => node.id === "third")?.point,
    )
      .toEqual({ x: mapColumnGap, y: 0 });
    expect(
      thirdInsertion.rooms.find(({ node }) => node.id === "second")?.point,
    )
      .toEqual({ x: 2 * mapColumnGap, y: 0 });
    expect(
      thirdInsertion.rooms.find(({ node }) => node.id === "first")?.point,
    )
      .toEqual({ x: 3 * mapColumnGap, y: 0 });
  });

  it("resolves diagonal insertions on the vertical axis", () => {
    const graph = buildMapGraph(
      [
        room("origin", 10),
        room("first", 20),
        room("inserted", 30),
      ],
      [
        link("origin", "first", "northeast", 20),
        link("origin", "inserted", "northeast", 30),
      ],
    );

    expect(graph.rooms.find(({ node }) => node.id === "inserted")?.point)
      .toEqual({ x: mapColumnGap, y: -mapRowGap });
    expect(graph.rooms.find(({ node }) => node.id === "first")?.point)
      .toEqual({ x: mapColumnGap, y: -2 * mapRowGap });
  });

  it("reserves bent links for contradictory direction evidence", () => {
    const graph = buildMapGraph(
      [room("a", 10), room("b", 20)],
      [
        link("a", "b", "north", 20),
        link("a", "b", "south", 21),
      ],
    );

    expect(graph.connections[0]?.bent).toBe(true);
  });

  it("seeds a displacement target in the nearest deterministic free cell", () => {
    const graph = buildMapGraph(
      [room("a", 10), room("b", 20)],
      [link("a", "b", "flee", 20)],
    );

    expect(graph.connections[0]).toMatchObject({
      direction: "flee",
      displacement: true,
      oneWay: true,
      vertical: false,
    });
    const [source, target] = graph.rooms;
    expect(Math.hypot(
      target.point.x - source.point.x,
      target.point.y - source.point.y,
    )).toBeCloseTo(Math.hypot(mapColumnGap, mapRowGap));
  });

  it("does not magnify a young world", () => {
    const graph = buildMapGraph([room("a", 10)], []);
    expect(initialMapCamera(graph).viewport).toEqual({
      x: graph.x - (1_600 - graph.width) / 2,
      y: graph.y - (900 - graph.height) / 2,
      width: 1_600,
      height: 900,
    });
  });

  it("fits only while every room remains readable", () => {
    const nodes = Array.from({ length: 20 }, (_, index) => {
      return room(String(index), index + 1);
    });
    const edges = nodes.slice(1).map((node, index) => {
      return link(nodes[index].id, node.id, "east", node.first_seq);
    });
    const graph = buildMapGraph(nodes, edges);
    const camera = initialMapCamera(graph);

    expect(camera.panning).toBe(true);
    expect(camera.viewport.width).toBeLessThanOrEqual(1_600 / 0.75);
    expect(camera.viewport.height).toBeLessThanOrEqual(900 / 0.75);

    const moved = centerMapViewport(graph, camera.viewport, {
      x: graph.x,
      y: graph.y,
    });
    expect(moved.x).toBe(graph.x);
  });

  it("lets one center-to-edge drag traverse the complete pan range", () => {
    expect(mapDragScale(2_332, 1_850)).toBe(1);
    expect(mapDragScale(1_694, 1_048)).toBeCloseTo(1.2945, 4);
  });

  it("places a down-only target diagonally below its source", () => {
    const graph = buildMapGraph(
      [room("source", 10), room("target", 20)],
      [link("source", "target", "down", 20)],
    );

    expect(graph.rooms.find(({ node }) => node.id === "target")?.point)
      .toEqual({ x: mapColumnGap, y: mapRowGap });
    expect(graph.connections[0]).toMatchObject({
      direction: "down",
      vertical: true,
      displacement: false,
      oneWay: true,
    });
  });

  it("places an up-only target diagonally above its source", () => {
    const graph = buildMapGraph(
      [room("source", 10), room("target", 20)],
      [link("source", "target", "up", 20)],
    );

    expect(graph.rooms.find(({ node }) => node.id === "target")?.point)
      .toEqual({ x: mapColumnGap, y: -mapRowGap });
  });

  it("uses coinciding planar evidence for placement and retains vertical evidence", () => {
    const graph = buildMapGraph(
      [room("source", 10), room("target", 30)],
      [
        link("source", "target", "east", 20),
        link("source", "target", "down", 21),
      ],
    );

    expect(graph.rooms.find(({ node }) => node.id === "target")?.point)
      .toEqual({ x: mapColumnGap, y: 0 });
    expect(graph.connections[0]).toMatchObject({
      direction: "down",
      vertical: true,
      displacement: false,
    });
  });

  it("retains reverse vertical evidence as an attached two-way connection", () => {
    const graph = buildMapGraph(
      [room("a", 10), room("b", 20)],
      [
        link("a", "b", "up", 20),
        link("b", "a", "down", 21),
      ],
    );

    expect(graph.connections[0]).toMatchObject({
      vertical: true,
      displacement: false,
      oneWay: false,
    });
  });

  it("collapses repeated synthetic places with the same atlas vnum", () => {
    const first = {
      ...room("first", 10),
      atlas: atlasIdentity(3001, "inside"),
    };
    const repeated = {
      ...room("repeated", 20),
      atlas: atlasIdentity(3001, "inside"),
    };
    const neighbor = {
      ...room("neighbor", 30),
      atlas: atlasIdentity(3005, "city"),
    };
    const graph = buildMapGraph(
      [first, repeated, neighbor],
      [
        link("first", "neighbor", "south", 15),
        link("repeated", "neighbor", "south", 25),
      ],
    );

    expect(graph.rooms).toHaveLength(2);
    expect(graph.rooms.find(({ node }) => node.id === "vnum:3001")?.node)
      .toMatchObject({
        visits: 2,
        evidence: [10, 20],
        method: "atlas-vnum-canonical",
      });
    expect(graph.connections).toHaveLength(1);
  });
});

function room(id: string, firstSequence: number): WorldNode {
  return {
    id,
    place: firstSequence,
    title: `Room ${id}`,
    exits: [],
    visits: 1,
    evidence: [firstSequence],
    first_seq: firstSequence,
    last_seq: firstSequence,
    state: id === "d" ? "current" : "observed",
    confidence: "tracked",
    method: "fixture",
  };
}

function link(
  source: string,
  target: string,
  direction: string,
  firstSequence: number,
): WorldEdge {
  return {
    id: `${source}:${target}:${direction}`,
    source,
    target,
    direction,
    traversals: 1,
    evidence: [firstSequence],
  };
}

function atlasIdentity(
  vnum: number,
  sector: string,
): NonNullable<WorldNode["atlas"]> {
  return {
    vnum,
    zone_id: 30,
    zone_label: "Midgaard",
    sector,
    atlas_digest: "fixture",
    confidence: "medium",
    evidence: ["fixture"],
  };
}
