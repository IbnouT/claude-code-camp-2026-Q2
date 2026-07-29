import type {
  ChronicleEvent,
  Diagnostic,
  RoomEdge,
  RoomNode,
} from "./types";

export const rooms: RoomNode[] = [
  { id: "temple", title: "Temple of Midgaard", x: 148, y: 196, state: "visited" },
  { id: "square", title: "Market Square", x: 304, y: 196, state: "visited" },
  { id: "nexus", title: "A Nexus", x: 442, y: 296, state: "visited" },
  { id: "white", title: "A White Square", x: 586, y: 230, state: "visited" },
  { id: "black", title: "A Black Square", x: 586, y: 366, state: "visited" },
  {
    id: "entrance-a",
    title: "Newbie Zone Entrance",
    x: 744,
    y: 264,
    state: "candidate",
    confidence: 0.5,
  },
  {
    id: "entrance-b",
    title: "Newbie Zone Entrance",
    x: 744,
    y: 362,
    state: "candidate",
    confidence: 0.5,
  },
  { id: "north", title: "Unknown north", x: 874, y: 214, state: "frontier" },
];

export const edges: RoomEdge[] = [
  { from: "temple", to: "square", direction: "north", traversals: 2 },
  { from: "square", to: "nexus", direction: "east", traversals: 4 },
  { from: "nexus", to: "white", direction: "north", traversals: 15 },
  { from: "nexus", to: "black", direction: "south", traversals: 13 },
  { from: "white", to: "entrance-a", direction: "east", traversals: 1 },
  { from: "black", to: "entrance-b", direction: "east", traversals: 1 },
  { from: "entrance-a", to: "north", direction: "north", traversals: 0 },
];

export const diagnostics: Diagnostic[] = [
  {
    id: "false-completion",
    severity: "critical",
    title: "Objective ended without evidence",
    detail: "The run stopped at an ambiguous entrance. No observation names the minotaur.",
    at: 90,
    evidence: 4,
  },
  {
    id: "confusion-loop",
    severity: "warning",
    title: "Repeated path stopped adding information",
    detail: "White Square, Black Square, and Nexus account for 36 revisits.",
    at: 61,
    evidence: 38,
  },
  {
    id: "position-ambiguity",
    severity: "notice",
    title: "Two locations remain plausible",
    detail: "Duplicate room titles are preserved until exits resolve the position.",
    at: 88,
    evidence: 2,
  },
];

export const chronicle: ChronicleEvent[] = [
  { seq: 72, label: "Decide route", kind: "model", cost: 0.0048, duration: 1240 },
  { seq: 73, label: "move north", kind: "tool", cost: 0, duration: 18 },
  { seq: 74, label: "Room frame", kind: "wire", cost: 0, duration: 84 },
  { seq: 75, label: "A White Square", kind: "observation", cost: 0, duration: 2 },
  { seq: 76, label: "Loop detected", kind: "diagnostic", cost: 0, duration: 1 },
  { seq: 77, label: "Reconsider path", kind: "model", cost: 0.0054, duration: 1510 },
  { seq: 78, label: "move east", kind: "tool", cost: 0, duration: 15 },
  { seq: 79, label: "Entrance frame", kind: "wire", cost: 0, duration: 76 },
  { seq: 80, label: "Position ambiguous", kind: "observation", cost: 0, duration: 3 },
  { seq: 81, label: "Claim complete", kind: "model", cost: 0.0061, duration: 1630 },
  { seq: 82, label: "False completion", kind: "diagnostic", cost: 0, duration: 1 },
];
