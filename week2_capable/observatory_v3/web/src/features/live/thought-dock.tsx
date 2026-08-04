import { ChevronDownIcon, ChevronUpIcon } from "lucide-react"

import type { LiveJourney } from "@/data/live-view"

import { formatAge } from "./live-evidence"

type ThoughtDockProps = {
  expanded: boolean
  historical?: boolean
  thought: LiveJourney["agent_thought"]
  onToggle: () => void
}

function phaseLabel(phase: string | undefined): string {
  if (phase === "reasoning") return "Thinking"
  if (phase === "plan" || phase === undefined) return "Planning"
  return "Acting"
}

function historicalTime(observedAt: string): string {
  const parsed = Date.parse(observedAt)
  if (!Number.isFinite(parsed)) return "time unavailable"
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  }).format(parsed)
}

/**
 * The agent thought dock over the map: the latest retained excerpt with
 * its phase, age, and evidence line.
 */
function ThoughtDock({
  expanded,
  historical = false,
  thought,
  onToggle,
}: ThoughtDockProps) {
  const time =
    thought === null
      ? null
      : historical
        ? historicalTime(thought.observed_at)
        : formatAge(thought.observed_at)
  return (
    <aside
      aria-label="Agent thought"
      data-map-marker-occluder="true"
      className="absolute bottom-[18px] left-[18px] z-[7] w-[min(340px,calc(50%-38px))] overflow-hidden rounded-xl border border-line-strong bg-[color-mix(in_srgb,var(--surface)_62%,transparent)] text-content-primary shadow-popover backdrop-blur-[7px] backdrop-saturate-105 max-[700px]:bottom-3.5 max-[700px]:left-3.5 max-[700px]:w-[calc(55%-20px)]"
    >
      <button
        type="button"
        aria-expanded={expanded}
        aria-label={
          expanded ? "Collapse agent thought" : "Expand agent thought"
        }
        className="flex min-h-9 w-full items-center justify-between gap-3 px-[11px] py-2 text-[9.5px] font-semibold tracking-[0.12em] text-accent uppercase hover:bg-surface-raised hover:text-content-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        onClick={onToggle}
      >
        <span>
          Agent · {phaseLabel(thought?.phase)}
          {time === null ? "" : ` · ${time}`}
        </span>
        {expanded ? (
          <ChevronDownIcon aria-hidden="true" className="size-3.5" />
        ) : (
          <ChevronUpIcon aria-hidden="true" className="size-3.5" />
        )}
      </button>
      {expanded ? (
        <div className="max-h-27 overflow-y-auto px-3 pb-[11px]">
          {thought === null ? (
            <p className="m-0 text-[12px] leading-normal text-content-primary">
              Agent thought not observed.
            </p>
          ) : (
            <>
              <p className="m-0 text-[12px] leading-normal text-content-primary">
                {thought.text}
              </p>
              <small
                title={`Observed ${thought.observed_at}`}
                className="mt-[7px] block font-mono text-[9px] text-content-quiet"
              >
                {thought.evidence} · line {thought.line}
              </small>
            </>
          )}
        </div>
      ) : null}
    </aside>
  )
}

export { ThoughtDock, type ThoughtDockProps }
