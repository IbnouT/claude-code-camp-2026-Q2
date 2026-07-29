import { Eye, ScanSearch } from "lucide-react";

type Props = {
  evidenceActive?: boolean;
  roomTitle?: string | null;
  roomConfidence?: string | null;
  parseMissRate?: number | null;
  evidenceCount?: number;
};

export function BeliefReality({
  evidenceActive = false,
  roomTitle,
  roomConfidence,
  parseMissRate,
  evidenceCount = 4,
}: Props) {
  return (
    <section className="belief-panel" aria-labelledby="belief-title">
      <header className="rail-heading compact">
        <div>
          <p className="eyebrow">Selected moment</p>
          <h2 id="belief-title">Belief vs reality</h2>
        </div>
        <button className="icon-button" type="button" aria-label="Open evidence lens">
          <ScanSearch size={16} aria-hidden="true" />
        </button>
      </header>
      <div className="belief-comparison">
        <article className="belief-cell agent-belief">
          <span className="cell-label">Agent belief</span>
          <strong>
            {evidenceActive
              ? "No belief event captured"
              : roomTitle ?? "Journey complete"}
          </strong>
          <p>
            {evidenceActive
              ? "This prefix contains gateway evidence only."
              : roomConfidence
              ? `Parsed room with ${roomConfidence} confidence.`
              : "“I have reached the destination.”"}
          </p>
          <span className="unsupported-tag">
            {evidenceActive
              ? "Instrumentation gap"
              : roomConfidence
                ? "Parsed inference"
                : "Unsupported claim"}
          </span>
        </article>
        <article className="belief-cell observed-state">
          <span className="cell-label">Observed state</span>
          <strong>
            {evidenceActive
              ? roomTitle ?? "No parsed room yet"
              : roomTitle ? "Evidence selected" : "Objective unmet"}
          </strong>
          <p>
            {evidenceActive && (parseMissRate === null || parseMissRate === undefined)
              ? `${evidenceCount} committed ${
                evidenceCount === 1 ? "event exists" : "events exist"
              } in this prefix.`
              : parseMissRate === null || parseMissRate === undefined
              ? "No evidence names the Massive Minotaur."
              : `${Math.round(parseMissRate * 100)}% of source lines remain unparsed.`}
          </p>
          <button type="button" className="evidence-link">
            <Eye size={13} aria-hidden="true" />
            {evidenceCount} {evidenceCount === 1 ? "evidence link" : "evidence links"}
          </button>
        </article>
      </div>
    </section>
  );
}
