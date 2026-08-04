import type { LiveJourney } from "@/data/live-view"
import { cn } from "@/lib/utils"

import {
  costCurve,
  eventSequences,
  labelledLandmarks,
  recentLandmarks,
  trackPosition,
} from "./timeline-model"

type CausalTimelineProps = {
  latest: LiveJourney | null
  pinned: LiveJourney | null
  reconnecting: boolean
  onSelectThrough: (sequence: number | null) => void
}

const landmarkTone: Record<string, string> = {
  room: "size-[9px] top-6 bg-[#2f5680]",
  level_up: "size-3 top-[22px] bg-warning",
  friction: "size-3 top-[22px] bg-[#c98f3a]",
  operator_message: "size-3 top-[22px] bg-(--violet)",
}

/**
 * The recent journey: causal landmarks over the retained window, the
 * cumulative cost curve, and the transport that pins an observed prefix.
 */
function CausalTimeline({
  latest,
  pinned,
  reconnecting,
  onSelectThrough,
}: CausalTimelineProps) {
  const view = pinned ?? latest
  if (view === null || latest === null) {
    return (
      <div
        role="status"
        className="grid h-full place-items-center text-[10px] text-content-quiet"
      >
        {reconnecting
          ? "Timeline evidence is reconnecting."
          : "Waiting for retained timeline evidence."}
      </div>
    )
  }

  const landmarks = recentLandmarks(latest)
  const labelled = labelledLandmarks(landmarks)
  const gateway = latest.timeline.filter((item) => item.source === "gateway")
  const firstSequence = gateway[0]?.sequence ?? latest.latest_sequence
  const lastSequence = latest.latest_sequence
  const selectedSequence = Math.min(
    Math.max(view.through_sequence, firstSequence),
    lastSequence
  )
  const events = eventSequences(latest)
  const previousEvent = [...events].reverse().find((s) => s < selectedSequence)
  const nextEvent = events.find((s) => s > selectedSequence)
  const curve = costCurve(latest.economics)
  const following = view.following_live

  const transportButton =
    "min-h-7 rounded-[8px] border border-line-strong bg-surface-raised px-[11px] py-[5px] text-[11.5px] leading-none font-medium text-content-muted disabled:cursor-default disabled:opacity-35"

  return (
    <>
      <div className="flex items-center gap-[13px] text-[11.5px] text-content-quiet">
        <small className="text-[9.5px] font-semibold tracking-[0.18em] uppercase">
          Recent journey{" "}
          <span className="tracking-[0.08em]">
            · last {latest.timeline.length} events
          </span>
        </small>
        <span
          className={cn(
            "flex items-center gap-1.5",
            following ? "text-accent" : undefined
          )}
        >
          <i
            aria-hidden="true"
            className={cn(
              "size-[7px] rounded-[50%]",
              following
                ? "bg-accent shadow-[0_0_9px_var(--accent)]"
                : "bg-content-quiet"
            )}
          />
          {following ? "following live" : "paused"}
        </span>
        <span className="text-[11.5px] whitespace-nowrap text-content-muted">
          {view.turn === null ? null : <span>turn {view.turn} · </span>}
          <span>seq {view.through_sequence}</span>
        </span>
        <div
          aria-label="Timeline transport"
          className="ml-auto flex items-center gap-2"
        >
          <button
            type="button"
            aria-label={following ? "Pause timeline" : "Resume timeline"}
            className={transportButton}
            onClick={() =>
              following
                ? onSelectThrough(view.through_sequence)
                : onSelectThrough(null)
            }
          >
            {following ? "⏸ Pause" : "▶ Resume"}
          </button>
          <button
            type="button"
            aria-label="Step to previous event"
            disabled={previousEvent === undefined}
            className={transportButton}
            onClick={() =>
              previousEvent === undefined
                ? undefined
                : onSelectThrough(previousEvent)
            }
          >
            ◀ Step
          </button>
          <button
            type="button"
            aria-label="Step to next event"
            disabled={following || nextEvent === undefined}
            className={transportButton}
            onClick={() =>
              nextEvent === undefined ? undefined : onSelectThrough(nextEvent)
            }
          >
            Step ▶
          </button>
          <button
            type="button"
            aria-label="Jump to live"
            disabled={following}
            className={cn(
              transportButton,
              "border-[color-mix(in_srgb,var(--accent)_35%,var(--line))] whitespace-nowrap text-accent"
            )}
            onClick={() => onSelectThrough(null)}
          >
            ⏭ Jump to live
          </button>
        </div>
      </div>
      <div className="group relative mt-2.5 h-[52px] cursor-pointer has-[input:focus-visible]:outline has-[input:focus-visible]:outline-offset-[3px] has-[input:focus-visible]:outline-accent">
        <div className="absolute top-[30px] right-0 left-0 h-px bg-line-strong transition-colors duration-120 group-hover:bg-[color-mix(in_srgb,var(--accent)_34%,var(--line-strong))]" />
        {curve === "" ? null : (
          <svg
            role="img"
            aria-label="Cumulative session cost"
            preserveAspectRatio="none"
            viewBox="0 0 900 52"
            className="pointer-events-none absolute inset-0 h-full w-full"
          >
            <polyline
              points={curve}
              className="fill-none stroke-[#1c2836] stroke-[1.4]"
            />
          </svg>
        )}
        {landmarks.map((landmark) => {
          const kindLabel =
            landmark.kind === "level_up"
              ? "Level up"
              : landmark.kind === "operator_message"
                ? "Operator message"
                : landmark.kind === "friction"
                  ? "Friction"
                  : "Room"
          const description = `${kindLabel}: ${landmark.label}, ${landmark.kind === "operator_message" ? "retained at " : ""}sequence ${landmark.sequence}`
          return (
            <button
              key={landmark.id}
              type="button"
              aria-label={description}
              title={description}
              style={{
                left: `${trackPosition(landmark.sequence, firstSequence, lastSequence)}%`,
              }}
              className={cn(
                "absolute z-[3] -translate-x-1/2 cursor-pointer rounded-[50%] border border-canvas transition-[box-shadow,transform] duration-120 hover:scale-125 hover:shadow-[0_0_0_4px_color-mix(in_srgb,currentColor_24%,transparent)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-content-primary",
                landmarkTone[landmark.kind]
              )}
              onClick={() =>
                onSelectThrough(
                  landmark.sequence === lastSequence ? null : landmark.sequence
                )
              }
            />
          )
        })}
        {labelled.map((landmark) => (
          <span
            key={`label-${landmark.id}`}
            style={{
              left: `${trackPosition(landmark.sequence, firstSequence, lastSequence)}%`,
            }}
            className="pointer-events-none absolute top-10 z-[2] -translate-x-1/2 text-[10px] whitespace-nowrap text-content-quiet"
          >
            {landmark.shortLabel}
          </span>
        ))}
        <div
          aria-hidden="true"
          style={{
            left: `${trackPosition(selectedSequence, firstSequence, lastSequence)}%`,
          }}
          className="pointer-events-none absolute top-3.5 bottom-2 z-[2] w-0.5 -translate-x-1/2 bg-accent after:absolute after:-top-1 after:-left-1 after:size-2.5 after:rounded-[50%] after:bg-accent after:content-['']"
        />
        <input
          type="range"
          aria-label="Observed prefix"
          min={firstSequence}
          max={lastSequence}
          value={selectedSequence}
          className="absolute inset-0 z-[1] h-full w-full cursor-pointer opacity-[0.001]"
          onChange={(event) => onSelectThrough(Number(event.target.value))}
        />
        {landmarks.length === 0 ? (
          <span className="absolute top-[27px] left-0.5 text-[10px] text-content-quiet">
            No causal landmarks in the recent retained window
          </span>
        ) : null}
      </div>
    </>
  )
}

export { CausalTimeline, type CausalTimelineProps }
