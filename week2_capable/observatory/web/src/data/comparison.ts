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
  definition: ExperimentDefinition;
  registry: ExperimentFeature[];
  validation: ExperimentValidation;
  cohorts: ComparisonCohort[];
  samples: ComparisonSample[];
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

export type ExperimentFeature = {
  id: string;
  label: string;
  group: "model" | "tools" | "rendering" | "memory" | "context" | "policy";
  kind: "boolean" | "enum" | "integer" | "number" | "text";
  description: string;
  default: boolean | number | string;
  options: string[];
  minimum?: number | null;
  maximum?: number | null;
  source: string;
};

export type ExperimentArmDefinition = {
  id: string;
  label: string;
  values: Record<string, boolean | number | string>;
};

export type ExperimentDefinition = {
  id: string;
  version: number;
  title: string;
  objective: string;
  success_predicate: string;
  journey: string;
  starting_state: string;
  reset_strategy: string;
  reset_identity: string;
  arms: ExperimentArmDefinition[];
  repetitions_per_arm: number;
  per_sample_spend_ceiling_usd: number;
  stop: {
    success_target: number;
    verified_predicate_required: boolean;
    max_iterations_per_sample: number;
    max_wall_seconds_per_sample: number;
    max_total_cost_usd: number;
    operator_stop_enabled: boolean;
  };
  effective_max_spend_usd: number;
  source: "imported_evidence" | "executable_definition";
  parent_definition_id: string | null;
  changed_feature: string | null;
};

export type ExperimentValidation = {
  valid: boolean;
  comparable: boolean;
  execution_available: boolean;
  paid_confirmation_required: boolean;
  issues: string[];
  checks: string[];
};

export type ComparisonSample = {
  run_id: string;
  mode: ComparisonMode;
  attempt: string;
  success: boolean;
  setup_failure: boolean;
  excluded: boolean;
  exclusion_reason: string | null;
  cost_usd: number;
  turns: number;
  calls: number;
};
