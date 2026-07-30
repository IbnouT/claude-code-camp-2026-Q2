import type { CapabilityState } from "./useCapabilities";

export type Space = "live" | "sessions" | "experiments" | "knowledge";
export type Theme = "dark" | "light";
export type Density = "comfortable" | "dense";
export type EvidenceForm =
  | "wire"
  | "parsed"
  | "rendered"
  | "believed"
  | "truth";

export type SelectorOption = {
  id: string;
  label: string;
  detail: string;
};

export type TimelineItem = {
  id: string;
  sequence: number;
  time: string;
  label: string;
  kind: "model" | "tool" | "observation" | "diagnostic";
  cost: string;
};

export type WorkspaceFixture = {
  players: SelectorOption[];
  sessions: SelectorOption[];
  objective: string;
  currentRoom: string;
  confidence: string;
  runState: string;
  sequence: number;
  cost: string;
  spendCap: string;
  tokens: string;
  sourceAge: string;
  diagnostic: {
    severity: "attention";
    title: string;
    detail: string;
  };
  timeline: TimelineItem[];
  evidence: Record<EvidenceForm, { state: "available" | "missing"; preview: string }>;
};

export type ShellCapabilities = CapabilityState;
