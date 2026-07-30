import type { EvidenceCitation } from "./investigation";

export type AskResponse = {
  tier:
    | "deterministic"
    | "model_translated"
    | "model_disabled"
    | "unsupported";
  question: string;
  scope_record_id: string | null;
  plan: Array<{
    operation: string;
    source: "agent" | "benchmark" | "gateway";
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
  model_cost_usd: number;
};
