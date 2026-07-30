import type { EvidenceCitation } from "./investigation";

export type QueryScope = {
  space: "live" | "sessions" | "experiments" | "knowledge";
  player_id?: string;
  live_session_id?: string;
  run_id?: string;
  through_sequence?: number;
  selected_record_id?: string;
  comparison_id?: string;
  subject_id?: string;
  lens?: string;
};

export type ObservatoryQuery = {
  version: 1;
  operation: string;
  scope: QueryScope;
  filters: Array<{
    field: string;
    operator: string;
    value: string | number | boolean;
  }>;
  order: "causal" | "chronological" | "cost_desc";
  limit: number;
};

export type AskResponse = {
  tier:
    | "deterministic"
    | "model_translated"
    | "model_summarized"
    | "model_disabled"
    | "unsupported";
  question: string;
  query: ObservatoryQuery | null;
  scope_record_id: string | null;
  plan: Array<{
    operation: string;
    source:
      | "agent"
      | "benchmark"
      | "gateway"
      | "runtime"
      | "experiments"
      | "knowledge";
    detail: string;
  }>;
  answer: string;
  claims: Array<{
    text: string;
    confidence: "high" | "medium" | "low";
    citations: string[];
  }>;
  citations: EvidenceCitation[];
  missing: string[];
  hypotheses: string[];
  model_cost_usd: number;
  model_input_tokens: number;
  model_output_tokens: number;
  model_summary: string | null;
  model_summary_citations: string[];
};
