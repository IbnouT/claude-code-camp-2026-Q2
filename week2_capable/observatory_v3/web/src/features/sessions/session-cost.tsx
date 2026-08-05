import { useMemo } from "react"

import type { SessionInvestigation } from "@/data/session-investigation"
import { cn } from "@/lib/utils"

import {
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
} from "./cost-model"
import type { SessionSelection } from "./story-projection"

type SessionCostProps = {
  investigation: SessionInvestigation
  selection: SessionSelection
  onOpenStory: () => void
  onSelect: (selection: SessionSelection) => void
}

function TokenRow({
  color,
  label,
  total,
  value,
}: {
  color: "fresh" | "read" | "write" | "output"
  label: string
  total: number
  value: number
}) {
  return (
    <div className="border-b border-line py-3">
      <div className="mb-[7px] flex justify-between gap-[18px]">
        <span className="text-content-muted">{label}</span>
        <strong className="text-warning">{formatInteger(value)}</strong>
      </div>
      <span className="block h-[7px] overflow-hidden rounded-[6px] bg-[#1c2934]">
        <span
          className={cn(
            "block h-full rounded-[inherit]",
            color === "fresh" && "bg-[#73b9ff]",
            color === "read" && "bg-accent",
            color === "write" && "bg-[#b9a8ff]",
            color === "output" && "bg-warning"
          )}
          style={{ width: tokenShare(value, total) }}
        />
      </span>
    </div>
  )
}

/**
 * The recorded session cost view: chronological response bars, token
 * composition behind the reconciled total, and the most expensive
 * responses. Every bar and row selects the producing response record
 * and returns to it in the iteration story.
 */
