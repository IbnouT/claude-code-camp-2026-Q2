import {
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type { MapLegendEntry } from "./mapLegend";

type Props = {
  entries: MapLegendEntry[];
  expanded: boolean;
  onToggle: () => void;
};

export function LiveMapLegend({
  entries,
  expanded,
  onToggle,
}: Props) {
  return (
    <aside
      aria-label="Map evidence legend"
      className={[
        "live-map-dock",
        "live-map-legend",
        expanded ? "is-expanded" : "is-collapsed",
      ].join(" ")}
      data-map-overlay-edge="bottom"
      data-map-focus-occluder="true"
    >
      <button
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse map legend" : "Expand map legend"}
        className="live-map-dock-toggle"
        type="button"
        onClick={onToggle}
      >
        <span>Legend</span>
        {expanded
          ? <ChevronDown aria-hidden="true" size={14} />
          : <ChevronUp aria-hidden="true" size={14} />}
      </button>
      {expanded ? (
        <ul className="live-map-legend-entries">
          {entries.map((entry) => (
            <li key={entry.kind}>
              <span
                aria-hidden="true"
                className={`live-map-legend-swatch is-${entry.kind}`}
              />
              <span>{entry.label}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </aside>
  );
}
