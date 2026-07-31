import type {
  RoomEconomics,
  WorldFrontier,
  WorldNode,
  WorldSighting,
} from "../contracts";
import { canonicalNodeId } from "./mapModel";

export type RoomInspectorExit = {
  direction: string;
  confirmed: boolean;
  evidence: number[];
};

export type RoomInspectorEvidence = {
  room: number;
  atlas: number;
  description: number;
  exits: number;
  sightings: number;
  economics: number;
};

export type RoomInspectorProjection = {
  id: string;
  title: string;
  sector: string | null;
  vnum: number | null;
  description: string | null;
  exits: RoomInspectorExit[];
  mobSightings: WorldSighting[];
  objectSightings: WorldSighting[];
  visits: number;
  firstSequence: number;
  lastSequence: number;
  spendUsd: number | null;
  confidence: string;
  evidence: RoomInspectorEvidence;
};

export function projectRoomInspector(
  selected: WorldNode,
  rawNodes: WorldNode[],
  frontier: WorldFrontier[],
  economics: RoomEconomics[],
): RoomInspectorProjection {
  const selectedId = canonicalNodeId(selected);
  const canonicalIds = new Map(
    rawNodes.map((node) => [node.id, canonicalNodeId(node)]),
  );
  const frontierByDirection = new Map<string, number[]>();
  for (const item of frontier) {
    if (canonicalIds.get(item.source) !== selectedId) continue;
    const direction = normalizeDirection(item.direction);
    frontierByDirection.set(
      direction,
      mergeNumbers(
        frontierByDirection.get(direction) ?? [],
        item.evidence,
      ),
    );
  }
  const confirmed = new Set(
    selected.exits.map(normalizeDirection),
  );
  const exits = [
    ...[...confirmed].map((direction) => ({
      direction,
      confirmed: true,
      evidence: [] as number[],
    })),
    ...[...frontierByDirection]
      .filter(([direction]) => !confirmed.has(direction))
      .map(([direction, evidence]) => ({
        direction,
        confirmed: false,
        evidence,
      })),
  ].sort(compareExits);

  const selectedEconomics = economics.filter(({ node_id: nodeId }) => {
    return canonicalIds.get(nodeId) === selectedId;
  });
  const economicsEvidence = new Set(
    selectedEconomics.flatMap(({ evidence }) => evidence),
  );
  const spendUsd = selectedEconomics.length === 0
    ? null
    : selectedEconomics.reduce((total, item) => total + item.cost_usd, 0);
  const sightingEvidence = new Set([
    ...selected.mob_sightings.flatMap(({ evidence }) => evidence),
    ...selected.object_sightings.flatMap(({ evidence }) => evidence),
  ]);
  const exitEvidence = new Set(
    [...frontierByDirection.values()].flat(),
  );

  return {
    id: selectedId,
    title: selected.title,
    sector: selected.atlas?.sector ?? null,
    vnum: selected.atlas?.vnum ?? null,
    description: selected.description?.text ?? null,
    exits,
    mobSightings: selected.mob_sightings,
    objectSightings: selected.object_sightings,
    visits: selected.visits,
    firstSequence: selected.first_seq,
    lastSequence: selected.last_seq,
    spendUsd,
    confidence: selected.confidence,
    evidence: {
      room: new Set(selected.evidence).size,
      atlas: new Set(selected.atlas?.evidence ?? []).size,
      description: new Set(selected.description?.evidence ?? []).size,
      exits: exitEvidence.size,
      sightings: sightingEvidence.size,
      economics: economicsEvidence.size,
    },
  };
}

function normalizeDirection(direction: string): string {
  const normalized = direction.trim().toLowerCase();
  const aliases: Record<string, string> = {
    n: "north",
    ne: "northeast",
    e: "east",
    se: "southeast",
    s: "south",
    sw: "southwest",
    w: "west",
    nw: "northwest",
    u: "up",
    d: "down",
  };
  return aliases[normalized] ?? normalized;
}

function mergeNumbers(left: number[], right: number[]): number[] {
  return [...new Set([...left, ...right])].sort(
    (first, second) => first - second,
  );
}

function compareExits(left: RoomInspectorExit, right: RoomInspectorExit) {
  const order = [
    "north",
    "northeast",
    "east",
    "southeast",
    "south",
    "southwest",
    "west",
    "northwest",
    "up",
    "down",
  ];
  const leftIndex = order.indexOf(left.direction);
  const rightIndex = order.indexOf(right.direction);
  return (leftIndex === -1 ? order.length : leftIndex)
    - (rightIndex === -1 ? order.length : rightIndex)
    || left.direction.localeCompare(right.direction);
}
