import type {
  MapCameraMode,
  MapMode,
} from "./mapPresentation";

type Props = {
  camera: MapCameraMode;
  mode: MapMode;
  variant?: "full" | "session";
  selectedRoomId: string | null;
  zoom: number;
  minimumZoom: number;
  maximumZoom: number;
  onCameraChange: (camera: MapCameraMode) => void;
  onModeChange: (mode: MapMode) => void;
  onReflow: () => void;
  onZoom: (direction: "in" | "out") => void;
};

const mapModes: { id: MapMode; label: string }[] = [
  { id: "grow", label: "Grow" },
  { id: "focus", label: "Focus" },
  { id: "lantern", label: "Lantern" },
];

export function LiveMapToolbar({
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
}: Props) {
  const fitLabel = selectedRoomId === null ? "Fit map" : "Fit selection";
  return (
    <div
      className={[
        "live-map-toolbar",
        variant === "session" ? "is-session" : "",
      ].filter(Boolean).join(" ")}
      data-map-overlay-edge="top"
      data-map-focus-occluder="true"
    >
      <div
        aria-label="Map camera"
        className="live-map-toolbar-group"
        role="group"
      >
        <small>Camera</small>
        <button
          aria-pressed={camera === "follow"}
          title="Keep the current room within the central follow zone"
          type="button"
          onClick={() => onCameraChange("follow")}
        >
          Follow
        </button>
        <button
          aria-pressed={camera === "manual"}
          title="Freeze the camera at its current center and scale"
          type="button"
          onClick={() => onCameraChange("manual")}
        >
          Manual
        </button>
        <button
          aria-pressed={camera === "fit"}
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
      <div
        aria-label="Map presentation"
        className="live-map-toolbar-group"
        role="group"
      >
        <small>Map</small>
        {mapModes.map((item) => (
          <button
            aria-pressed={mode === item.id}
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
          className="live-map-toolbar-tool live-map-reflow"
          title="Recalculate room positions from retained evidence"
          type="button"
          onClick={onReflow}
        >
          Reflow
        </button>
      ) : null}
      <button
        aria-label="Zoom in"
        className="live-map-toolbar-tool"
        disabled={zoom >= maximumZoom}
        title={
          zoom >= maximumZoom ? "Maximum zoom reached" : "Zoom in"
        }
        type="button"
        onClick={() => onZoom("in")}
      >
        +
      </button>
      <button
        aria-label="Zoom out"
        className="live-map-toolbar-tool"
        disabled={zoom <= minimumZoom}
        title={
          zoom <= minimumZoom ? "Minimum zoom reached" : "Zoom out"
        }
        type="button"
        onClick={() => onZoom("out")}
      >
        −
      </button>
    </div>
  );
}
