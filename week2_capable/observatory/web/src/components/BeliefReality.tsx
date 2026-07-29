import { Eye, ScanSearch } from "lucide-react";

export function BeliefReality() {
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
          <strong>Journey complete</strong>
          <p>“I have reached the destination.”</p>
          <span className="unsupported-tag">Unsupported claim</span>
        </article>
        <article className="belief-cell observed-state">
          <span className="cell-label">Observed state</span>
          <strong>Objective unmet</strong>
          <p>No evidence names the Massive Minotaur.</p>
          <button type="button" className="evidence-link">
            <Eye size={13} aria-hidden="true" />
            4 evidence links
          </button>
        </article>
      </div>
    </section>
  );
}
