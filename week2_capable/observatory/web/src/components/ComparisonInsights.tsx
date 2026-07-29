import { AlertCircle, BrainCircuit, DatabaseZap } from "lucide-react";
import type { RunComparison } from "../data/comparison";

type Props = {
  comparison: RunComparison;
};

export function ComparisonInsights({ comparison }: Props) {
  const maximum = Math.max(
    ...comparison.cohorts.map(
      (cohort) => cohort.attention.fresh_tokens
        + cohort.attention.cache_read_tokens
        + cohort.attention.cache_write_tokens
        + cohort.attention.output_tokens,
    ),
  );
  return (
    <>
      <section className="comparison-insights">
        <header className="rail-heading">
          <div>
            <p className="eyebrow">Decision-ready findings</p>
            <h2>What changed</h2>
          </div>
          <BrainCircuit size={15} aria-hidden="true" />
        </header>
        <div className="comparison-findings">
          {comparison.findings.map((finding, index) => (
            <article key={finding}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{finding}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="attention-panel">
        <header className="rail-heading compact">
          <div>
            <p className="eyebrow">Attention economics</p>
            <h2>Tokens per journey</h2>
          </div>
          <DatabaseZap size={15} aria-hidden="true" />
        </header>
        <div className="attention-bars">
          {comparison.cohorts.map((cohort) => {
            const attention = cohort.attention;
            const total = attention.fresh_tokens
              + attention.cache_read_tokens
              + attention.cache_write_tokens
              + attention.output_tokens;
            return (
              <article key={cohort.mode}>
                <header><strong>{cohort.mode}</strong><span>
                  {Math.round(total).toLocaleString()}
                </span></header>
                <div className="attention-track" aria-label={`${cohort.mode} token classes`}>
                  <span
                    className="token-fresh"
                    style={{ width: `${attention.fresh_tokens / maximum * 100}%` }}
                    title="Fresh input"
                  />
                  <span
                    className="token-cache"
                    style={{ width: `${attention.cache_read_tokens / maximum * 100}%` }}
                    title="Cache read"
                  />
                  <span
                    className="token-write"
                    style={{ width: `${attention.cache_write_tokens / maximum * 100}%` }}
                    title="Cache write"
                  />
                  <span
                    className="token-output"
                    style={{ width: `${attention.output_tokens / maximum * 100}%` }}
                    title="Output"
                  />
                </div>
              </article>
            );
          })}
        </div>
        <div className="attention-legend">
          <span className="token-fresh">fresh</span>
          <span className="token-cache">cache read</span>
          <span className="token-write">cache write</span>
          <span className="token-output">output</span>
        </div>
        <p className="method-note">
          <AlertCircle size={12} aria-hidden="true" />
          Cost and calls are cohort measurements. Byte replay is a
          path-independent counterfactual.
        </p>
      </section>
    </>
  );
}
