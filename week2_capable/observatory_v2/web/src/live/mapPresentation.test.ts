import {
  describe,
  expect,
  it,
} from "vitest";
import type {
  WorldNode,
} from "../contracts";
import type {
  MapConnection,
  MapGraph,
} from "./mapModel";
import {
  automaticMapMode,
  changeMapZoom,
  lanternOpacity,
  projectMapPresentation,
  transitionMapCamera,
} from "./mapPresentation";

describe("map presentation", () => {
  it("uses the retained 12-room automatic mode boundary", () => {
    expect(automaticMapMode(12, null)).toBe("grow");
    expect(automaticMapMode(13, null)).toBe("focus");
    expect(automaticMapMode(40, "lantern")).toBe("lantern");
  });

  it("projects a two-hop focus and one unique boundary count", () => {
    const graph = lineGraph(5);
    graph.connections.push(connection("branch", "room-2", "room-4", 8));

    const projection = projectMapPresentation(
      graph,
      "focus",
      null,
      new Set(),
    );

    expect([...projection.visibleRoomIds].sort()).toEqual([
      "room-0",
      "room-1",
      "room-2",
    ]);
    expect(projection.boundaries).toEqual([
      { roomId: "room-2", count: 2, expanded: false },
    ]);
  });

  it("expands and retracts only the immediate hidden boundary rooms", () => {
    const graph = lineGraph(5);
    const expanded = projectMapPresentation(
      graph,
      "focus",
      null,
      new Set(["room-2"]),
    );
    const retracted = projectMapPresentation(
      graph,
      "focus",
      null,
      new Set(),
    );

    expect(expanded.visibleRoomIds.has("room-3")).toBe(true);
    expect(expanded.visibleRoomIds.has("room-4")).toBe(false);
    expect(expanded.boundaries[0]?.expanded).toBe(true);
    expect(retracted.visibleRoomIds.has("room-3")).toBe(false);
  });

  it("keeps an external selection and its deterministic learned path visible", () => {
    const graph = lineGraph(6);
    const projection = projectMapPresentation(
      graph,
      "focus",
      "room-5",
      new Set(),
    );

    expect([...projection.visibleRoomIds].sort()).toEqual([
      "room-0",
      "room-1",
      "room-2",
      "room-3",
      "room-4",
      "room-5",
    ]);
    expect(projection.selectionPathRoomIds).toEqual([
      "room-0",
      "room-1",
      "room-2",
      "room-3",
      "room-4",
      "room-5",
    ]);
  });

  it("keeps a disconnected external selection addressable", () => {
    const graph = lineGraph(3);
    graph.rooms.push({
      node: room("detached", 30),
      point: { x: 800, y: 300 },
    });

    const projection = projectMapPresentation(
      graph,
      "focus",
      "detached",
      new Set(),
    );

    expect(projection.visibleRoomIds.has("detached")).toBe(true);
    expect(projection.selectionPathRoomIds).toEqual(["detached"]);
  });

  it("keeps complete evidence in Grow and Lantern", () => {
    const graph = lineGraph(6);
    for (const mode of ["grow", "lantern"] as const) {
      const projection = projectMapPresentation(
        graph,
        mode,
        null,
        new Set(),
      );
      expect(projection.visibleRoomIds.size).toBe(6);
      expect(projection.visibleConnectionIds.size).toBe(5);
      expect(projection.boundaries).toEqual([]);
    }
  });

  it("uses the retained neutral Lantern distance falloff", () => {
    const graph = lineGraph(3);

    expect(lanternOpacity(graph, "room-0")).toBe(1);
    expect(lanternOpacity(graph, "room-1")).toBeCloseTo(1 - 148 / 280);
    expect(lanternOpacity(graph, "room-2")).toBe(0);
  });
});

describe("map camera state", () => {
  it("separates drag, follow, fit, selection, and zoom transitions", () => {
    expect(transitionMapCamera("follow", "drag")).toBe("manual");
    expect(transitionMapCamera("manual", "fit")).toBe("fit");
    expect(transitionMapCamera("fit", "room-select")).toBe("fit");
    expect(transitionMapCamera("fit", "zoom")).toBe("fit");
    expect(transitionMapCamera("manual", "session-change")).toBe("follow");
  });

  it("clamps zoom to the documented readable range", () => {
    expect(changeMapZoom(2, "in")).toBe(2);
    expect(changeMapZoom(0.75, "out")).toBe(0.75);
    expect(changeMapZoom(1, "in")).toBe(1.25);
    expect(changeMapZoom(1, "out")).toBe(0.8);
  });
});

function lineGraph(roomCount: number): MapGraph {
  const rooms = Array.from({ length: roomCount }, (_, index) => ({
    node: room(`room-${index}`, index + 1),
    point: { x: index * 148, y: 0 },
  }));
  const connections = rooms.slice(1).map((item, index) => {
    return connection(
      `edge-${index}`,
      rooms[index].node.id,
      item.node.id,
      index + 1,
    );
  });
  return {
    rooms,
    connections,
    currentRoomId: "room-0",
    x: -92,
    y: -92,
    width: roomCount * 148 + 184,
    height: 248,
  };
}

function connection(
  id: string,
  source: string,
  target: string,
  firstSequence: number,
): MapConnection {
  return {
    id,
    source,
    target,
    direction: "east",
    firstSequence,
    displacement: false,
    vertical: false,
    bent: false,
    oneWay: false,
  };
}

function room(id: string, sequence: number): WorldNode {
  return {
    id,
    place: sequence,
    title: id,
    atlas: null,
    exits: [],
    visits: 1,
    evidence: [sequence],
    first_seq: sequence,
    last_seq: sequence,
    state: id === "room-0" ? "current" : "observed",
    confidence: "tracked",
    method: "fixture",
  };
}
