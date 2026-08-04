import { useEffect, useRef } from "react"

import type { LiveJourney } from "@/data/live-view"
import { cn } from "@/lib/utils"

type CombatPanelProps = {
  episode: LiveJourney["combat_episode"]
}

/** The reference tone classification for one combat line. */
function combatLineTone(text: string): string {
  if (/is dead!|death cry|you receive .*experience/i.test(text)) {
    return "text-success font-[650]"
  }
  if (/critical|obliterate|annihilate|massacre/i.test(text)) {
    return "text-warning"
  }
  if (
    /hits you|slashes you|pierces you|pounds you|crushes you|rakes you|bites you|kicks you|you are dead/i.test(
      text
    )
  ) {
    return "text-danger"
  }
  return "text-content-muted"
}

/**
 * The active combat feed over the map: opponent, exchange count, and
 * the classified combat lines, following the newest.
 */
function CombatPanel({ episode }: CombatPanelProps) {
  const streamRef = useRef<HTMLDivElement>(null)
  const latestSequence = episode?.lines.at(-1)?.sequence
  useEffect(() => {
    const stream = streamRef.current
    if (stream !== null) stream.scrollTop = stream.scrollHeight
  }, [latestSequence])

  if (episode === null || !episode.active) return null

  const since =
    episode.first_observed_turn === null
      ? "turn unknown"
      : `since turn ${episode.first_observed_turn}`

  return (
    <aside
      aria-label="Active combat"
      data-map-focus-occluder="true"
      className="absolute top-[18px] left-[18px] z-[6] w-[340px] overflow-hidden rounded-[14px] border border-[color-mix(in_srgb,var(--danger)_24%,var(--line))] bg-(image:--combat-panel-bg) shadow-[0_18px_50px_-20px_#000]"
    >
      <header className="flex items-center gap-[9px] border-b border-[color-mix(in_srgb,var(--danger)_24%,var(--line))] bg-(--combat-header-bg) px-3.5 py-[11px]">
        <span
          aria-hidden="true"
          className="grid size-[26px] flex-none place-items-center rounded-[8px] bg-(--combat-icon-bg) text-danger"
        >
          ⚔
        </span>
        <div className="min-w-0">
          <strong className="block truncate text-[13.5px] text-content-primary">
            {episode.opponent === null
              ? "In combat"
              : `In combat: ${episode.opponent}`}
          </strong>
          <small className="mt-px block text-[11px] text-content-quiet">
            {episode.lines.length} combat{" "}
            {episode.lines.length === 1 ? "event" : "events"} · {since}
          </small>
        </div>
      </header>
      <div
        ref={streamRef}
        role="log"
        aria-live="polite"
        aria-label="Combat events"
        className="max-h-[138px] [scrollbar-width:thin] [scrollbar-color:color-mix(in_srgb,var(--danger)_32%,transparent)_transparent] overflow-y-auto px-3.5 py-2.5 font-mono text-[12px] leading-[1.7]"
      >
        {episode.lines.map((line) => (
          <span
            key={`${line.sequence}:${line.evidence}`}
            className={cn("block", combatLineTone(line.text))}
          >
            {line.text}
          </span>
        ))}
      </div>
    </aside>
  )
}

export { CombatPanel, combatLineTone, type CombatPanelProps }