function SessionCost({
  investigation,
  selection,
  onOpenStory,
  onSelect,
}: SessionCostProps) {
  const points = useMemo(
    () => attributeCostPoints(investigation),
    [investigation]
  )
  const expensive = useMemo(() => rankByCost(points), [points])
  const maximum = maximumCost(points)
  const total = tokenTotal(investigation.cost)
  const choose = (point: AttributedCostPoint): void => {
    onSelect({
      turn: point.record?.turn ?? null,
      iteration: point.iteration,
      recordId: point.record_id,
    })
    onOpenStory()
  }

  return (
    <section
      aria-label="Session cost"
      className="mx-auto w-[min(1100px,calc(100%-48px))] pt-[30px] pb-[90px] max-[900px]:w-[calc(100%-28px)]"
    >
      <header>
        <span className="text-[12px] font-[750] tracking-[0.11em] text-accent uppercase">
          Session cost
        </span>
        <h2 className="mb-1 text-[24px] font-bold">
          {usd(investigation.cost.total_usd)} across {points.length} model{" "}
          response{points.length === 1 ? "" : "s"}
        </h2>
        <p className="mb-[22px] text-content-muted">
          Every amount is attributed once. Select a bar or row to return to the
          response in its iteration story.
        </p>
      </header>

      <div className="grid grid-cols-[1.6fr_1fr] gap-[18px] max-[900px]:grid-cols-1">
        <article className="min-w-0 rounded-[14px] border border-line bg-surface p-[19px]">
          <header className="flex items-start justify-between gap-[18px]">
            <div>
              <h3 className="mb-[15px] text-[16px] font-bold">
                Cost by response over time
              </h3>
              <p className="mt-[-10px] mb-[15px] text-[13px] text-content-muted">
                Chronological model calls, from session start to stop.
              </p>
            </div>
            <span className="text-[12px] text-[#8cdda7]">
              {investigation.cost.complete ? "Reconciled" : "Partial"}
            </span>
          </header>
          {points.length === 0 ? (
            <div className="grid h-[250px] place-items-center border border-dashed border-line-strong text-content-muted">
              No response-level cost points were retained.
            </div>
          ) : (
            <div
              aria-label="Cost by response"
              className="flex h-[250px] items-end gap-[2px] overflow-hidden border-b border-line-strong pt-5"
            >
              {points.map((point, index) => (
                <button
                  aria-label={[
                    `Response ${index + 1}`,
                    point.iteration === null
                      ? "iteration unavailable"
                      : `iteration ${point.iteration}`,
                    usd(point.cost_usd),
                  ].join(", ")}
                  aria-pressed={selection.recordId === point.record_id}
                  className="min-w-px flex-1 rounded-t-[4px] bg-[image:linear-gradient(var(--warning),#866526)] p-0 aria-pressed:bg-[image:linear-gradient(var(--accent),#276b6b)]"
                  key={point.record_id}
                  style={{ height: barHeight(point.cost_usd, maximum) }}
                  title={`Iteration ${point.iteration ?? "?"} · ${usd(point.cost_usd)}`}
                  type="button"
                  onClick={() => choose(point)}
                />
              ))}
            </div>
          )}
          <div className="flex justify-between pt-2 text-[11px] text-content-quiet">
            <span>Start</span>
            <span>Response {Math.max(points.length, 1)}</span>
          </div>
        </article>

        <article className="min-w-0 rounded-[14px] border border-line bg-surface p-[19px]">
          <header className="flex items-start justify-between gap-[18px]">
            <div>
              <h3 className="mb-[15px] text-[16px] font-bold">
                Token composition
              </h3>
              <p className="mt-[-10px] mb-[15px] text-[13px] text-content-muted">
                Retained usage behind the reconciled response cost.
              </p>
            </div>
            <strong className="whitespace-nowrap text-content-primary">
              {formatInteger(total)} tok
            </strong>
          </header>
          <TokenRow
            color="fresh"
            label="Fresh input"
            total={total}
            value={investigation.cost.fresh_input_tokens}
          />
          <TokenRow
            color="read"
            label="Cache read"
            total={total}
            value={investigation.cost.cache_read_tokens}
          />
          <TokenRow
            color="write"
            label="Cache write"
            total={total}
            value={investigation.cost.cache_write_tokens}
          />
          <TokenRow
            color="output"
            label="Output"
            total={total}
            value={investigation.cost.output_tokens}
          />
          <dl className="mt-4 grid gap-2">
            <div className="flex justify-between gap-[18px]">
              <dt className="text-content-muted">Response total</dt>
              <dd>{usd(investigation.cost.response_total_usd)}</dd>
            </div>
            <div className="flex justify-between gap-[18px]">
              <dt className="text-content-muted">Raw response total</dt>
              <dd>{usd(investigation.cost.raw_response_total_usd)}</dd>
            </div>
            <div className="flex justify-between gap-[18px]">
              <dt className="text-content-muted">Reconciliation delta</dt>
              <dd>{signedUsd(investigation.cost.reconciliation_delta_usd)}</dd>
            </div>
          </dl>
        </article>

        <article className="col-span-full min-w-0 rounded-[14px] border border-line bg-surface p-[19px]">
          <header className="flex items-start justify-between gap-[18px]">
            <div>
              <h3 className="mb-[15px] text-[16px] font-bold">
                Most expensive responses
              </h3>
              <p className="mt-[-10px] mb-[15px] text-[13px] text-content-muted">
                Open the exact response and the causal work around it.
              </p>
            </div>
          </header>
          <div>
            {expensive.slice(0, 12).map((point, index) => (
              <button
                aria-pressed={selection.recordId === point.record_id}
                className="grid w-full grid-cols-[32px_1fr_auto] items-center gap-3 border-b border-line py-3 text-left text-content-primary last:border-b-0 aria-pressed:text-accent"
                key={point.record_id}
                type="button"
                onClick={() => choose(point)}
              >
                <span className="text-center font-extrabold text-accent">
                  {index + 1}
                </span>
                <span>
                  <strong>
                    Iteration {point.iteration ?? "?"} · Model response
                  </strong>
                  <small className="block text-content-muted">
                    {formatTimestamp(point.record?.at)}
                    {" · "}
                    {formatInteger(point.context_tokens)} context tok
                  </small>
                </span>
                <b className="text-warning">{usd(point.cost_usd)}</b>
              </button>
            ))}
          </div>
        </article>
      </div>

      <footer className="mt-[18px] rounded-r-[9px] border-l-[3px] border-accent bg-[#0f1c22] px-4 py-3.5 text-content-muted">
        <strong className="mr-2 text-content-primary">Cost completeness</strong>
        <span>{investigation.cost.completeness_detail}</span>
      </footer>
    </section>
  )
}

export { SessionCost, type SessionCostProps }
