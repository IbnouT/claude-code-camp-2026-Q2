import type { VitalsFields } from "@/data/session-vitals"

type ObservedField = VitalsFields[string]

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
  evidenceTitle,
  formatAge,
  latestCommand,
  money,
  observedNumber,
  responseTrend,
  type ObservedField,
}
