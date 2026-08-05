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
  projectLanternOpacities,
  projectMapPresentation,
  transitionMapCamera,
  visibleRoomComponentSize,
} from "./mapPresentation";

describe("map presentation", () => {
  it("uses the retained 12-room automatic mode boundary", () => {
    expect(automaticMapMode(12, null)).toBe("grow");
    expect(automaticMapMode(13, null)).toBe("focus");
    expect(automaticMapMode(40, "lantern")).toBe("lantern");
  });

  it("uses only the hard cap when frame measurement is unavailable", () => {
    const graph = lineGraph(20);

    const projection = projectMapPresentation(
      graph,
      "focus",
      null,
    );

    expect(projection.visibleRoomIds.size).toBe(18);
    expect(projection.visibleRoomIds.has("room-17")).toBe(true);
    expect(projection.visibleRoomIds.has("room-18")).toBe(false);
  });

  it("keeps dense focus shells whole beneath the hard cap", () => {
    const graph = starGraph(20);
    const projection = projectMapPresentation(
      graph,
      "focus",
      null,
    );

    expect(projection.visibleRoomIds.size).toBe(1);
  });

  it("chooses complete Focus shells that fit at the current scale", () => {
    const projection = projectMapPresentation(
      lineGraph(20),
      "focus",
      null,
      {
        frame: { width: 440, height: 120 },
        overlayRects: [],
        viewport: { x: -40, y: -30, width: 440, height: 120 },
      },
    );

    expect([...projection.visibleRoomIds]).toEqual([
      "room-0",
      "room-1",
      "room-2",
    ]);
    expect(projection.focusShellRoomCount).toBe(3);
    expect(projection.focusFillRoomCount).toBe(0);
  });

  it("fills geometric holes without refitting or breaking the shell cap", () => {
    const graph = lineGraph(4);
    graph.rooms[2].point = { x: 50, y: 0 };
    graph.rooms[3].point = { x: 400, y: 0 };
    graph.connections = [
      connection("edge-0", "room-0", "room-1", 1),
      connection("edge-1", "room-1", "room-2", 2),
      connection("edge-2", "room-1", "room-3", 3),
    ];

    const projection = projectMapPresentation(
      graph,
      "focus",
      null,
      {
        frame: { width: 320, height: 120 },
        overlayRects: [],
        viewport: { x: -40, y: -30, width: 320, height: 120 },
      },
    );

    expect([...projection.visibleRoomIds]).toEqual([
      "room-0",
      "room-1",
      "room-2",
    ]);
    expect(projection.focusShellRoomCount).toBe(2);
    expect(projection.focusFillRoomCount).toBe(1);
  });

  it("keeps iterative geometric fill beneath the hard room cap", () => {
    const projection = projectMapPresentation(
      lineGraph(30),
      "focus",
      null,
      {
        frame: { width: 3_000, height: 400 },
        overlayRects: [],
        viewport: { x: -100, y: -100, width: 3_000, height: 400 },
      },
    );

    expect(projection.visibleRoomIds.size).toBe(18);
    expect(visibleRoomComponentSize(
      lineGraph(30),
      projection.visibleRoomIds,
    )).toBe(18);
  });

  it("prioritizes a fitting selected path without exceeding the cap", () => {
    const graph = starGraph(30);
    const projection = projectMapPresentation(
      graph,
      "focus",
      "room-20",
      {
        frame: { width: 6_000, height: 400 },
        overlayRects: [],
        viewport: { x: -100, y: -100, width: 6_000, height: 400 },
      },
    );

    expect(projection.visibleRoomIds.size).toBe(18);
    expect(projection.visibleRoomIds.has("room-20")).toBe(true);
    expect(visibleRoomComponentSize(graph, projection.visibleRoomIds)).toBe(18);
  });

  it("uses local overlay rectangles instead of full-width bands", () => {
    const graph = lineGraph(2);
    graph.rooms[1].point = { x: 0, y: 122 };

    const projection = projectMapPresentation(
      graph,
      "focus",
      null,
      {
        frame: { width: 500, height: 270 },
        overlayRects: [{ x: 200, y: 200, width: 100, height: 100 }],
        viewport: { x: -100, y: -30, width: 500, height: 270 },
      },
    );

    expect([...projection.visibleRoomIds]).toEqual(["room-0", "room-1"]);
    expect(projection.focusShellRoomCount).toBe(2);
  });

  it("excludes an unneeded room when its footprint intersects an overlay", () => {
    const graph = lineGraph(2);
    graph.rooms[1].point = { x: 0, y: 122 };

    const projection = projectMapPresentation(
      graph,
      "focus",
      null,
      {
        frame: { width: 500, height: 270 },
        overlayRects: [{ x: 90, y: 210, width: 90, height: 90 }],
        viewport: { x: -100, y: -30, width: 500, height: 270 },
      },
    );

    expect([...projection.visibleRoomIds]).toEqual(["room-0"]);
  });

  it("keeps an overlay-crossing bridge needed by fitting rooms", () => {
    const graph = lineGraph(3);
    graph.rooms[1].point = { x: 80, y: 0 };
    graph.rooms[2].point = { x: 160, y: 0 };

    const projection = projectMapPresentation(
      graph,
      "focus",
      null,
      {
        frame: { width: 320, height: 120 },
        overlayRects: [{ x: 120, y: 20, width: 70, height: 70 }],
        viewport: { x: -40, y: -30, width: 320, height: 120 },
      },
    );

    expect([...projection.visibleRoomIds]).toEqual([
      "room-0",
      "room-1",
      "room-2",
    ]);
    expect(visibleRoomComponentSize(graph, projection.visibleRoomIds)).toBe(
      projection.visibleRoomIds.size,
    );
  });

  it("does not fill an island beyond a bridge outside the pane", () => {
    const graph = lineGraph(4);
    graph.rooms[1].point = { x: 600, y: 0 };
    graph.rooms[2].point = { x: 60, y: 0 };
    graph.rooms[3].point = { x: 140, y: 0 };

    const projection = projectMapPresentation(
      graph,
      "focus",
      null,
      {
        frame: { width: 280, height: 120 },
        overlayRects: [],
        viewport: { x: -40, y: -30, width: 280, height: 120 },
      },
    );

    expect([...projection.visibleRoomIds]).toEqual(["room-0"]);
    expect(visibleRoomComponentSize(graph, projection.visibleRoomIds)).toBe(
      projection.visibleRoomIds.size,
    );
  });

  it("excludes a room when its cell fits but its title is clipped", () => {
    const graph = lineGraph(2);
    graph.rooms[1].point = { x: 440, y: 0 };

    const projection = projectMapPresentation(
      graph,
      "focus",
      null,
      {
        frame: { width: 500, height: 120 },
        overlayRects: [],
        viewport: { x: -40, y: -30, width: 500, height: 120 },
      },
    );

    expect([...projection.visibleRoomIds]).toEqual(["room-0"]);
  });

  it("keeps an external selection and its deterministic learned path visible", () => {
    const graph = lineGraph(6);
    const projection = projectMapPresentation(
      graph,
      "focus",
      "room-5",
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

  it("does not render a disconnected external selection as an island", () => {
    const graph = lineGraph(3);
    graph.rooms.push({
      node: room("detached", 30),
      point: { x: 800, y: 300 },
    });

    const projection = projectMapPresentation(
      graph,
      "focus",
      "detached",
    );

    expect(projection.visibleRoomIds.has("detached")).toBe(false);
    expect(projection.selectionPathRoomIds).toEqual([]);
  });

  it("keeps complete evidence in Grow and Lantern", () => {
    const graph = lineGraph(6);
    for (const mode of ["grow", "lantern"] as const) {
      const projection = projectMapPresentation(
        graph,
        mode,
        null,
      );
      expect(projection.visibleRoomIds.size).toBe(6);
      expect(projection.visibleConnectionIds.size).toBe(5);
    }
  });

  it("uses graph-distance Lantern tiers and keeps the graph faint", () => {
    const graph = lineGraph(5);
    const opacities = projectLanternOpacities(graph);

    expect(opacities.get("room-0")).toBe(1);
    expect(opacities.get("room-1")).toBe(0.8);
    expect(opacities.get("room-2")).toBe(0.5);
    expect(opacities.get("room-3")).toBe(0.12);
    expect(opacities.get("room-4")).toBe(0.12);
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
    expect(changeMapZoom(0.1, "out")).toBe(0.1);
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

function starGraph(roomCount: number): MapGraph {
  const graph = lineGraph(roomCount);
  graph.connections = graph.rooms.slice(1).map((item, index) => {
    return connection(
      `edge-${index}`,
      "room-0",
      item.node.id,
      index + 1,
    );
  });
  return graph;
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
    description: null,
    atlas: null,
    exits: [],
    mobs: [],
    objects: [],
    mob_sightings: [],
    object_sightings: [],
    visits: 1,
    evidence: [sequence],
    first_seq: sequence,
    last_seq: sequence,
    state: id === "room-0" ? "current" : "observed",
    confidence: "tracked",
    method: "fixture",
  };
}
