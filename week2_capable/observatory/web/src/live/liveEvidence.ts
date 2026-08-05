import type {
  LiveEconomicsPoint,
  Observed,
  Snapshot,
} from "../contracts";

export type SpendProjection = {
  amount: number;
  cap: number | null;
  scope: "session" | "turn" | null;
};

export function formatAge(observedAt: string, now = Date.now()): string {
  const milliseconds = Date.parse(observedAt);
  if (!Number.isFinite(milliseconds)) return "age unknown";
  const seconds = Math.max(Math.floor((now - milliseconds) / 1_000), 0);
  if (seconds < 1) return "now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

export function projectSpend(snapshot: Snapshot): SpendProjection {
  const scope = snapshot.spend_cap_scope;
  return {
    amount: scope === "turn"
      ? snapshot.current_turn_cost_usd
      : snapshot.cost_usd,
    cap: snapshot.spend_cap_usd,
    scope,
  };
}

export function observedNumber(
  fields: Record<string, Observed>,
  key: string,
): number | null {
  const value = fields[key]?.value;
  return typeof value === "number" ? value : null;
}

export function latestCommand(snapshot: Snapshot): string | null {
  const item = [...snapshot.timeline].reverse().find((candidate) => {
    return candidate.source === "gateway" && candidate.kind === "command";
  });
  if (item === undefined) return null;
  return item.label.replace(/^Command:\s*/i, "");
}

export function tokensIn(usage: Record<string, number>): number {
  return (usage.fresh_input ?? 0)
    + (usage.cache_read ?? 0)
    + (usage.cache_write ?? 0);
}

export function cacheHit(usage: Record<string, number>): number | null {
  const input = tokensIn(usage);
  return input > 0 ? (usage.cache_read ?? 0) / input : null;
}

export function latestContextFill(snapshot: Snapshot): number | null {
  const latest = snapshot.economics.at(-1);
  if (latest === undefined || snapshot.context_limit === null) return null;
  if (snapshot.context_limit <= 0) return null;
  return latest.context_tokens / snapshot.context_limit;
}

export function responseTrend(points: LiveEconomicsPoint[]): number | null {
  const latest = points.at(-1)?.cost_usd;
  const previous = points.at(-2)?.cost_usd;
  if (latest === undefined || previous === undefined || previous === 0) {
    return null;
  }
  return (latest - previous) / previous;
}
