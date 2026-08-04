import type { LiveJourney } from "@/data/live-view"
import type { VitalsFields } from "@/data/session-vitals"

type ObservedField = VitalsFields[string]

type SpendProjection = {
  amount: number
  cap: number | null
  scope: "session" | "turn" | null
}

/** The spend figure matching the configured cap scope. */
function projectSpend(view: LiveJourney): SpendProjection {
  const scope = view.spend_cap_scope
  return {
    amount: scope === "turn" ? view.current_turn_cost_usd : view.cost_usd,
    cap: view.spend_cap_usd,
    scope,
  }
}

/** Total input tokens: fresh plus cache reads and writes. */
function tokensIn(usage: Record<string, number>): number {
  return (
    (usage.fresh_input ?? 0) +
    (usage.cache_read ?? 0) +
    (usage.cache_write ?? 0)
  )
}

/** Cache read share of total input, null when nothing came in. */
function cacheHit(usage: Record<string, number>): number | null {
  const total = tokensIn(usage)
  if (total === 0) return null
  return (usage.cache_read ?? 0) / total
}

/** The last response's context share of the window, unclamped. */
function latestContextFill(view: LiveJourney): number | null {
  const latest = view.economics.at(-1)
  if (latest === undefined) return null
  if (view.context_limit === null || view.context_limit <= 0) return null
  return latest.context_tokens / view.context_limit
}

/** Humanized age of an observation, from seconds to hours. */
function formatAge(observedAt: string | number, now = Date.now()): string {
  const parsed =
    typeof observedAt === "number" ? observedAt * 1000 : Date.parse(observedAt)
  if (!Number.isFinite(parsed)) return "age unknown"
  const seconds = Math.max(0, Math.floor((now - parsed) / 1000))
  if (seconds < 1) return "now"
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
}

/** The field's numeric value, or null when absent or non numeric. */
function observedNumber(fields: VitalsFields, key: string): number | null {
  const value = fields[key]?.value
  return typeof value === "number" ? value : null
}

/** Provenance tooltip: how and when a field was observed. */
function evidenceTitle(field: ObservedField | undefined): string | undefined {
  if (field === undefined) return undefined
  return `${field.method} · sequence ${field.sequence}`
}

/** Money in the reference format: four decimals under a cent. */
function money(value: number): string {
  return `$${value < 0.01 ? value.toFixed(4) : value.toFixed(3)}`
}

/** The most recent gateway command label, prefix stripped. */
function latestCommand(
  timeline: readonly { source: string; kind: string; label: string }[]
): string | null {
  const item = [...timeline]
    .reverse()
    .find((entry) => entry.source === "gateway" && entry.kind === "command")
  if (item === undefined) return null
  return item.label.replace(/^Command:\s*/i, "")
}

/** Fractional change of the last response cost versus the one before. */
function responseTrend(costs: readonly number[]): number | null {
  if (costs.length < 2) return null
  const previous = costs[costs.length - 2]
  if (previous === 0) return null
  return (costs[costs.length - 1] - previous) / previous
}

export {
  cacheHit,
  evidenceTitle,
  formatAge,
  latestCommand,
  latestContextFill,
  money,
  observedNumber,
  projectSpend,
  responseTrend,
  tokensIn,
  type ObservedField,
}
