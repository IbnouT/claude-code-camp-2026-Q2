import { memo, useRef } from "react"
import type { KeyboardEvent } from "react"

import { cn } from "@/lib/utils"

import { mapRoomHeight, mapRoomWidth, type MapPoint } from "./mapModel"
import { truncateMapRoomTitle } from "./mapRoomFootprint"
import type { VerticalMarker } from "./markerProjection"
import type { WorldNode } from "./world-types"

type MapRoomProps = {
  node: WorldNode
  point: MapPoint
  current: boolean
  selected: boolean
  combat: boolean
  beacon: boolean
  verticalMarkers: VerticalMarker[]
  onSelect: (nodeId: string) => void
}

type RoomState = "" | "is-combat" | "is-current" | "is-selected" | "is-beacon"

/**
 * The sector paint family for a room rect. Water spelled exactly takes the
 * dedicated water pair while the wider water family (water sub-sectors,
 * flying, underwater) shares the current-room pair. City and unknown sectors
 * keep the base room pair.
 */
type SectorPaint =
  | "room"
  | "temple"
  | "shop"
  | "dark"
  | "route"
  | "interior"
  | "underground"
  | "urban"
  | "open-land"
  | "current"
  | "water"
  | "highland"
  | "woodland"
  | "commerce"
  | "civic"
  | "sacred"
  | "special"

const sectorFill: Record<SectorPaint, string> = {
  room: "fill-(--map-room)",
  temple: "fill-(--map-temple)",
  shop: "fill-(--map-shop)",
  dark: "fill-(--map-dark)",
  route: "fill-(--map-route)",
  interior: "fill-(--map-interior)",
  underground: "fill-(--map-underground)",
  urban: "fill-(--map-urban)",
  "open-land": "fill-(--map-open-land)",
  current: "fill-(--map-current)",
  water: "fill-(--map-water)",
  highland: "fill-(--map-highland)",
  woodland: "fill-(--map-woodland)",
  commerce: "fill-(--map-commerce)",
  civic: "fill-(--map-civic)",
  sacred: "fill-(--map-sacred)",
  special: "fill-(--map-special)",
}

const sectorStroke: Record<SectorPaint, string> = {
  room: "stroke-(--map-room-line)",
  temple: "stroke-(--map-temple-line)",
  shop: "stroke-(--map-shop-line)",
  dark: "stroke-(--map-dark-line)",
  route: "stroke-(--map-route-line)",
  interior: "stroke-(--map-interior-line)",
  underground: "stroke-(--map-underground-line)",
  urban: "stroke-(--map-urban-line)",
  "open-land": "stroke-(--map-open-land-line)",
  current: "stroke-(--map-current-line)",
  water: "stroke-(--map-water-line)",
  highland: "stroke-(--map-highland-line)",
  woodland: "stroke-(--map-woodland-line)",
  commerce: "stroke-(--map-commerce-line)",
  civic: "stroke-(--map-civic-line)",
  sacred: "stroke-(--map-sacred-line)",
  special: "stroke-(--map-special-line)",
}

export function sectorPaint(sector: string | undefined): SectorPaint {
  const normalized = sector?.trim().toLowerCase() ?? "unknown"
  if (normalized === "field" || normalized === "forest") return "temple"
  if (normalized === "inside" || normalized === "hills") return "shop"
  if (normalized === "mountain") return "dark"
  if (normalized === "water") return "water"
  if (
    normalized.startsWith("water") ||
    normalized === "flying" ||
    normalized === "underwater"
  ) {
    return "current"
  }
  if (normalized === "route") return "route"
  if (normalized === "interior") return "interior"
  if (normalized === "underground") return "underground"
  if (normalized === "urban") return "urban"
  if (normalized === "open land" || normalized === "open-land") {
    return "open-land"
  }
  if (normalized === "highland") return "highland"
  if (normalized === "woodland") return "woodland"
  if (normalized === "commerce") return "commerce"
  if (normalized === "civic") return "civic"
  if (normalized === "sacred") return "sacred"
  if (normalized === "special") return "special"
  return "room"
}

export function roomStateClass({
  combat,
  current,
  selected,
  beacon,
}: {
  combat: boolean
  current: boolean
  selected: boolean
  beacon: boolean
}): RoomState {
  if (combat && current) return "is-combat"
  if (current) return "is-current"
  if (selected) return "is-selected"
  if (beacon) return "is-beacon"
  return ""
}

/**
 * The main rect paint, applied in the frozen override order: sector base,
 * then candidate, beacon, selected, current, combat. Each later state
 * replaces only the properties it sets, so a candidate keeps its dash under
 * a selected stroke.
 */
