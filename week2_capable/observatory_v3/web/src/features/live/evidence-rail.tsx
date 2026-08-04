import { useMemo, type ReactNode } from "react"

import type { LiveJourney } from "@/data/live-view"
import { useLivePartition } from "@/data/live-partitions"
import { useSessionCost } from "@/data/session-cost"
import { useSessionVitals, type VitalsFields } from "@/data/session-vitals"
import { cn } from "@/lib/utils"

import { FrictionBlock } from "./friction-block"
import {
  evidenceTitle,
  formatAge,
  latestCommand,
  money,
  observedNumber,
  responseTrend,
} from "./live-evidence"

type EvidenceRailProps = {
  sessionId: string | undefined
  lifecycle: string
  sessionRunning: boolean
  view: LiveJourney | null
  captureStatus: string | null
  reconnecting: boolean
}

const conditionPresentations: Record<
  string,
  { label: string; tone: "warn" | "bad" }
> = {
  hungry: { label: "Hungry", tone: "warn" },
  thirsty: { label: "Thirsty", tone: "warn" },
  drunk: { label: "Intoxicated", tone: "warn" },
  poisoned: { label: "Poisoned", tone: "bad" },
}

function lifecycleLabel(value: string): string {
  const spaced = value.replaceAll("_", " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

function RailBlock({
  title,
  status,
  children,
}: {
  title: string
  status?: { label: string; tone: "live" | "history" }
  children: ReactNode
}) {
  return (
    <section className="grid gap-2.5 border-b border-line px-4 py-3.5">
      <header className="flex items-center justify-between gap-2.5">
        <h2 className="text-[9.5px] font-semibold tracking-[0.14em] text-content-quiet uppercase">
          {title}
        </h2>
        {status === undefined ? null : (
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-[9px] tracking-[0.1em] uppercase",
              status.tone === "live" ? "text-success" : "text-content-quiet"
            )}
          >
            <i
              aria-hidden="true"
              className={cn(
                "size-[7px] rounded-[50%]",
                status.tone === "live"
                  ? "bg-success shadow-[0_0_9px_color-mix(in_srgb,var(--success)_72%,transparent)]"
                  : "bg-content-quiet"
              )}
            />
            {status.label}
          </span>
        )}
      </header>
      {children}
    </section>
  )
}

function EvidenceText({
  label,
  meta,
  title,
  value,
}: {
  label: string
  meta?: string
  title?: string
  value: string
}) {
  return (
    <div className="grid gap-[3px]" title={title}>
      <small className="text-[10px] font-semibold tracking-[0.1em] text-content-quiet uppercase">
        {label}
        {meta === undefined ? "" : ` · ${meta}`}
      </small>
      <strong className="text-[12.5px] leading-[1.45] font-semibold text-content-primary">
        {value}
      </strong>
    </div>
  )
}

function VitalBar({
  label,
  value,
  maximum,
  tone,
}: {
  label: string
  value: number | null
  maximum: number | null
  tone: "hit" | "mana" | "move"
}) {
  const observed = value !== null
  const ratio =
    observed && maximum !== null && maximum > 0
      ? Math.min(Math.max(value / maximum, 0), 1)
      : 0
  const fill =
    tone === "hit"
      ? "bg-[image:linear-gradient(90deg,var(--vital-hit-from),var(--vital-hit-to))]"
      : tone === "mana"
        ? "bg-[image:linear-gradient(90deg,var(--vital-mana-from),var(--vital-mana-to))]"
        : "bg-[image:linear-gradient(90deg,var(--vital-move-from),var(--vital-move-to))]"
  return (
    <div className="grid grid-cols-[44px_minmax(0,1fr)_72px] items-center gap-2.5 text-[12px]">
      <span className="text-content-muted">{label}</span>
      <span
        aria-hidden="true"
        className="col-start-2 row-start-1 h-2 overflow-hidden rounded-[6px] bg-(--live-track)"
      >
        <i
          className={cn("block h-full rounded-[inherit]", fill)}
          style={{ width: `${ratio * 100}%` }}
        />
      </span>
      <strong className="col-start-3 w-[72px] text-right font-mono text-[12px] font-medium text-content-muted">
        {!observed
          ? "Not observed"
          : maximum === null
            ? String(value)
            : `${value} / ${maximum}`}
      </strong>
    </div>
  )
}

