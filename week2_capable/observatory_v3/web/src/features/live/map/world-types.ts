import type {
  LiveRoomEconomicsOutput,
  WorldEdgeOutput,
  WorldFrontierOutput,
  WorldNodeOutput,
  WorldRoomDescriptionOutput,
  WorldSightingOutput,
} from "@/data/generated/validators"

export type WorldRoomDescription = WorldRoomDescriptionOutput
export type WorldSighting = WorldSightingOutput
export type WorldEdge = WorldEdgeOutput
export type WorldFrontier = WorldFrontierOutput
export type RoomEconomics = LiveRoomEconomicsOutput

export type WorldNode = Omit<WorldNodeOutput, "atlas"> & {
  atlas?: WorldNodeOutput["atlas"]
}