function roomRectClass({
  sector,
  candidate,
  state,
  selected,
}: {
  sector: SectorPaint
  candidate: boolean
  state: RoomState
  selected: boolean
}): string {
  let fill = sectorFill[sector]
  let stroke = sectorStroke[sector]
  let width = "stroke-1"
  let dash = ""
  if (candidate) {
    fill = "fill-none"
    stroke = "stroke-[#6a5a2a]"
    dash = "[stroke-dasharray:4_3]"
  }
  if (state === "is-beacon") {
    fill = "fill-(--map-shop)"
    stroke = "stroke-(--warning)"
    width = "stroke-2"
  }
  if (selected) {
    stroke = "stroke-[#5db4ff]"
    width = "stroke-2"
  }
  if (state === "is-current") {
    fill = "fill-(--map-current)"
    stroke = "stroke-(--map-current-line)"
    width = "stroke-2"
  }
  if (state === "is-combat") {
    fill = "fill-[#3a1620]"
    stroke = "stroke-[#ff5d6c]"
    width = "stroke-2"
  }
  return cn(
    fill,
    stroke,
    width,
    dash,
    "group-focus-visible:stroke-[#5db4ff] group-focus-visible:stroke-2"
  )
}

/**
 * The title paint, in the frozen override order: current, candidate,
 * selected, beacon, combat. Weight 600 comes from the current and combat
 * states and survives a selected fill.
 */
function roomTitleClass({
  candidate,
  state,
  selected,
}: {
  candidate: boolean
  state: RoomState
  selected: boolean
}): string {
  const fill =
    state === "is-combat"
      ? "fill-[#ff5d6c]"
      : state === "is-beacon"
        ? "fill-(--warning)"
        : selected
          ? "fill-[#5db4ff]"
          : candidate
            ? "fill-[#b79a4a]"
            : state === "is-current"
              ? "fill-(--content-primary)"
              : "fill-(--content-muted)"
  return cn(
    "pointer-events-none text-[10.5px] [paint-order:stroke_fill]",
    "stroke-(--canvas) stroke-[3px] [stroke-linejoin:round] [text-anchor:middle]",
    fill,
    (state === "is-current" || state === "is-combat") && "font-semibold"
  )
}

/**
 * One learned room on the map: the sector-painted rect with its state
 * overrides, vertical markers, visit and sighting badges, identity text,
 * and title.
 */
