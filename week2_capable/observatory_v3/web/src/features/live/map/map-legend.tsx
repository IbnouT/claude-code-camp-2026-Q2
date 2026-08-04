import { ChevronDownIcon, ChevronUpIcon } from "lucide-react"

import { cn } from "@/lib/utils"

import type { MapLegendEntry, MapLegendKind } from "./mapLegend"

type MapLegendProps = {
  entries: MapLegendEntry[]
  expanded: boolean
  inspectorOpen?: boolean
  onToggle: () => void
}

const swatchBase = "flex-none rounded-[4px] border"

const swatchClass: Record<MapLegendKind, string> = {
  room: "size-3.5 border-(--map-room-line) bg-(--map-room)",
  current: "size-3.5 border-(--map-current-line) bg-(--map-current)",
  selected:
    "size-3.5 border-[rgb(93_180_255/70%)] bg-transparent shadow-[0_0_7px_rgb(93_180_255/38%)]",
  frontier:
    "h-0 w-4 rounded-none border-0 border-t-2 border-dashed border-t-(--map-frontier) bg-transparent",
  continuation: "relative size-3.5 border-0 bg-transparent",
  vertical: "relative size-3.5 border-0 bg-transparent",
  visits:
    "size-3.5 rounded-full border-(--map-room-line) bg-(--surface-raised)",
  beacon: "size-3.5 border-(--warning) bg-(--map-shop)",
  mob: "relative size-[13px] rounded-full border-[#ff5d6c] bg-[#35131b]",
  object: "relative size-[13px] rounded-full border-(--warning) bg-[#33270f]",
}

/** The glyph inside a swatch, for the kinds that carry one. */
function swatchGlyph(kind: MapLegendKind) {
  if (kind === "continuation") {
    return (
      <span className="absolute inset-x-0 -top-1 bottom-0 text-center text-[20px] leading-[14px] text-[#b99cff]">
        »
      </span>
    )
  }
  if (kind === "vertical") {
    return (
      <span className="absolute inset-0 text-center text-[10px] text-(--map-vertical)">
        ▲
      </span>
    )
  }
  if (kind === "visits") {
    return (
      <span className="block text-center text-[7px] leading-3 text-content-muted">
        ×N
      </span>
    )
  }
  if (kind === "mob") {
    return (
      <span className="absolute inset-0 text-center text-[8px] leading-[11px] text-[#ff8178]">
        ☠
      </span>
    )
  }
  if (kind === "object") {
    return (
      <span className="absolute inset-0 text-center text-[8px] leading-[11px] text-warning">
        ◇
      </span>
    )
  }
  return null
}

/**
 * The map evidence legend dock in the stage's bottom-right corner: one
 * swatch per visible evidence kind, collapsible, sliding left while the
 * room inspector is open.
 */
function MapLegend({
  entries,
  expanded,
  inspectorOpen = false,
  onToggle,
}: MapLegendProps) {
  return (
    <aside
      aria-label="Map evidence legend"
      className={cn(
        "pointer-events-none absolute bottom-[18px] z-[7] w-[190px] overflow-hidden rounded-[12px] border border-line-strong bg-[color-mix(in_srgb,var(--surface)_62%,transparent)] text-content-primary shadow-popover backdrop-blur-[7px] backdrop-saturate-105 [transition:right_160ms_ease]",
        inspectorOpen ? "right-[336px]" : "right-[18px]"
      )}
      data-map-overlay-edge="bottom"
      data-map-focus-occluder="true"
    >
      <button
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse map legend" : "Expand map legend"}
        className="pointer-events-auto flex min-h-9 w-full cursor-pointer items-center justify-between gap-3 px-[11px] py-2 text-[9.5px] font-semibold tracking-[0.12em] text-content-quiet uppercase hover:bg-surface-raised hover:text-content-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        type="button"
        onClick={onToggle}
      >
        <span>Legend</span>
        {expanded ? (
          <ChevronDownIcon aria-hidden="true" className="size-3.5" />
        ) : (
          <ChevronUpIcon aria-hidden="true" className="size-3.5" />
        )}
      </button>
      {expanded ? (
        <ul className="m-0 grid list-none gap-1.5 px-3 pt-0 pb-[11px]">
          {entries.map((entry) => (
            <li
              className="flex items-center gap-2 text-[11px] text-content-muted"
              key={entry.kind}
            >
              <span
                aria-hidden="true"
                className={cn(swatchBase, swatchClass[entry.kind])}
              >
                {swatchGlyph(entry.kind)}
              </span>
              <span>{entry.label}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </aside>
  )
}

export { MapLegend, type MapLegendProps }
