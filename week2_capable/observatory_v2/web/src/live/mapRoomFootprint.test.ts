import {
  describe,
  expect,
  it,
} from "vitest";
import type { WorldNode } from "../contracts";
import {
  mapRoomFootprint,
  truncateMapRoomTitle,
} from "./mapRoomFootprint";

describe("map room footprint", () => {
  it("includes the title below a learned room", () => {
    const footprint = mapRoomFootprint(
      node(),
      { x: 100, y: 200 },
      false,
    );

    expect(footprint.y).toBe(200);
    expect(footprint.height).toBe(88);
    expect(footprint.x).toBeLessThanOrEqual(100);
    expect(footprint.x + footprint.width).toBeGreaterThanOrEqual(164);
  });

  it("includes the current title and external evidence badges", () => {
    const current = node();
    current.visits = 3;
    current.mob_sightings = [{
      name: "rat",
      count: 1,
      first_seq: 3,
      last_seq: 4,
      evidence: [3, 4],
    }];
    current.object_sightings = [{
      name: "key",
      count: 1,
      first_seq: 5,
      last_seq: 5,
      evidence: [5],
    }];

    const footprint = mapRoomFootprint(current, { x: 100, y: 200 }, true);

    expect(footprint.y).toBe(172);
    expect(footprint.x).toBeLessThanOrEqual(91);
    expect(footprint.x + footprint.width).toBeGreaterThanOrEqual(174);
  });

  it("bounds long and wide titles to the fitted title width", () => {
    const displayed = truncateMapRoomTitle("WWWWWWWWWWWWWWWWWW");

    expect(displayed.endsWith("…")).toBe(true);
    expect(displayed.length).toBeLessThan(18);
  });
});

function node(): WorldNode {
  return {
    id: "room",
    place: 1,
    title: "Main Street",
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
    state: "observed",
    confidence: "tracked",
    method: "fixture",
  };
}
