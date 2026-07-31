import { describe, expect, it } from "vitest";
import type {
  WorldEdgeData,
  WorldNodeData,
} from "../../data/worldContracts";
import {
  layoutWorld,
  visibleWorld,
} from "./worldLayout";

const nodes: WorldNodeData[] = [
  node("a", 1),
  node("b", 2),
  node("c", 3),
  node("d", 4),
];

const edges: WorldEdgeData[] = [
  edge("a", "b", "north"),
  edge("b", "c", "east"),
  edge("c", "d", "south"),
];

describe("world framing", () => {
  it("keeps focus local while grow preserves the complete journey", () => {
    expect(visibleWorld(nodes, edges, "b", "focus").map(({ id }) => id))
      .toEqual(["a", "b", "c"]);
    expect(visibleWorld(nodes, edges, "b", "grow")).toEqual(nodes);
  });

  it("uses two supported edges for lantern context", () => {
    expect(visibleWorld(nodes, edges, "a", "lantern").map(({ id }) => id))
      .toEqual(["a", "b", "c"]);
  });

  it("lays out connected and disconnected identities without overlap", () => {
    const points = layoutWorld(nodes, edges);
    const coordinates = points.map(({ x, y }) => `${x}:${y}`);
    expect(new Set(coordinates).size).toBe(nodes.length);
    expect(points.find(({ node: item }) => item.id === "b")!.y)
      .toBeLessThan(points.find(({ node: item }) => item.id === "a")!.y);
  });
});

function node(id: string, place: number): WorldNodeData {
  return {
    id,
    place,
    title: `Room ${id}`,
    description: null,
    atlas: null,
    exits: [],
    mobs: [],
    objects: [],
    mob_sightings: [],
    object_sightings: [],
    visits: 1,
    evidence: [place],
    first_seq: place,
    last_seq: place,
    state: id === "d" ? "current" : "observed",
    confidence: "tracked",
    method: "fixture",
  };
}

function edge(
  source: string,
  target: string,
  direction: string,
): WorldEdgeData {
  return {
    id: `${source}:${target}`,
    source,
    target,
    direction,
    traversals: 1,
    evidence: [1],
  };
}
