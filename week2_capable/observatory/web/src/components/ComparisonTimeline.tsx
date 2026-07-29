import { GitCompareArrows } from "lucide-react";
import type { RunComparison } from "../data/comparison";

type Props = {
  comparison: RunComparison;
  selected: number;
  onSelect: (index: number) => void;
};

export function ComparisonTimeline({
  comparison,
  selected,
  onSelect,
}: Props) {
  const length = Math.max(...comparison.lanes.map((lane) => lane.milestones.length));
  return (
    <section className="comparison-timeline" aria-labelledby="alignment-title">
      <header>
        <div>
          <p className="eyebrow">Semantic run alignment</p>
          <h2 id="alignment-title">First meaningful divergence</h2>
        </div>
        <span>
          <GitCompareArrows size={13} aria-hidden="true" />
          action {comparison.divergence.index ?? "none"} · {comparison.divergence.summary}
        </span>
      </header>
      <div className="alignment-scroll">
        <div
          className="alignment-grid"
          style={{ gridTemplateColumns: `72px repeat(${length}, minmax(76px, 1fr))` }}
        >
          {comparison.lanes.map((lane) => (
            <div className="alignment-row" key={lane.mode}>
              <strong className={`lane-label mode-${lane.mode}`}>{lane.mode}</strong>
              {Array.from({ length }, (_, offset) => {
                const milestone = lane.milestones[offset];
                const index = offset + 1;
                return (
                  <button
                    key={index}
                    type="button"
                    className={[
                      "alignment-cell",
                      index === selected ? "is-selected" : "",
                      index === comparison.divergence.index ? "is-divergence" : "",
                      milestone ? `kind-${milestone.kind}` : "is-empty",
                    ].join(" ")}
                    onClick={() => onSelect(index)}
                    disabled={!milestone}
                  >
                    <small>{index}</small>
                    <span>{milestone?.label ?? "—"}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
