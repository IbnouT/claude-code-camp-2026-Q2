import type { SessionInvestigation } from "@/data/session-investigation"

type SessionCostLedger = SessionInvestigation["cost"]
type SessionCostPoint = SessionCostLedger["points"][number]
type SessionEvidenceRecord = SessionInvestigation["records"][number]

type AttributedCostPoint = SessionCostPoint & {
  record: SessionEvidenceRecord | null
}

/**
 * Every cost point joined to the session record that produced it, in
 * payload (chronological) order. A point whose record was not retained
 * keeps a null record.
 */
function attributeCostPoints(
  investigation: SessionInvestigation
): AttributedCostPoint[] {
  const records = new Map(
    investigation.records.map((record) => [record.id, record])
  )
  return investigation.cost.points.map((point): AttributedCostPoint => ({
    ...point,
    record: records.get(point.record_id) ?? null,
  }))
}

/** A fresh copy ranked by attributed cost, most expensive first. */
function rankByCost(
  points: readonly AttributedCostPoint[]
): AttributedCostPoint[] {
  return [...points].sort((left, right) => right.cost_usd - left.cost_usd)
}

function maximumCost(points: readonly SessionCostPoint[]): number {
  return Math.max(...points.map((point) => point.cost_usd), 0)
}

/**
 * Bar height as a percentage of the most expensive response, floored at
 * 2% so every retained point stays visible and clickable.
 */
function barHeight(costUsd: number, maximum: number): string {
  if (maximum <= 0) return "2%"
  return `${Math.max((costUsd / maximum) * 100, 2)}%`
}

function tokenTotal(cost: SessionCostLedger): number {
  return (
    cost.fresh_input_tokens +
    cost.cache_read_tokens +
    cost.cache_write_tokens +
    cost.output_tokens
  )
}

/** Track fill width for one token class over the composition total. */
function tokenShare(value: number, total: number): string {
  return total <= 0 ? "0%" : `${(value / total) * 100}%`
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 0,
  }).format(value)
}

function formatTimestamp(value: string | undefined): string {
  if (!value) return "Timestamp unavailable"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  }).format(date)
}

function usd(value: number): string {
  return `$${value.toFixed(6)}`
}

/**
 * A signed amount for reconciliation deltas: amounts inside the half
 * micro-dollar rounding band print as exact zero, negatives carry a true
 * minus sign.
 */
function signedUsd(value: number): string {
  if (Math.abs(value) < 0.0000005) return "$0.000000"
  return `${value > 0 ? "+" : "−"}$${Math.abs(value).toFixed(6)}`
}

export {
  attributeCostPoints,
  barHeight,
  formatInteger,
  formatTimestamp,
  maximumCost,
  rankByCost,
  signedUsd,
  tokenShare,
  tokenTotal,
  usd,
  type AttributedCostPoint,
}