function ObservedFact({
  label,
  fields,
  name,
  gold,
}: {
  label: string
  fields: VitalsFields
  name: string
  gold?: boolean
}) {
  const field = fields[name]
  return (
    <div
      className="inline-flex items-baseline gap-1.5"
      title={evidenceTitle(field)}
    >
      <small className="text-[10px] font-semibold tracking-[0.1em] text-content-quiet uppercase">
        {label}
      </small>
      <strong
        className={cn(
          "font-mono text-[12px] font-medium text-content-primary",
          gold && "text-warning"
        )}
      >
        {field === undefined ? "Not observed" : String(field.value)}
      </strong>
    </div>
  )
}

/**
 * The retained evidence rail: current status, observed character state,
 * and live economics, every value carrying its provenance.
 */
function EvidenceRail({
  sessionId,
  lifecycle,
  sessionRunning,
  view,
  captureStatus,
  reconnecting,
}: EvidenceRailProps) {
  const vitals = useSessionVitals(sessionId)
  const cost = useSessionCost(sessionId)
  const thoughts = useLivePartition(sessionId, "thought-activity")

  const fields = vitals.data?.fields ?? {}
  const hasVitals = vitals.data !== undefined

  const latestTool = useMemo(() => {
    const values = thoughts.data?.values
    if (typeof values !== "object" || values === null) return null
    const list = (values as { records?: unknown }).records
    if (!Array.isArray(list)) return null
    for (let index = list.length - 1; index >= 0; index -= 1) {
      const record = list[index] as Record<string, unknown>
      if (record?.kind === "agent:tool_call") {
        return {
          text: String(record.title ?? ""),
          at: (record.occurred_at ?? "") as string | number,
        }
      }
    }
    return null
  }, [thoughts.data?.values])

  const contributors = cost.data?.contributors ?? []
  const costs = contributors.map((entry) => entry.cost_usd ?? 0)
  const latestCost = costs.at(-1) ?? null
  const trend = responseTrend(costs)
  const spark = costs.slice(-20)
  const sparkMax = Math.max(...spark, 0.000001)
  const sparkPoints = spark
    .map((value, index) => {
      const x = spark.length <= 1 ? 0 : (index * 240) / (spark.length - 1)
      const y = 36 - (value / sparkMax) * 32 - 2
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")

  if (!hasVitals) {
    return (
      <p className="mx-4 mt-[42px] text-[11px] text-content-quiet">
        Waiting for retained evidence…
      </p>
    )
  }

  const conditions = Object.entries(conditionPresentations).flatMap(
    ([key, presentation]) =>
      fields[key]?.value === true ? [{ key, ...presentation }] : []
  )
  const posture = fields.posture

  return (
    <div className="grid min-h-full content-start bg-surface">
      <RailBlock
        title="Now"
        status={
          view !== null && !view.following_live
            ? { label: "Historical prefix", tone: "history" }
            : sessionRunning
              ? { label: "Live", tone: "live" }
              : { label: lifecycleLabel(lifecycle), tone: "history" }
        }
      >
        {view?.combat ? (
          <span className="w-fit rounded-[7px] border border-line bg-(--fighting-bg) px-[9px] py-[3px] text-[11px] text-danger capitalize">
            fighting
          </span>
        ) : posture === undefined ? null : (
          <span
            className="w-fit rounded-[7px] border border-line bg-surface-soft px-[9px] py-[3px] text-[11px] text-success capitalize"
            title={evidenceTitle(posture)}
          >
            {String(posture.value)}
          </span>
        )}
        <EvidenceText
          label="Latest tool action"
          meta={latestTool === null ? undefined : formatAge(latestTool.at)}
          value={latestTool?.text || "No tool action retained"}
        />
        <EvidenceText
          label="Last command"
          value={
            (view === null ? null : latestCommand(view.timeline)) ??
            "No command retained"
          }
        />
      </RailBlock>
      <RailBlock title="Character">
        <VitalBar
          label="HP"
          tone="hit"
          value={observedNumber(fields, "hit")}
          maximum={observedNumber(fields, "max_hit")}
        />
        <VitalBar
          label="Mana"
          tone="mana"
          value={observedNumber(fields, "mana")}
          maximum={observedNumber(fields, "max_mana")}
        />
        <VitalBar
          label="Move"
          tone="move"
          value={observedNumber(fields, "move")}
          maximum={observedNumber(fields, "max_move")}
        />
        <div className="flex items-center gap-4 py-px">
          <ObservedFact label="Level" fields={fields} name="level" />
          <ObservedFact label="Gold" fields={fields} name="gold" gold />
        </div>
        {conditions.length === 0 ? null : (
          <div
            aria-label="Observed conditions"
            className="flex flex-wrap gap-1.5"
          >
            {conditions.map((condition) => (
              <span
                key={condition.key}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-[8px] px-2.5 py-[5px] text-[11.5px] capitalize",
                  condition.tone === "warn"
                    ? "bg-warning-soft text-warning"
                    : "bg-danger-soft text-danger"
                )}
              >
                {condition.label}
              </span>
            ))}
          </div>
        )}
      </RailBlock>
      <RailBlock title="Live economics">
        <div className="grid gap-[9px]">
          <div className="flex items-center justify-between gap-2.5">
            <small className="text-[10px] font-semibold tracking-[0.1em] text-content-quiet uppercase">
              Session spend
            </small>
            <strong className="font-mono text-[15px] font-semibold text-content-primary">
              {cost.data === undefined
                ? "Not retained"
                : money(cost.data.total_cost_usd ?? 0)}
            </strong>
          </div>
        </div>
        <div className="mt-1 grid grid-cols-2 gap-2.5">
          <div className="grid min-w-0 gap-[3px] rounded-[10px] border border-line bg-(--live-cell) px-[11px] py-2.5">
            <small className="text-[10px] font-semibold tracking-[0.1em] text-content-quiet uppercase">
              Latest response
            </small>
            <strong className="font-mono text-[14px] font-semibold text-content-primary">
              {latestCost === null ? "Not retained" : money(latestCost)}
            </strong>
            {trend === null ? null : (
              <em className="text-[10px] text-content-quiet not-italic">
                {trend >= 0 ? "+" : ""}
                {Math.round(trend * 100)}% vs prior
              </em>
            )}
          </div>
          <div className="grid min-w-0 gap-[3px] rounded-[10px] border border-line bg-(--live-cell) px-[11px] py-2.5">
            <small className="text-[10px] font-semibold tracking-[0.1em] text-content-quiet uppercase">
              Tokens
            </small>
            <strong className="font-mono text-[14px] font-semibold text-content-primary">
              {cost.data === undefined
                ? "Not observed"
                : (cost.data.total_tokens ?? 0).toLocaleString()}
            </strong>
          </div>
        </div>
        <figure className="m-0 grid gap-[5px]">
          <figcaption className="text-[10px] font-semibold tracking-[0.1em] text-content-quiet uppercase">
            Cost per response: last 20
          </figcaption>
          {spark.length === 0 ? (
            <span className="text-[11px] text-content-muted">
              No response costs retained
            </span>
          ) : (
            <svg
              role="img"
              aria-label="Cost per response sparkline"
              viewBox="0 0 240 36"
              className="h-[26px] w-full overflow-visible"
            >
              <polyline
                points={sparkPoints}
                className="fill-none stroke-(--sparkline-stroke) stroke-[1.6] [vector-effect:non-scaling-stroke]"
              />
            </svg>
          )}
        </figure>
      </RailBlock>
      {view === null ? null : (
        <FrictionBlock
          view={view}
          captureStatus={captureStatus}
          reconnecting={reconnecting}
        />
      )}
    </div>
  )
}

export { EvidenceRail, type EvidenceRailProps }
