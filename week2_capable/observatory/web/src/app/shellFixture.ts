import type { WorkspaceFixture } from "./shellTypes";

export const shellFixture: WorkspaceFixture = {
  players: [
    { id: "poucet", label: "poucet", detail: "Active player" },
    { id: "dummy", label: "Dummy", detail: "Recorded player" },
  ],
  sessions: [
    { id: "live-poucet", label: "Live journey", detail: "Connected · seq 82" },
    { id: "j2-minotaur", label: "J2 navigation", detail: "Recorded · 90 turns" },
  ],
  objective: "Find the Massive Minotaur",
  currentRoom: "The Temple of Midgaard",
  confidence: "50% · two candidates",
  runState: "Live evidence",
  sequence: 82,
  cost: "$0.1842",
  spendCap: "$0.50",
  tokens: "31.8k",
  sourceAge: "240 ms",
  diagnostic: {
    severity: "attention",
    title: "Position needs confirmation",
    detail: "Two rooms share this title. The next observed exit can resolve it.",
  },
  timeline: [
    {
      id: "t79",
      sequence: 79,
      time: "02:14:08",
      label: "Model chose north",
      kind: "model",
      cost: "$0.0031",
    },
    {
      id: "t80",
      sequence: 80,
      time: "02:14:10",
      label: "Gateway accepted movement",
      kind: "tool",
      cost: "$0.0000",
    },
    {
      id: "t81",
      sequence: 81,
      time: "02:14:11",
      label: "Room observation parsed",
      kind: "observation",
      cost: "$0.0000",
    },
    {
      id: "t82",
      sequence: 82,
      time: "02:14:11",
      label: "Duplicate room candidate detected",
      kind: "diagnostic",
      cost: "$0.0000",
    },
  ],
  evidence: {
    wire: {
      state: "available",
      preview: "The Temple of Midgaard\\n[ Exits: north east south west down ]",
    },
    parsed: {
      state: "available",
      preview: "room.title · exits[5] · player=poucet · confidence=0.50",
    },
    rendered: {
      state: "available",
      preview: "Temple hall with five observed exits and one present character.",
    },
    believed: {
      state: "available",
      preview: "Agent believes it is at the southern end of the temple hall.",
    },
    truth: {
      state: "missing",
      preview: "Observer truth is not configured for this installation.",
    },
  },
};
