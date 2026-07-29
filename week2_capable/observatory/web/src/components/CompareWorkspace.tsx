import {
  BadgeCheck,
  GitCompareArrows,
  Orbit,
  Sigma,
} from "lucide-react";
import type { RunComparison } from "../data/comparison";
import { RouteFingerprint } from "./RouteFingerprint";

type Props = {
  comparison: RunComparison;
  selected: number;
  onSelect: (index: number) => void;
};

const modeLabel = {
  raw: "Raw text",
  minimal: "Minimal envelope",
  full: "Full envelope",
};

export function CompareWorkspace({ comparison, selected, onSelect }: Props) {
  const maxCost = Math.max(...comparison.cohorts.map((cohort) => cohort.cost_mean));
  return (
    <section className="compare-workspace" aria-labelledby="compare-title">
      <header className="compare-toolbar">
        <div>
          <p className="eyebrow">Evidence-aligned experiment</p>
          <h2 id="compare-title">{comparison.title}</h2>
        </div>
        <button
          type="button"
          className="divergence-jump"
          onClick={() => onSelect(comparison.divergence.index ?? 1)}
        >
          <GitCompareArrows size={14} aria-hidden="true" />
          First divergence · action {comparison.divergence.index ?? "none"}
        </button>
      </header>

      <div className="cohort-grid">
        {comparison.cohorts.map((cohort) => (
          <article key={cohort.mode} className={`cohort-card mode-${cohort.mode}`}>
            <header>
              <span>{modeLabel[cohort.mode]}</span>
              <small>{cohort.samples} reset runs</small>
            </header>
            <div className="cohort-outcome">
              <BadgeCheck size={16} aria-hidden="true" />
              <strong>{cohort.successes}/{cohort.samples}</strong>
              <span>journeys verified</span>
            </div>
            <div className="cost-measure">
              <span style={{ width: `${cohort.cost_mean / maxCost * 100}%` }} />
            </div>
            <dl>
              <div><dt>Mean cost</dt><dd>${cohort.cost_mean.toFixed(4)}</dd></div>
              <div><dt>Mean calls</dt><dd>{cohort.calls_mean.toFixed(1)}</dd></div>
              <div><dt>Movement</dt><dd>
                {(cohort.attention.movement_share * 100).toFixed(0)}%
              </dd></div>
            </dl>
          </article>
        ))}
      </div>

      <div className="compare-detail-grid">
        <section className="route-comparison" aria-labelledby="routes-title">
          <header>
            <div>
              <p className="eyebrow">Synchronized semantic paths</p>
              <h3 id="routes-title">Route shape at action {selected}</h3>
            </div>
            <span>room transitions, not wall clock</span>
          </header>
          <div className="route-lanes">
            {comparison.lanes.map((lane) => (
              <article key={lane.mode}>
                <span className={`mode-dot mode-${lane.mode}`} />
                <strong>{lane.mode}</strong>
                <RouteFingerprint lane={lane} through={selected} />
              </article>
            ))}
          </div>
        </section>

        <section className="counterfactual-panel" aria-labelledby="counterfactual-title">
          <header>
            <div>
              <p className="eyebrow">Free deterministic replay</p>
              <h3 id="counterfactual-title">Same evidence, three renderings</h3>
            </div>
            <Orbit size={15} aria-hidden="true" />
          </header>
          <div className="counterfactual-list">
            {comparison.counterfactuals.map((projection) => (
              <article key={projection.mode}>
                <span className={`mode-dot mode-${projection.mode}`} />
                <strong>{projection.mode}</strong>
                <b>{projection.bytes.toLocaleString()} B</b>
                <small>
                  ≈ {projection.estimated_tokens.toLocaleString()} tokens
                  {projection.mode === "raw"
                    ? " · baseline"
                    : ` · ${projection.delta_from_raw > 0 ? "+" : ""}${(
                        projection.delta_from_raw * 100
                      ).toFixed(1)}%`}
                </small>
              </article>
            ))}
          </div>
          <div className="parser-replay-summary">
            <span>Canonical parser replay</span>
            <strong>
              {comparison.parser_counterfactuals.filter(
                (projection) => projection.typed_delta === 0,
              ).length}/{comparison.parser_counterfactuals.length} exact
            </strong>
            <small>
              {comparison.parser_counterfactuals[0]?.recorded_version ?? "unknown"}
              {" → "}
              {comparison.parser_counterfactuals[0]?.replayed_version ?? "unknown"}
            </small>
          </div>
          <p>
            <Sigma size={12} aria-hidden="true" />
            Payload replay changes no model decision. Cohort cards above carry
            the measured journey effect.
          </p>
        </section>
      </div>
    </section>
  );
}
