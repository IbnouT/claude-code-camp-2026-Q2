import {
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type { LiveAgentExcerpt } from "../contracts";

type Props = {
  expanded: boolean;
  thought: LiveAgentExcerpt;
  onToggle: () => void;
};

export function LiveThoughtDock({
  expanded,
  thought,
  onToggle,
}: Props) {
  const phase = thought.phase === "reasoning"
    ? "Thinking"
    : thought.phase === "plan"
      ? "Planning"
      : "Acting";
  return (
    <aside
      aria-label="Agent thought"
      className={[
        "live-map-dock",
        "live-thought-dock",
        expanded ? "is-expanded" : "is-collapsed",
      ].join(" ")}
      data-map-overlay-edge="bottom"
      data-map-focus-occluder="true"
    >
      <button
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse agent thought" : "Expand agent thought"}
        className="live-map-dock-toggle"
        type="button"
        onClick={onToggle}
      >
        <span>Agent · {phase}</span>
        {expanded
          ? <ChevronDown aria-hidden="true" size={14} />
          : <ChevronUp aria-hidden="true" size={14} />}
      </button>
      {expanded ? (
        <div className="live-thought-dock-body">
          <p>{thought.text}</p>
          <small title={`Observed ${thought.observed_at}`}>
            {thought.evidence} · line {thought.line}
          </small>
        </div>
      ) : null}
    </aside>
  );
}
