import {
  describe,
  expect,
  it,
} from "vitest";
import type { MapGraph } from "./mapModel";
import {
  projectFocusContinuationOverlay,
  projectFocusContinuations,
} from "./focusContinuation";

describe("Focus continuation projection", () => {
  it("projects learned crossings by hidden-room position, one per edge", () => {
    const graph = fixtureGraph([
      ["current", 100, 100],
      ["north-near", 120, -100],
      ["north-far", 160, -300],
      ["east", 600, 140],
    ], [
      ["current", "north-near"],
      ["current", "north-far"],
      ["current", "east"],
    ]);

    expect(projectFocusContinuations(
      graph,
      new Set(["current"]),
      { x: 0, y: 0, width: 400, height: 300 },
    )).toEqual([
      {
        edge: "top",
        hiddenRoomId: "north-near",
        point: { x: 152, y: -68 },
      },
      {
        edge: "right",
        hiddenRoomId: "east",
        point: { x: 632, y: 172 },
      },
    ]);
  });

  it("uses the nearer overshoot and lets a vertical edge win a tie", () => {
    const graph = fixtureGraph([
      ["current", 100, 100],
      ["near-top", 410, -50],
      ["tie-top", 418, -50],
    ], [
      ["current", "near-top"],
      ["current", "tie-top"],
    ]);

    const markers = projectFocusContinuations(
      graph,
      new Set(["current"]),
      { x: 0, y: 0, width: 400, height: 300 },
    );

    expect(markers).toHaveLength(1);
    expect(markers[0]?.edge).toBe("top");
    expect(markers[0]?.hiddenRoomId).toBe("near-top");
  });

  it("migrates a continuation edge when the live viewBox pans", () => {
    const graph = fixtureGraph([
      ["current", 100, 100],
      ["hidden", 450, -100],
    ], [["current", "hidden"]]);

    expect(projectFocusContinuations(
      graph,
      new Set(["current"]),
      { x: 0, y: 0, width: 400, height: 300 },
    )[0]?.edge).toBe("top");
    expect(projectFocusContinuations(
      graph,
      new Set(["current"]),
      { x: 0, y: -200, width: 400, height: 300 },
    )[0]?.edge).toBe("right");
  });

  it("announces a connected hidden room even when its center is inside", () => {
    const graph = fixtureGraph([
      ["current", 100, 100],
      ["inside", 200, 120],
      ["unconnected", 700, 120],
    ], [["current", "inside"]]);

    expect(projectFocusContinuations(
      graph,
      new Set(["current"]),
      { x: 0, y: 0, width: 400, height: 300 },
    )).toEqual([{
      edge: "right",
      hiddenRoomId: "inside",
      point: { x: 232, y: 152 },
    }]);
  });

  it("keeps a fixed-size overlay on the safe pane edge", () => {
    const marker = {
      edge: "right",
      hiddenRoomId: "hidden",
      point: { x: 500, y: 120 },
    } as const;
    const insets = { top: 10, right: 10, bottom: 10, left: 10 };

    expect(projectFocusContinuationOverlay(
      marker,
      { x: 0, y: 0, width: 400, height: 300 },
      { width: 400, height: 300 },
      insets,
      [],
    )).toEqual({ left: 340, top: 108, width: 50, height: 24 });
    expect(projectFocusContinuationOverlay(
      marker,
      { x: 0, y: 0, width: 800, height: 600 },
      { width: 400, height: 300 },
      insets,
      [],
    )).toMatchObject({ width: 50, height: 24 });
  });

  it("slides along the edge instead of covering a visible room", () => {
    const box = projectFocusContinuationOverlay(
      {
        edge: "bottom",
        hiddenRoomId: "hidden",
        point: { x: 132, y: 400 },
      },
      { x: 0, y: 0, width: 400, height: 300 },
      { width: 400, height: 300 },
      { top: 10, right: 10, bottom: 10, left: 10 },
      [{ x: 100, y: 200, width: 64, height: 88 }],
    );

    expect(box).toEqual({ left: 72, top: 240, width: 24, height: 50 });
  });
});

function fixtureGraph(
  rooms: [string, number, number][],
  connections: [string, string][],
): MapGraph {
  return {
    rooms: rooms.map(([id, x, y]) => ({
      node: {
        id,
        place: 1,
        title: id,
        description: null,
        atlas: null,
        exits: [],
        mobs: [],
        objects: [],
        mob_sightings: [],
        object_sightings: [],
        visits: 1,
        evidence: [1],
        first_seq: 1,
        last_seq: 1,
        state: id === "current" ? "current" : "observed",
        confidence: "tracked",
        method: "fixture",
      },
      point: { x, y },
    })),
    connections: connections.map(([source, target], index) => ({
      id: `${source}:${target}`,
      source,
      target,
      direction: "unknown",
      firstSequence: index,
      displacement: false,
      vertical: false,
      bent: false,
      oneWay: false,
    })),
    currentRoomId: "current",
    x: 0,
    y: 0,
    width: 800,
    height: 500,
  };
}
