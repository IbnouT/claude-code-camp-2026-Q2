import {
  describe,
  expect,
  it,
} from "vitest";
import type { WorldNode } from "../contracts";
import type { MapGraph } from "./mapModel";
import {
  centerMapViewportInExtent,
  fitMapViewport,
  keepSelectedRoomOutsidePanel,
  mapContentExtent,
  resolveMapViewport,
  roomCenter,
  viewportCenter,
  zoomMapViewport,
} from "./mapCamera";

describe("map camera geometry", () => {
  it("includes only visible rooms and their frontier marker extents", () => {
    const graph = fixtureGraph();
    const extent = mapContentExtent(
      graph,
      new Set(["current"]),
      [
        { source: "current", point: { x: -26, y: 32 } },
        { source: "hidden", point: { x: 412, y: 32 } },
      ],
      10,
    );

    expect(extent).toEqual({
      x: -36,
      y: -10,
      width: 110,
      height: 84,
    });
  });

  it("fits an extent to the visible frame aspect without cropping", () => {
    expect(fitMapViewport(
      { x: 10, y: 20, width: 200, height: 200 },
      { width: 1_600, height: 900 },
    )).toEqual({
      x: -67.77777777777777,
      y: 20,
      width: 355.55555555555554,
      height: 200,
    });
  });

  it("zooms around the existing camera center", () => {
    const viewport = { x: -100, y: -50, width: 400, height: 200 };
    const zoomed = zoomMapViewport(viewport, 2);

    expect(zoomed).toEqual({ x: 0, y: 0, width: 200, height: 100 });
    expect(viewportCenter(zoomed)).toEqual(viewportCenter(viewport));
  });

  it("clamps manual framing to the complete marker-inclusive extent", () => {
    const extent = { x: -120, y: -80, width: 600, height: 300 };
    const viewport = centerMapViewportInExtent(
      extent,
      { width: 240, height: 160 },
      { x: 900, y: 400 },
    );

    expect(viewport).toEqual({
      x: 240,
      y: 60,
      width: 240,
      height: 160,
    });
  });

  it("centers room framing on the complete square", () => {
    expect(roomCenter(fixtureGraph(), "current")).toEqual({ x: 32, y: 32 });
    expect(roomCenter(fixtureGraph(), "missing")).toBeNull();
  });

  it("re-centers Follow while Manual holds its investigator center", () => {
    const graph = fixtureGraph();
    const completeExtent = {
      x: -120,
      y: -80,
      width: 700,
      height: 300,
    };
    const shared = {
      activeExtent: completeExtent,
      completeExtent,
      fitExtent: completeExtent,
      frame: { width: 300, height: 180 },
      graph,
      zoom: 1,
    };

    const follow = resolveMapViewport({
      ...shared,
      camera: "follow",
      manualCenter: null,
    });
    const manual = resolveMapViewport({
      ...shared,
      camera: "manual",
      manualCenter: { x: 520, y: 40 },
    });

    expect(viewportCenter(follow.viewport).x).toBe(32);
    expect(viewportCenter(manual.viewport).x).toBe(380);
    expect(follow.panning).toBe(true);
    expect(manual.panning).toBe(true);
  });

  it("fits the supplied map or selection extent", () => {
    const graph = fixtureGraph();
    const completeExtent = {
      x: -120,
      y: -80,
      width: 700,
      height: 300,
    };
    const mapFit = resolveMapViewport({
      activeExtent: completeExtent,
      camera: "fit",
      completeExtent,
      fitExtent: completeExtent,
      frame: { width: 400, height: 200 },
      graph,
      manualCenter: null,
      zoom: 1,
    });
    const selectionFit = resolveMapViewport({
      activeExtent: completeExtent,
      camera: "fit",
      completeExtent,
      fitExtent: { x: -20, y: -20, width: 240, height: 120 },
      frame: { width: 400, height: 200 },
      graph,
      manualCenter: null,
      zoom: 1,
    });

    expect(mapFit.viewport).toEqual({
      x: -120,
      y: -105,
      width: 700,
      height: 350,
    });
    expect(selectionFit.viewport).toEqual({
      x: -20,
      y: -20,
      width: 240,
      height: 120,
    });
  });

  it("keeps Grow framed while Follow tracks new complete evidence", () => {
    const graph = fixtureGraph();
    const completeExtent = {
      x: -120,
      y: -80,
      width: 700,
      height: 300,
    };
    const grow = resolveMapViewport({
      activeExtent: completeExtent,
      camera: "follow",
      completeExtent,
      fitExtent: completeExtent,
      fitOnFollow: true,
      frame: { width: 400, height: 200 },
      graph,
      manualCenter: null,
      zoom: 1,
    });

    expect(grow.viewport).toEqual({
      x: -120,
      y: -105,
      width: 700,
      height: 350,
    });
  });

  it("applies zoom around the active camera target", () => {
    const graph = fixtureGraph();
    const extent = {
      x: -120,
      y: -80,
      width: 700,
      height: 300,
    };
    const normal = resolveMapViewport({
      activeExtent: extent,
      camera: "fit",
      completeExtent: extent,
      fitExtent: extent,
      frame: { width: 400, height: 200 },
      graph,
      manualCenter: null,
      zoom: 1,
    });
    const zoomed = resolveMapViewport({
      activeExtent: extent,
      camera: "fit",
      completeExtent: extent,
      fitExtent: extent,
      frame: { width: 400, height: 200 },
      graph,
      manualCenter: null,
      zoom: 2,
    });

    expect(viewportCenter(zoomed.viewport)).toEqual(
      viewportCenter(normal.viewport),
    );
    expect(zoomed.viewport.width).toBe(normal.viewport.width / 2);
    expect(zoomed.viewport.height).toBe(normal.viewport.height / 2);
  });

  it("moves only enough to keep a selected square beside the inspector", () => {
    const viewport = { x: 0, y: 0, width: 1_600, height: 900 };
    const shifted = keepSelectedRoomOutsidePanel(
      viewport,
      { width: 1_600, height: 900 },
      { x: 1_380, y: 20 },
      { right: 336, bottom: 0 },
    );

    expect(shifted).toEqual({
      x: 236,
      y: 0,
      width: 1_600,
      height: 900,
    });
  });

  it("does not disturb framing when selection clears or stays outside the panel", () => {
    const viewport = { x: 0, y: 0, width: 1_600, height: 900 };

    expect(keepSelectedRoomOutsidePanel(
      viewport,
      { width: 1_600, height: 900 },
      null,
      { right: 336, bottom: 0 },
    )).toBe(viewport);
    expect(keepSelectedRoomOutsidePanel(
      viewport,
      { width: 1_600, height: 900 },
      { x: 100, y: 800 },
      { right: 336, bottom: 0 },
    )).toBe(viewport);
  });

  it("moves narrow framing above a bottom-sheet inspector", () => {
    expect(keepSelectedRoomOutsidePanel(
      { x: 0, y: 0, width: 390, height: 700 },
      { width: 390, height: 700 },
      { x: 100, y: 620 },
      { right: 0, bottom: 385 },
    )).toEqual({
      x: 0,
      y: 417,
      width: 390,
      height: 700,
    });
  });
});

function fixtureGraph(): MapGraph {
  return {
    rooms: [
      { node: room("current", "current"), point: { x: 0, y: 0 } },
      { node: room("hidden", "observed"), point: { x: 322, y: 0 } },
    ],
    connections: [],
    currentRoomId: "current",
    x: -92,
    y: -92,
    width: 570,
    height: 248,
  };
}

function room(
  id: string,
  state: WorldNode["state"],
): WorldNode {
  return {
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
    state,
    confidence: "tracked",
    method: "fixture",
  };
}
