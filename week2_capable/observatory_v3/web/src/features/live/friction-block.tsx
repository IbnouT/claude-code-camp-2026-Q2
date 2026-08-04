import { useState } from "react"

import type { LiveJourney } from "@/data/live-view"
import { cn } from "@/lib/utils"

type FrictionBlockProps = {
  view: LiveJourney
  captureStatus: string | null
  reconnecting: boolean
}

type GuardState = { title: string; detail: string } | null

const progressGapKinds = new Set([
  "agent_events_missing",
  "agent_events_incomplete",
  "gateway_events_missing",
  "position_not_observed",
])

/** The reference guard precedence, first match wins. */
function guardState(
  view: LiveJourney,
  captureStatus: string | null,
  reconnecting: boolean
): GuardState {
  if (reconnecting) {
    return {
      title: "Live evidence connection lost",
      detail: "Agent state is unknown until the connection recovers.",
    }
  }
  if (view.lifecycle === "crashed") {
    return {
      title: "Agent process ended unexpectedly",
      detail: `Retained evidence stops at sequence ${view.latest_sequence}.`,
    }
  }
  if (view.lifecycle === "stopped") {
    return {
      title: "Session stopped",
      detail: `No further activity is expected after sequence ${view.latest_sequence}.`,
    }
  }
  if (view.control_state === "paused") {
    return {
      title: "Agent paused by operator",
      detail: "No new activity is expected until it is resumed.",
    }
  }
  if (
    (captureStatus !== null && captureStatus !== "complete") ||
    view.capture_gaps.some((gap) => progressGapKinds.has(gap))
  ) {
    return {
      title: "Progress cannot be determined",
      detail: "This session reports incomplete retained evidence.",
    }
  }
  return null
}

/**
 * The progress block: friction diagnostics over the retained window, or
 * the guard state that explains why progress cannot be judged.
 */
function FrictionBlock({
  view,
  captureStatus,
  reconnecting,
}: FrictionBlockProps) {
  const [showEvidence, setShowEvidence] = useState(false)
  const guard = guardState(view, captureStatus, reconnecting)
  const friction = view.friction
  const fired = guard === null && friction.kind !== null

  return (
    <section
      className={cn(
        "grid min-h-[126px] content-start gap-2.5 border-b border-line px-4 py-3.5",
        fired &&
          "border-l-[3px] border-l-warning bg-[color-mix(in_srgb,var(--warning)_7%,transparent)]"
      )}
    >
      <h2 className="text-[9.5px] font-semibold tracking-[0.14em] text-content-quiet uppercase">
        Progress
      </h2>
      {guard !== null ? (
        <div className="grid gap-1.5">
          <strong className="text-[12.5px] text-content-muted">
            {guard.title}
          </strong>
          <p className="m-0 text-[11px] leading-[1.45] text-content-muted">
            {guard.detail}
          </p>
        </div>
      ) : (
        <div className="grid gap-1.5">
          {fired ? (
            <>
              <strong className="text-[12.5px] text-warning">
                {friction.kind === "confusion_loop"
                  ? "Possible navigation loop"
                  : "Possible progress stall"}
              </strong>
              <small className="text-[11px] text-content-muted">
                <code className="font-mono text-[10px] text-warning">
                  {friction.kind}
                </code>{" "}
                · {friction.threshold}
              </small>
            </>
          ) : null}
          <p className="m-0 text-[11px] leading-[1.45] text-content-muted">
            {friction.new_places} new{" "}
            {friction.new_places === 1 ? "place" : "places"} ·{" "}
            {friction.window_iterations} iterations
          </p>
          <p className="m-0 text-[11px] leading-[1.45] text-content-muted">
            {friction.iterations_since_new_place === null
              ? "No new place retained"
              : `${friction.iterations_since_new_place} iterations since the last new place`}
          </p>
          {friction.repeated_count > 1 ? (
            <p className="m-0 text-[11px] leading-[1.45] text-content-muted">
              <code className="font-mono text-[10px] text-warning">
                {friction.repeated_command}
              </code>{" "}
              repeated ×{friction.repeated_count} in the current room
            </p>
          ) : null}
          {view.combat ? (
            <small className="text-[11px] text-content-muted">
              Combat in progress. Spatial progress may pause.
            </small>
          ) : null}
          {fired ? (
            <>
              <button
                type="button"
                className="w-fit rounded-[7px] border border-line bg-surface-raised px-2 py-[5px] text-[9.5px] text-accent"
                onClick={() => setShowEvidence((current) => !current)}
              >
                {showEvidence ? "Hide attempts" : "Inspect attempts"}
              </button>
              {showEvidence ? (
                <p className="m-0 font-mono text-[9px] text-content-muted">
                  Evidence sequences{" "}
                  {friction.evidence.join(", ") || "not retained"}
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      )}
    </section>
  )
}

export { FrictionBlock, guardState, type FrictionBlockProps }
