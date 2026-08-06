import { describe, expect, it } from "vitest";
import { buildMapGraph } from "./mapModel";
import world from "./mapReflowRegression.fixture.json";
import type { WorldEdge, WorldNode } from "../contracts";

const nodes = world.nodes as unknown as WorldNode[];
const edges = world.edges as unknown as WorldEdge[];

describe("map reflow with disconnected exploration", () => {
  it("lays out a world whose planar placement collides with a foreign cluster", () => {
    const graph = buildMapGraph(nodes, edges);
    expect(graph.rooms).toHaveLength(nodes.length);
  });
});
