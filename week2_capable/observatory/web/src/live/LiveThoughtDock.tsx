import {
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type { LiveAgentExcerpt } from "../contracts";
import { formatAge } from "./liveEvidence";

type Props = {
  expanded: boolean;
  historical?: boolean;
  thought: LiveAgentExcerpt | null;
  onToggle: () => void;
};

export function LiveThoughtDock({
  expanded,
  historical = false,
  thought,
  onToggle,
}: Props) {
  const phase = thought?.phase === "reasoning"
    ? "Thinking"
    : thought?.phase === "plan"
      ? "Planning"
      : thought === null
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
      data-map-marker-occluder="true"
    >
      <button
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse agent thought" : "Expand agent thought"}
        className="live-map-dock-toggle"
        type="button"
        onClick={onToggle}
      >
        <span>
          Agent · {phase}
          {thought === null
            ? ""
            : ` · ${historical
              ? formatHistoricalTime(thought.observed_at)
              : formatAge(thought.observed_at)}`}
        </span>
        {expanded
          ? <ChevronDown aria-hidden="true" size={14} />
          : <ChevronUp aria-hidden="true" size={14} />}
      </button>
      {expanded ? (
        <div className="live-thought-dock-body">
          {thought === null ? (
            <p>Agent thought not observed.</p>
          ) : (
            <>
              <p>{thought.text}</p>
              <small title={`Observed ${thought.observed_at}`}>
                {thought.evidence} · line {thought.line}
              </small>
            </>
          )}
        </div>
      ) : null}
    </aside>
  );
}

function formatHistoricalTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  }).format(date);
}
