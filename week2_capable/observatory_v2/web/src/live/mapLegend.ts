import type { WorldNode } from "../contracts";
import type { MapEvidenceProjection } from "./markerProjection";

export type MapLegendKind =
  | "room"
  | "current"
  | "selected"
  | "frontier"
  | "continuation"
  | "vertical"
  | "visits"
  | "beacon"
  | "mob"
  | "object";

export type MapLegendEntry = {
  kind: MapLegendKind;
  label: string;
};

type MapLegendInput = {
  rooms: WorldNode[];
  visibleRoomIds: ReadonlySet<string>;
  currentRoomId: string | null;
  selectedRoomId: string | null;
  combat: boolean;
  beaconRoomIds: ReadonlySet<string>;
  evidence: MapEvidenceProjection;
  focusContinuationCount?: number;
};

export function projectMapLegend({
  rooms,
  visibleRoomIds,
  currentRoomId,
  selectedRoomId,
  combat,
  beaconRoomIds,
  evidence,
  focusContinuationCount = 0,
}: MapLegendInput): MapLegendEntry[] {
  const visibleRooms = rooms.filter(({ id }) => visibleRoomIds.has(id));
  if (visibleRooms.length === 0) return [];

  const entries: MapLegendEntry[] = [{
    kind: "room",
    label: "Learned room",
  }];
  if (currentRoomId !== null && visibleRoomIds.has(currentRoomId)) {
    entries.push({
      kind: "current",
      label: combat ? "Current · combat" : "Current room",
    });
  }
  if (selectedRoomId !== null && visibleRoomIds.has(selectedRoomId)) {
    entries.push({ kind: "selected", label: "Selected room" });
  }
  entries.push({ kind: "frontier", label: "Frontier exit" });
  if (focusContinuationCount > 0) {
    entries.push({
      kind: "continuation",
      label: "Learned map continues",
    });
  }
  if ([...evidence.verticalByRoom].some(([roomId, markers]) => {
    return visibleRoomIds.has(roomId) && markers.length > 0;
  })) {
    entries.push({ kind: "vertical", label: "Up or down exit" });
  }
  entries.push({ kind: "visits", label: "Repeat visit" });
  if (visibleRooms.some(({ id }) => beaconRoomIds.has(id))) {
    entries.push({ kind: "beacon", label: "Objective beacon" });
  }
  entries.push(
    { kind: "mob", label: "Mob sighting" },
    { kind: "object", label: "Object sighting" },
  );
  return entries;
}
