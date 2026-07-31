import {
  describe,
  expect,
  it,
} from "vitest";
import type { WorldNode } from "../contracts";
import type { MapEvidenceProjection } from "./markerProjection";
import { projectMapLegend } from "./mapLegend";

describe("map legend projection", () => {
  it("lists only marker kinds drawn for visible rooms", () => {
    const evidence: MapEvidenceProjection = {
      frontiers: [{
        id: "frontier:current:east",
        source: "current",
        direction: "east",
        start: { x: 64, y: 32 },
        end: { x: 90, y: 32 },
        evidence: [3],
      }],
      verticalByRoom: new Map([
        ["current", [{ direction: "up", state: "frontier" }]],
      ]),
      markerKinds: new Set(["frontier", "vertical", "visits"]),
    };

    expect(projectMapLegend({
      rooms: [
        {
          ...room("current", 3),
          mob_sightings: [sighting("kobold")],
        },
        {
          ...room("selected", 1),
          object_sightings: [sighting("a brass key")],
        },
        room("hidden", 4),
      ],
      visibleRoomIds: new Set(["current", "selected"]),
      currentRoomId: "current",
      selectedRoomId: "selected",
      combat: true,
      beaconRoomIds: new Set(["selected", "hidden"]),
      evidence,
      focusContinuationCount: 2,
    })).toEqual([
      { kind: "room", label: "Learned room" },
      { kind: "current", label: "Current · combat" },
      { kind: "selected", label: "Selected room" },
      { kind: "frontier", label: "Frontier exit" },
      { kind: "continuation", label: "Learned map continues" },
      { kind: "vertical", label: "Up or down exit" },
      { kind: "visits", label: "Repeat visit" },
      { kind: "beacon", label: "Objective beacon" },
      { kind: "mob", label: "Mob sighting" },
      { kind: "object", label: "Object sighting" },
    ]);
  });

  it("excludes hidden markers and unsupported rows", () => {
    expect(projectMapLegend({
      rooms: [room("visible", 1), room("hidden", 3)],
      visibleRoomIds: new Set(["visible"]),
      currentRoomId: "hidden",
      selectedRoomId: "hidden",
      combat: false,
      beaconRoomIds: new Set(["hidden"]),
      evidence: {
        frontiers: [{
          id: "frontier:hidden:east",
          source: "hidden",
          direction: "east",
          start: { x: 64, y: 32 },
          end: { x: 90, y: 32 },
          evidence: [3],
        }],
        verticalByRoom: new Map([
          ["hidden", [{ direction: "down", state: "frontier" }]],
        ]),
        markerKinds: new Set(["frontier", "vertical", "visits"]),
      },
    })).toEqual([{ kind: "room", label: "Learned room" }]);
  });

  it("returns no legend rows without visible rooms", () => {
    expect(projectMapLegend({
      rooms: [room("hidden", 1)],
      visibleRoomIds: new Set(),
      currentRoomId: null,
      selectedRoomId: null,
      combat: false,
      beaconRoomIds: new Set(),
      evidence: {
        frontiers: [],
        verticalByRoom: new Map(),
        markerKinds: new Set(),
      },
    })).toEqual([]);
  });
});

function room(id: string, visits: number): WorldNode {
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
    visits,
    evidence: [1],
    first_seq: 1,
    last_seq: 1,
    state: id === "current" ? "current" : "observed",
    confidence: "tracked",
    method: "fixture",
  };
}

function sighting(name: string): WorldNode["mob_sightings"][number] {
  return {
    name,
    count: 1,
    first_seq: 1,
    last_seq: 1,
    evidence: [1],
  };
}
