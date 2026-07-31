import {
  describe,
  expect,
  it,
} from "vitest";
import type {
  RoomEconomics,
  WorldFrontier,
  WorldNode,
} from "../contracts";
import { buildMapGraph } from "./mapModel";
import { projectRoomInspector } from "./roomInspector";

describe("room inspector projection", () => {
  it("projects retained room evidence without substitutions", () => {
    const node = room("place:1", 10);
    const result = projectRoomInspector(
      node,
      [node],
      [frontier("place:1", "s", [18])],
      [economics("place:1", 0.014, ["response:3"])],
    );

    expect(result).toMatchObject({
      title: "A Nexus",
      sector: "urban",
      vnum: 3001,
      description: "A broad crossing.",
      exits: [
        { direction: "north", confirmed: true },
        { direction: "south", confirmed: false, evidence: [18] },
      ],
      visits: 5,
      firstSequence: 10,
      lastSequence: 44,
      spendUsd: 0.014,
      confidence: "tracked",
      evidence: {
        room: 2,
        atlas: 1,
        description: 1,
        exits: 1,
        sightings: 2,
        economics: 1,
      },
    });
  });

  it("keeps absent evidence absent", () => {
    const node = {
      ...room("place:1", 10),
      atlas: null,
      description: null,
      mob_sightings: [],
      object_sightings: [],
    };

    expect(projectRoomInspector(node, [node], [], [])).toMatchObject({
      sector: null,
      vnum: null,
      description: null,
      spendUsd: null,
      mobSightings: [],
      objectSightings: [],
    });
  });

  it("canonicalizes frontier and economics sources", () => {
    const first = room("place:1", 10);
    const repeated = {
      ...room("place:2", 20),
      atlas: first.atlas,
      exits: ["east"],
      visits: 2,
      evidence: [20],
    };
    const graph = buildMapGraph([first, repeated], []);
    const selected = graph.rooms[0].node;
    const result = projectRoomInspector(
      selected,
      [first, repeated],
      [
        frontier("place:1", "south", [30]),
        frontier("place:2", "s", [31]),
      ],
      [
        economics("place:1", 0.01, ["response:1"]),
        economics("place:2", 0.02, ["response:2"]),
      ],
    );

    expect(result.visits).toBe(7);
    expect(result.exits).toEqual([
      { direction: "north", confirmed: true, evidence: [] },
      { direction: "east", confirmed: true, evidence: [] },
      { direction: "south", confirmed: false, evidence: [30, 31] },
    ]);
    expect(result.spendUsd).toBeCloseTo(0.03);
    expect(result.evidence.economics).toBe(2);
  });
});

function room(id: string, firstSequence: number): WorldNode {
  return {
    id,
    place: firstSequence,
    title: "A Nexus",
    description: {
      text: "A broad crossing.",
      evidence: [12],
    },
    atlas: {
      vnum: 3001,
      zone_id: 30,
      zone_label: "Midgaard",
      sector: "urban",
      atlas_digest: "fixture",
      confidence: "high",
      evidence: ["atlas:3001"],
    },
    exits: ["north"],
    mobs: ["a large kobold"],
    objects: ["a brass key"],
    mob_sightings: [{
      name: "a large kobold",
      count: 2,
      first_seq: 20,
      last_seq: 40,
      evidence: [20],
    }],
    object_sightings: [{
      name: "a brass key",
      count: 1,
      first_seq: 23,
      last_seq: 23,
      evidence: [23],
    }],
    visits: 5,
    evidence: [firstSequence, 44],
    first_seq: firstSequence,
    last_seq: 44,
    state: "observed",
    confidence: "tracked",
    method: "fixture",
  };
}

function frontier(
  source: string,
  direction: string,
  evidence: number[],
): WorldFrontier {
  return {
    id: `${source}:${direction}`,
    source,
    direction,
    evidence,
  };
}

function economics(
  nodeId: string,
  costUsd: number,
  evidence: string[],
): RoomEconomics {
  return {
    node_id: nodeId,
    response_count: 1,
    cost_usd: costUsd,
    first_response: 1,
    last_response: 1,
    evidence,
  };
}