const MapRoom = memo(function MapRoom({
  node,
  point,
  current,
  selected,
  combat,
  beacon,
  verticalMarkers,
  onSelect,
}: MapRoomProps) {
  const renderCount = useRef(0)
  renderCount.current += 1
  const identityLabel =
    node.atlas === null || node.atlas === undefined
      ? `${node.title}, observed place ${node.place}`
      : `${node.title}, atlas-correlated vnum ${node.atlas.vnum}, ` +
        `${node.atlas.confidence} confidence`
  const contentLabel = [
    node.mob_sightings.length > 0
      ? `${node.mob_sightings.length} mob sighting`
      : "",
    node.object_sightings.length > 0
      ? `${node.object_sightings.length} object sighting`
      : "",
  ]
    .filter(Boolean)
    .join(", ")
  const accessibleLabel =
    contentLabel.length === 0
      ? identityLabel
      : `${identityLabel}, ${contentLabel}`
  const state = roomStateClass({ combat, current, selected, beacon })
  const candidate = node.state === "candidate"
  const hasMobSighting = node.mob_sightings.length > 0
  const visitBadgeX = hasMobSighting ? mapRoomWidth - 16 : mapRoomWidth
  const select = () => onSelect(node.id)
  const handleKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return
    event.preventDefault()
    select()
  }

  return (
    <g
      className="group cursor-pointer outline-none"
      data-room-id={node.id}
      data-render-count={
        import.meta.env.MODE === "test" ? renderCount.current : undefined
      }
      transform={`translate(${point.x} ${point.y})`}
      aria-label={current ? `Agent in ${accessibleLabel}` : accessibleLabel}
      aria-pressed={selected}
      role="button"
      tabIndex={0}
      onClick={select}
      onKeyDown={handleKeyDown}
    >
      <title>{identityLabel}</title>
      {current ? (
        <circle
          className="pointer-events-none"
          fill="url(#live-current-room-glow)"
          cx={mapRoomWidth / 2}
          cy={mapRoomHeight / 2}
          r="48"
        />
      ) : null}
      {selected ? (
        <rect
          className="pointer-events-none fill-none stroke-[rgb(93_180_255/34%)] [stroke-width:1.25] [filter:drop-shadow(0_0_5px_rgb(93_180_255/28%))_drop-shadow(0_0_11px_rgb(93_180_255/16%))]"
          height={mapRoomHeight + 12}
          rx="16"
          vectorEffect="non-scaling-stroke"
          width={mapRoomWidth + 12}
          x="-6"
          y="-6"
        />
      ) : null}
      <rect
        className={roomRectClass({
          sector: sectorPaint(node.atlas?.sector),
          candidate,
          state,
          selected,
        })}
        width={mapRoomWidth}
        height={mapRoomHeight}
        rx="10"
        vectorEffect="non-scaling-stroke"
      />
      {verticalMarkers.map((marker) => (
        <text
          className={cn(
            "pointer-events-none fill-(--map-vertical) text-[10px] font-bold [text-anchor:middle]",
            marker.state === "frontier" && "opacity-[.48]"
          )}
          data-direction={marker.direction}
          data-state={marker.state}
          key={marker.direction}
          x="10"
          y={marker.direction === "up" ? 15 : mapRoomHeight - 7}
        >
          {marker.direction === "up" ? "▲" : "▼"}
        </text>
      ))}
      {node.visits > 1 ? (
        <g
          className="pointer-events-none"
          data-shifted={hasMobSighting ? "true" : "false"}
          data-visits={node.visits}
        >
          <circle
            className="fill-(--surface-raised) stroke-(--map-room-line) stroke-1"
            cx={visitBadgeX}
            cy="0"
            r="10"
            vectorEffect="non-scaling-stroke"
          />
          <text
            className="fill-(--content-muted) text-[9px] [text-anchor:middle]"
            x={visitBadgeX}
            y="3.5"
          >
            ×{node.visits}
          </text>
        </g>
      ) : null}
      {hasMobSighting ? (
        <g
          aria-label={`${node.mob_sightings.length} mob sighting`}
          className="pointer-events-none"
          data-count={node.mob_sightings.length}
          role="img"
        >
          <circle
            className="fill-[#35131b] stroke-[#ff5d6c] [stroke-width:1.25]"
            cx={mapRoomWidth - 2}
            cy="0"
            r={current ? 8 : 7}
            vectorEffect="non-scaling-stroke"
          />
          <text
            className="fill-[#ff8178] text-[8px] font-bold [text-anchor:middle]"
            x={mapRoomWidth - 2}
            y="2.8"
          >
            ☠
          </text>
        </g>
      ) : null}
      {node.object_sightings.length > 0 ? (
        <g
          aria-label={`${node.object_sightings.length} object sighting`}
          className="pointer-events-none"
          data-count={node.object_sightings.length}
          role="img"
        >
          <circle
            className="fill-[#33270f] stroke-(--warning) [stroke-width:1.25]"
            cx="-2"
            cy={mapRoomHeight - 2}
            r="7"
            vectorEffect="non-scaling-stroke"
          />
          <text
            className="fill-(--warning) text-[8px] font-bold [text-anchor:middle]"
            x="-2"
            y={mapRoomHeight + 1}
          >
            ◇
          </text>
        </g>
      ) : null}
      <text
        className={cn(
          "pointer-events-none fill-(--content-primary) text-[10px] font-bold [text-anchor:middle]",
          state === "is-combat" && "fill-white"
        )}
        x={mapRoomWidth / 2}
        y={mapRoomHeight / 2 + 4}
      >
        {node.atlas === null || node.atlas === undefined
          ? `p${node.place}`
          : `#${node.atlas.vnum}`}
      </text>
      <text
        className={roomTitleClass({ candidate, state, selected })}
        x={mapRoomWidth / 2}
        y={current ? -14 : mapRoomHeight + 18}
      >
        {truncateMapRoomTitle(node.title)}
      </text>
    </g>
  )
}, sameRoomRender)

function sameRoomRender(previous: MapRoomProps, next: MapRoomProps): boolean {
  return (
    previous.node.id === next.node.id &&
    previous.node.title === next.node.title &&
    previous.node.place === next.node.place &&
    previous.node.state === next.node.state &&
    previous.node.atlas?.vnum === next.node.atlas?.vnum &&
    previous.node.atlas?.confidence === next.node.atlas?.confidence &&
    previous.node.atlas?.sector === next.node.atlas?.sector &&
    previous.node.visits === next.node.visits &&
    sameSightings(previous.node.mob_sightings, next.node.mob_sightings) &&
    sameSightings(previous.node.object_sightings, next.node.object_sightings) &&
    sameVerticalMarkers(previous.verticalMarkers, next.verticalMarkers) &&
    previous.point.x === next.point.x &&
    previous.point.y === next.point.y &&
    previous.current === next.current &&
    previous.selected === next.selected &&
    previous.combat === next.combat &&
    previous.beacon === next.beacon &&
    previous.onSelect === next.onSelect
  )
}

function sameSightings(
  previous: WorldNode["mob_sightings"],
  next: WorldNode["mob_sightings"]
): boolean {
  return (
    previous.length === next.length &&
    previous.every((sighting, index) => {
      const candidate = next[index]
      return (
        sighting.name === candidate?.name &&
        sighting.count === candidate.count &&
        sighting.last_seq === candidate.last_seq
      )
    })
  )
}

function sameVerticalMarkers(
  previous: VerticalMarker[],
  next: VerticalMarker[]
): boolean {
  return (
    previous.length === next.length &&
    previous.every((marker, index) => {
      const candidate = next[index]
      return (
        marker.direction === candidate?.direction &&
        marker.state === candidate.state
      )
    })
  )
}

export { MapRoom, type MapRoomProps }
