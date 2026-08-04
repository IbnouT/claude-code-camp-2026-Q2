import { cn } from "@/lib/utils"

import type { MapCameraMode, MapMode } from "./mapPresentation"

type MapToolbarProps = {
  camera: MapCameraMode
  mode: MapMode
  variant?: "full" | "session"
  selectedRoomId: string | null
  zoom: number
  minimumZoom: number
  maximumZoom: number
  onCameraChange: (camera: MapCameraMode) => void
  onModeChange: (mode: MapMode) => void
  onReflow: () => void
  onZoom: (direction: "in" | "out") => void
}

const mapModes: { id: MapMode; label: string }[] = [
  { id: "grow", label: "Grow" },
  { id: "focus", label: "Focus" },
  { id: "lantern", label: "Lantern" },
]

const groupClass =
  "inline-flex items-center gap-[2px] rounded-[9px] border border-line bg-[color-mix(in_srgb,var(--surface-raised)_92%,transparent)] p-[3px] text-content-quiet"

const groupButtonClass =
  "min-h-7 cursor-pointer rounded-[6px] bg-transparent px-[9px] py-1 text-[11px] text-content-quiet focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-[.48] aria-pressed:bg-accent-soft aria-pressed:text-accent aria-pressed:disabled:opacity-100"

const toolClass =
  "h-[34px] min-h-7 cursor-pointer rounded-[9px] border border-line bg-[color-mix(in_srgb,var(--surface-raised)_92%,transparent)] p-0 text-[16px] text-content-quiet focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-[.48]"

/**
 * The map controls: camera mode, presentation mode, reflow, and zoom,
 * grouped in the stage's top-right corner.
 */
function MapToolbar({
  camera,
  mode,
  variant = "full",
  selectedRoomId,
  zoom,
  minimumZoom,
  maximumZoom,
  onCameraChange,
  onModeChange,
  onReflow,
  onZoom,
}: MapToolbarProps) {
  const fitLabel = selectedRoomId === null ? "Fit map" : "Fit selection"
  return (
    <div
      className="absolute top-3.5 right-[18px] z-[5] flex items-center gap-2"
      data-map-overlay-edge="top"
      data-map-focus-occluder="true"
    >
      <div aria-label="Map camera" className={groupClass} role="group">
        <small className="mr-1 ml-1.5 text-[9px] tracking-[.1em] text-content-quiet uppercase">
          Camera
        </small>
        <button
          aria-pressed={camera === "follow"}
          className={groupButtonClass}
          title="Keep the current room within the central follow zone"
          type="button"
          onClick={() => onCameraChange("follow")}
        >
          Follow
        </button>
        <button
          aria-pressed={camera === "manual"}
          className={groupButtonClass}
          title="Freeze the camera at its current center and scale"
          type="button"
          onClick={() => onCameraChange("manual")}
        >
          Manual
        </button>
        <button
          aria-pressed={camera === "fit"}
          className={groupButtonClass}
          title={
            selectedRoomId === null
              ? "Frame every room and visible frontier"
              : "Frame the current room, selection, and learned path"
          }
          type="button"
          onClick={() => onCameraChange("fit")}
        >
          {fitLabel}
        </button>
      </div>
      <div aria-label="Map presentation" className={groupClass} role="group">
        <small className="mr-1 ml-1.5 text-[9px] tracking-[.1em] text-content-quiet uppercase">
          Map
        </small>
        {mapModes.map((item) => (
          <button
            aria-pressed={mode === item.id}
            className={groupButtonClass}
            key={item.id}
            type="button"
            onClick={() => onModeChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {variant === "full" ? (
        <button
          aria-label="Reflow map"
          className={cn(toolClass, "w-auto px-2.5 text-[11px]")}
          title="Recalculate room positions from retained evidence"
          type="button"
          onClick={onReflow}
        >
          Reflow
        </button>
      ) : null}
      <button
        aria-label="Zoom in"
        className={cn(toolClass, "w-[34px]")}
        disabled={zoom >= maximumZoom}
        title={zoom >= maximumZoom ? "Maximum zoom reached" : "Zoom in"}
        type="button"
        onClick={() => onZoom("in")}
      >
        +
      </button>
      <button
        aria-label="Zoom out"
        className={cn(toolClass, "w-[34px]")}
        disabled={zoom <= minimumZoom}
        title={zoom <= minimumZoom ? "Minimum zoom reached" : "Zoom out"}
        type="button"
        onClick={() => onZoom("out")}
      >
        −
      </button>
    </div>
  )
}

export { MapToolbar, type MapToolbarProps }
