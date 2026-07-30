export type Mode = "live" | "investigate" | "compare";

export type RoomNode = {
  id: string;
  title: string;
  x: number;
  y: number;
  state: "visited" | "current" | "candidate" | "frontier";
  confidence?: number;
};

export type RoomEdge = {
  from: string;
  to: string;
  direction: string;
  traversals: number;
};

export type Diagnostic = {
  id: string;
  severity: "critical" | "warning" | "notice";
  title: string;
  detail: string;
  at: number;
  evidence: number;
};

export type ChronicleEvent = {
  seq: number;
  label: string;
  kind: "model" | "tool" | "wire" | "observation" | "diagnostic";
  cost: number;
  duration: number;
};

export type SourceState = {
  id: "gateway" | "agent" | "benchmark" | "knowledge" | "world";
  label: string;
  state: "ready" | "unavailable" | "disabled";
  detail: string;
  contract_digest?: string | null;
};
