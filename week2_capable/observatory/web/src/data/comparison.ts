export type ComparisonMode = "raw" | "minimal" | "full";

export type AttentionEconomics = {
  fresh_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  output_tokens: number;
  result_chars: number;
  schema_tokens: number;
  movement_share: number;
};

export type ComparisonCohort = {
  mode: ComparisonMode;
  samples: number;
  successes: number;
  cost_mean: number;
  cost_median: number;
  cost_stdev: number;
  calls_mean: number;
  calls_stdev: number;
  invalid_calls: number;
  corrective_calls: number;
  tools: Record<string, number>;
  attention: AttentionEconomics;
};

export type ComparisonMilestone = {
  index: number;
  kind: "observe" | "move" | "inspect" | "outcome" | "other";
  label: string;
  tool: string | null;
  argument: string | null;
};

export type ComparisonLane = {
  mode: ComparisonMode;
  attempt: string;
  success: boolean;
  cost_usd: number;
  calls: number;
  milestones: ComparisonMilestone[];
};

export type CounterfactualProjection = {
  mode: ComparisonMode;
  observations: number;
  bytes: number;
  estimated_tokens: number;
  delta_from_raw: number;
};

export type ParserCounterfactual = {
  mode: ComparisonMode;
  frames: number;
  recorded_version: string;
  replayed_version: string;
  recorded_lines: number;
  recorded_typed: number;
  replayed_lines: number;
  replayed_typed: number;
  recorded_miss_rate: number;
  replayed_miss_rate: number;
  typed_delta: number;
};

export type RunComparison = {
  id: string;
  title: string;
  journey: string;
  cohorts: ComparisonCohort[];
  lanes: ComparisonLane[];
  divergence: {
    index: number | null;
    summary: string;
    actions: Record<string, string>;
  };
  counterfactuals: CounterfactualProjection[];
  parser_counterfactuals: ParserCounterfactual[];
  findings: string[];
};
