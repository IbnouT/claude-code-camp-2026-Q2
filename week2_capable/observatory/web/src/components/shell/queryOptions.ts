import type { QueryScope } from "../../data/ask";

export type QueryOrder = "causal" | "chronological" | "cost_desc";

export function scopeDescription(
  scope: QueryScope,
  ready: boolean,
): string {
  if (!ready) {
    return scope.space === "live"
      ? "Select a runtime session before asking about live evidence."
      : scope.space === "sessions"
        ? "Select a recorded session before asking about retained evidence."
        : "Select a player before asking about retained knowledge.";
  }
  if (scope.space === "live") {
    return scope.through_sequence === undefined
      ? "The answer uses only this runtime session as it advances."
      : `The answer cannot read beyond live sequence ${scope.through_sequence}.`;
  }
  if (scope.space === "sessions") {
    return scope.selected_record_id
      ? `The answer cannot read beyond ${scope.selected_record_id}.`
      : "The answer is limited to this recorded run.";
  }
  if (scope.space === "experiments") {
    return "The answer uses experiment definitions, jobs, samples, and comparisons only.";
  }
  return "The answer uses only retained knowledge for the selected player.";
}

export function suggestions(space: QueryScope["space"]): string[] {
  if (space === "live") {
    return [
      "What is happening now?",
      "Why did the agent stop?",
      "Which position candidates remain?",
    ];
  }
  if (space === "sessions") {
    return [
      "Why did the agent stop?",
      "Find tool records",
      "Which position candidates remain?",
    ];
  }
  if (space === "experiments") {
    return [
      "Show experiment samples",
      "Compare raw, minimal, and full",
      "Find failed samples",
    ];
  }
  return [
    "What does this player know?",
    "Find learned places",
    "Show unresolved facts",
  ];
}

export function filterFields(space: QueryScope["space"]): string[] {
  if (space === "live") {
    return ["source", "kind", "trace_id", "cost_usd"];
  }
  if (space === "sessions") {
    return ["source", "kind", "room", "trace_id", "state", "cost_usd"];
  }
  if (space === "experiments") {
    return ["arm_id", "state", "cost_usd"];
  }
  return ["kind", "confidence"];
}

export function filterOperators(
  field: string,
): Array<{ value: string; label: string }> {
  if (field === "cost_usd") {
    return [
      { value: "eq", label: "equals" },
      { value: "gte", label: "at least" },
      { value: "lte", label: "at most" },
    ];
  }
  return [
    { value: "eq", label: "equals" },
    { value: "contains", label: "contains" },
  ];
}
