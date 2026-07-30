export type KnowledgeEvidence = {
  session_id: string;
  source_seq: number;
  wire_digest: string;
  parser_version: string;
  method: string;
  observed_at: number;
};

export type KnowledgeAssertion = {
  assertion_id: string;
  fact_id: string;
  subject: string;
  predicate: string;
  value: unknown;
  layer: "belief" | "parsed" | "learned" | "observer_truth";
  status: string;
  confidence: string;
  current: boolean;
  conflict_group: string | null;
  evidence: KnowledgeEvidence[];
};

export type KnowledgeChange = {
  change_seq: number;
  transaction_id: string;
  operation: string;
  entity_type: string;
  entity_id: string;
  before_digest: string | null;
  after_digest: string | null;
  session_id: string | null;
  source_seq: number | null;
  at: number;
};

export type KnowledgeSnapshot = {
  snapshot_id: string;
  cdc_high_water: number;
  reason: string;
  digest: string;
  generation: number;
  at: number;
  verified: boolean;
};

export type KnowledgeRecovery = {
  operation: "reset" | "restore";
  operation_id: string;
  snapshot_id: string;
  reason: string;
  assertions: number;
  transaction_id: string;
  at: number;
};

export type PlayerKnowledge = {
  version: 1;
  player_id: string;
  state: "ready" | "unavailable" | "incomplete";
  source: "per-player durable knowledge";
  cdc_cursor: number;
  metrics: Array<{
    id: string;
    label: string;
    value: number;
    detail: string;
  }>;
  assertions: KnowledgeAssertion[];
  changes: KnowledgeChange[];
  snapshots: KnowledgeSnapshot[];
  recoveries: KnowledgeRecovery[];
  capture_gaps: string[];
};

export const emptyKnowledge: PlayerKnowledge = {
  version: 1,
  player_id: "",
  state: "unavailable",
  source: "per-player durable knowledge",
  cdc_cursor: 0,
  metrics: [],
  assertions: [],
  changes: [],
  snapshots: [],
  recoveries: [],
  capture_gaps: ["Select a player to inspect retained knowledge."],
};
