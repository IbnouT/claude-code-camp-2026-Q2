import { XIcon } from "lucide-react"

import { cn } from "@/lib/utils"

import type { RoomInspectorProjection } from "./roomInspector"

type RoomInspectorProps = {
  room: RoomInspectorProjection
  onClose: () => void
}

const chipClass =
  "rounded-[7px] border border-line bg-[color-mix(in_srgb,var(--surface-raised)_60%,transparent)] px-[9px] py-1 text-[11px] text-content-primary"

const evidenceRowClass =
  "flex justify-between gap-3 text-[10.5px] text-content-muted"

/**
 * The selected room's evidence panel: identity, description, exits,
 * sightings, stats, provenance counts, and the atlas reference.
 */
function RoomInspector({ room, onClose }: RoomInspectorProps) {
  const provenanceRows: Array<[string, number]> = [
    ["Room observations", room.evidence.room],
    ["Description observations", room.evidence.description],
    ["Frontier observations", room.evidence.exits],
    ["Sighting observations", room.evidence.sightings],
    ["Economics records", room.evidence.economics],
  ]
  const provenance = provenanceRows.filter(([, count]) => count > 0)

  return (
    <aside
      aria-label={`Room inspector, ${room.title}`}
      className="absolute top-[62px] right-[18px] z-[6] max-h-[calc(100%-80px)] w-[300px] overflow-y-auto rounded-[14px] border border-line-strong bg-[linear-gradient(180deg,color-mix(in_srgb,var(--surface)_50%,var(--accent)_3%),color-mix(in_srgb,var(--surface)_50%,transparent))] text-content-primary shadow-popover backdrop-blur-[5px] backdrop-saturate-95"
      data-map-overlay-edge="right"
      data-room-id={room.id}
    >
      <header className="sticky top-0 z-[1] flex items-start justify-between gap-2.5 border-b border-line bg-[color-mix(in_srgb,var(--surface)_56%,transparent)] px-3.5 py-3">
        <div>
          <div className="flex items-center gap-2">
            <strong className="text-[15px] font-semibold">{room.title}</strong>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-2.5 gap-y-1 text-[11px] text-content-quiet">
            <span>passed ×{room.visits}</span>
            <span>
              first s{room.firstSequence} · last s{room.lastSequence}
            </span>
          </div>
        </div>
        <button
          aria-label="Close room inspector"
          className="grid size-7 flex-none cursor-pointer place-items-center rounded-[7px] border-0 bg-transparent p-0 text-content-quiet hover:bg-surface-raised hover:text-content-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          type="button"
          onClick={onClose}
        >
          <XIcon aria-hidden="true" className="size-[15px]" />
        </button>
      </header>

      <div className="px-3.5 pt-3 pb-3.5">
        {room.description === null ? null : (
          <p className="m-0 mb-3 text-[12px] leading-[1.5] text-content-muted">
            {room.description}
          </p>
        )}

        <InspectorHeading>Exits</InspectorHeading>
        <div className="flex flex-wrap gap-1.5">
          {room.exits.length === 0 ? (
            <span className={cn(chipClass, "text-content-quiet")}>
              none observed
            </span>
          ) : (
            room.exits.map((exit) => (
              <span
                className={cn(
                  chipClass,
                  exit.confirmed ? "" : "text-content-quiet"
                )}
                key={exit.direction}
              >
                {exit.direction}
                {exit.confirmed ? "" : " ?"}
              </span>
            ))
          )}
        </div>

        <InspectorHeading>Seen here</InspectorHeading>
        <SightingList
          empty="no mob sightings retained"
          icon="☠"
          items={room.mobSightings}
          tone="mob"
        />

        <InspectorHeading>Objects known here</InspectorHeading>
        <SightingList
          empty="none retained"
          icon="◇"
          items={room.objectSightings}
          tone="object"
        />

        <div className="mt-3 grid grid-cols-2 gap-2">
          <InspectorStat label="Passed" value={`${room.visits}×`} />
          {room.spendUsd === null ? null : (
            <InspectorStat
              label="Spent here"
              value={`$${room.spendUsd.toFixed(3)}`}
            />
          )}
          <InspectorStat label="Confidence" value={room.confidence} />
        </div>

        {provenance.length === 0 ? null : (
          <>
            <InspectorHeading>Agent evidence</InspectorHeading>
            <dl className="m-0 grid gap-[5px]">
              {provenance.map(([label, count]) => (
                <div className={evidenceRowClass} key={label}>
                  <dt>{label}</dt>
                  <dd className="m-0 font-mono text-content-quiet">{count}</dd>
                </div>
              ))}
            </dl>
          </>
        )}

        {room.atlas === null ? null : (
          <section
            aria-label="Atlas reference"
            className="mt-3.5 rounded-[9px] border border-[color-mix(in_srgb,var(--map-room-line)_72%,transparent)] bg-[color-mix(in_srgb,var(--surface-raised)_46%,transparent)] px-2.5 pt-px pb-[9px]"
          >
            <InspectorHeading className="mt-2">
              Atlas reference
            </InspectorHeading>
            <dl className="m-0 grid gap-[5px]">
              <AtlasRow label="Vnum" value={room.atlas.vnum} />
              <AtlasRow label="Sector" value={room.atlas.sector} />
              <AtlasRow label="Zone" value={room.atlas.zoneLabel} />
              <AtlasRow label="Correlation" value={room.atlas.confidence} />
              <AtlasRow label="Atlas sources" value={room.atlas.sources} />
            </dl>
          </section>
        )}
      </div>
    </aside>
  )
}

function InspectorHeading({
  children,
  className,
}: {
  children: string
  className?: string
}) {
  return (
    <h2
      className={cn(
        "mt-3 mb-1.5 text-[9.5px] font-semibold tracking-[0.12em] text-content-quiet uppercase",
        className
      )}
    >
      {children}
    </h2>
  )
}

function InspectorStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-w-0 gap-[3px] rounded-[8px] border border-line bg-[color-mix(in_srgb,var(--surface-raised)_60%,transparent)] px-[9px] py-2">
      <small className="text-[9.5px] tracking-[0.08em] text-content-quiet uppercase">
        {label}
      </small>
      <strong className="overflow-hidden text-[12px] font-medium text-ellipsis text-content-primary">
        {value}
      </strong>
    </div>
  )
}

function AtlasRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className={evidenceRowClass}>
      <dt>{label}</dt>
      <dd className="m-0 text-right font-mono text-content-quiet">{value}</dd>
    </div>
  )
}

function SightingList({
  empty,
  icon,
  items,
  tone,
}: {
  empty: string
  icon: string
  items: RoomInspectorProjection["mobSightings"]
  tone: "mob" | "object"
}) {
  if (items.length === 0) {
    return <p className="m-0 text-[11px] text-content-quiet">{empty}</p>
  }
  return (
    <ul className="m-0 grid list-none gap-[5px] p-0">
      {items.map((item) => (
        <li
          className="grid grid-cols-[16px_minmax(0,1fr)_auto] items-center gap-2 text-[12px] text-content-primary"
          key={item.name}
        >
          <span
            aria-hidden="true"
            className={tone === "mob" ? "text-danger" : "text-warning"}
          >
            {icon}
          </span>
          <span>{item.name}</span>
          <small className="text-[11px] text-content-quiet">
            ×{item.count}
          </small>
        </li>
      ))}
    </ul>
  )
}

export { RoomInspector, type RoomInspectorProps }
