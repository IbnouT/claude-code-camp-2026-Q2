import {
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  FlaskConical,
  GitCompareArrows,
  ListChecks,
  Play,
  RotateCcw,
  Route,
  ShieldCheck,
} from "lucide-react";
import { useMemo, useState } from "react";
import type {
  ExperimentCohort,
  ExperimentComparison,
  ExperimentFeature,
  ExperimentJob,
  ExperimentSample,
} from "../contracts";

type Lens = "compare" | "paths" | "samples" | "definition" | "replay";

export function ExperimentWorkspace({
  comparison,
  jobs,
  loading,
  error,
}: {
  comparison: ExperimentComparison | null;
  jobs: ExperimentJob[];
  loading: boolean;
  error: string;
}) {
  const initial = new URLSearchParams(window.location.search).get("lens");
  const [lens, setLens] = useState<Lens>(
    isLens(initial) ? initial : "compare",
  );
  const [selectedMode, setSelectedMode] = useState<string | null>(null);

  if (loading && comparison === null) {
    return <div className="experiment-empty">Loading retained comparison evidence…</div>;
  }
  if (error) return <div className="experiment-empty" role="alert">{error}</div>;
  if (comparison === null) {
    return <div className="experiment-empty">No retained comparison is configured.</div>;
  }

  const totalCost = comparison.samples
    .filter((sample) => !sample.excluded)
    .reduce((sum, sample) => sum + sample.cost_usd, 0);
  const successes = comparison.samples.filter(
    (sample) => sample.success && !sample.excluded,
  ).length;

  const changeLens = (next: Lens): void => {
    setLens(next);
    const url = new URL(window.location.href);
    url.searchParams.set("lens", next);
    window.history.replaceState(null, "", url);
  };

  return (
    <section className="experiment-workspace">
      <div className="experiment-strip">
        <div>
          <span>{comparison.validation.comparable ? "Comparable" : "Needs repair"} · definition v{comparison.definition.version}</span>
          <h1>{comparison.title}</h1>
          <p>{comparison.definition.objective}</p>
        </div>
        <ExperimentStat label="Arms" value={comparison.definition.arms.length.toString()} />
        <ExperimentStat label="Samples" value={comparison.samples.length.toString()} />
        <ExperimentStat label="Success" value={`${successes} / ${comparison.samples.length}`} />
        <ExperimentStat label="Observed cost" value={usd(totalCost, 6)} />
      </div>
      <div className="experiment-body">
        <aside className="experiment-rail">
          <div className="experiment-pane-title">Comparison</div>
          <button className="is-selected" type="button">
            <FlaskConical size={14} />
            <span><b>{comparison.definition.title}</b><small>{comparison.journey} · {comparison.samples.length} retained samples</small></span>
          </button>
          <div className="experiment-pane-title">Execution jobs</div>
          {jobs.length === 0 ? (
            <div className="experiment-rail-empty">
              <ShieldCheck size={14} />
              <span><b>No active job</b><small>Local paid execution is disabled by default.</small></span>
            </div>
          ) : jobs.map((job) => (
            <div className="experiment-job" key={job.id}>
              <span>{job.state}</span><b>{job.definition.title}</b>
              <small>{job.samples.length} samples · {usd(job.spent_usd, 4)} spent</small>
            </div>
          ))}
        </aside>
        <div className="experiment-main">
          <nav className="experiment-tabs" aria-label="Experiment lenses">
            {([
              ["compare", GitCompareArrows, "Compare"],
              ["paths", Route, "Paths"],
              ["samples", ListChecks, "Samples"],
              ["definition", FlaskConical, "Definition"],
              ["replay", RotateCcw, "Replay"],
            ] as const).map(([id, Icon, label]) => (
              <button
                aria-current={lens === id ? "page" : undefined}
                key={id}
                type="button"
                onClick={() => changeLens(id)}
              >
                <Icon size={14} />{label}
              </button>
            ))}
          </nav>
          <main className="experiment-content">
            {lens === "compare" ? (
              <CompareLens
                comparison={comparison}
                selectedMode={selectedMode}
                onSelectMode={setSelectedMode}
                onOpenSamples={() => changeLens("samples")}
              />
            ) : null}
            {lens === "paths" ? <PathsLens comparison={comparison} /> : null}
            {lens === "samples" ? (
              <SamplesLens comparison={comparison} selectedMode={selectedMode} />
            ) : null}
            {lens === "definition" ? <DefinitionLens comparison={comparison} /> : null}
            {lens === "replay" ? <ReplayLens comparison={comparison} /> : null}
          </main>
        </div>
      </div>
    </section>
  );
}

function CompareLens({
  comparison,
  selectedMode,
  onSelectMode,
  onOpenSamples,
}: {
  comparison: ExperimentComparison;
  selectedMode: string | null;
  onSelectMode: (mode: string) => void;
  onOpenSamples: () => void;
}) {
  const changed = useMemo(
    () => changedFeatures(comparison),
    [comparison],
  );
  return (
    <>
      <header className="experiment-question">
        <div>
          <span>Controlled question</span>
          <h2>Does {changed.map((feature) => feature.label.toLowerCase()).join(", ")} change journey behavior and cost?</h2>
          <p>
            Success: {comparison.definition.success_predicate}
            <i>·</i>
            Reset: {comparison.definition.reset_identity} before every sample
          </p>
        </div>
        <strong className={comparison.validation.comparable ? "is-comparable" : "is-blocked"}>
          {comparison.validation.comparable ? <CheckCircle2 size={14} /> : null}
          {comparison.validation.comparable ? "Comparable evidence" : "Comparison blocked"}
        </strong>
      </header>
      <div className="experiment-arms">
        {comparison.definition.arms.map((arm) => {
          const cohort = comparison.cohorts.find((item) => item.mode === arm.id);
          return (
            <button
              className={selectedMode === arm.id ? "is-selected" : undefined}
              key={arm.id}
              type="button"
              onClick={() => onSelectMode(arm.id)}
            >
              <span><i>{arm.id}</i><small>{cohort?.samples ?? 0} runs</small></span>
              <h3>{arm.label}</h3>
              <dl>
                {changed.map((feature) => (
                  <div key={feature.id}>
                    <dt>{feature.label}</dt>
                    <dd>{formatValue(arm.values[feature.id])}</dd>
                  </div>
                ))}
              </dl>
            </button>
          );
        })}
      </div>
      <section className="experiment-panel">
        <header><h2>Cohort evidence</h2><span>Means retain their observed variation</span></header>
        <div className="experiment-metrics">
          <CohortMetric
            cohorts={comparison.cohorts}
            label="Verified success"
            value={(cohort) => `${cohort.successes} / ${cohort.samples}`}
            magnitude={(cohort) => cohort.samples ? cohort.successes / cohort.samples : 0}
            onSelect={onSelectMode}
          />
          <CohortMetric
            cohorts={comparison.cohorts}
            label="Mean cost"
            value={(cohort) => usd(cohort.cost_mean, 6)}
            magnitude={(cohort) => cohort.cost_mean}
            onSelect={onSelectMode}
          />
          <CohortMetric
            cohorts={comparison.cohorts}
            label="Cost deviation"
            value={(cohort) => usd(cohort.cost_stdev, 6)}
            magnitude={(cohort) => cohort.cost_stdev}
            onSelect={onSelectMode}
          />
          <CohortMetric
            cohorts={comparison.cohorts}
            label="Mean calls"
            value={(cohort) => cohort.calls_mean.toFixed(1)}
            magnitude={(cohort) => cohort.calls_mean}
            onSelect={onSelectMode}
          />
        </div>
        <div className="experiment-finding">
          <strong>Observed</strong>
          <div>
            <p>{comparison.findings[1] ?? comparison.findings[0]}</p>
            <small>{comparison.findings[2]}</small>
          </div>
          <button type="button" onClick={onOpenSamples}>
            Open {comparison.samples.length} samples <ChevronRight size={14} />
          </button>
        </div>
      </section>
      <AttentionPanel cohorts={comparison.cohorts} />
    </>
  );
}

function CohortMetric({
  cohorts,
  label,
  value,
  magnitude,
  onSelect,
}: {
  cohorts: ExperimentCohort[];
  label: string;
  value: (cohort: ExperimentCohort) => string;
  magnitude: (cohort: ExperimentCohort) => number;
  onSelect: (mode: string) => void;
}) {
  const ceiling = Math.max(...cohorts.map(magnitude), 0.000001);
  return (
    <div className="experiment-metric">
      <span>{label}</span>
      {cohorts.map((cohort) => (
        <button key={cohort.mode} type="button" onClick={() => onSelect(cohort.mode)}>
          <i>{cohort.mode}</i>
          <b><em style={{ width: `${magnitude(cohort) / ceiling * 100}%` }} /></b>
          <strong>{value(cohort)}</strong>
        </button>
      ))}
    </div>
  );
}

function AttentionPanel({ cohorts }: { cohorts: ExperimentCohort[] }) {
  const ceiling = Math.max(
    ...cohorts.map((cohort) => (
      cohort.attention.fresh_tokens
      + cohort.attention.cache_read_tokens
      + cohort.attention.cache_write_tokens
      + cohort.attention.output_tokens
    )),
  );
  return (
    <section className="experiment-panel attention-panel">
      <header><h2>Attention economics</h2><span>Mean tokens per sample</span></header>
      {cohorts.map((cohort) => {
        const attention = cohort.attention;
        const total = attention.fresh_tokens + attention.cache_read_tokens
          + attention.cache_write_tokens + attention.output_tokens;
        return (
          <div className="attention-row" key={cohort.mode}>
            <b>{cohort.mode}</b>
            <div style={{ width: `${total / ceiling * 100}%` }}>
              <i style={{ flex: attention.fresh_tokens }} title="Fresh input" />
              <i style={{ flex: attention.cache_read_tokens }} title="Cache read" />
              <i style={{ flex: attention.cache_write_tokens }} title="Cache write" />
              <i style={{ flex: attention.output_tokens }} title="Output" />
            </div>
            <span>{integer(total)} tokens</span>
            <small>
              {integer(attention.result_chars)} result chars · {integer(attention.schema_tokens)} schema tokens
              {" · "}{(attention.movement_share * 100).toFixed(1)}% movement
              {" · "}{cohort.invalid_calls} invalid · {cohort.corrective_calls} corrective
            </small>
          </div>
        );
      })}
      <footer><span>Fresh input</span><span>Cache read</span><span>Cache write</span><span>Output</span></footer>
    </section>
  );
}

function PathsLens({ comparison }: { comparison: ExperimentComparison }) {
  return (
    <section className="experiment-panel paths-panel">
      <header>
        <div><span>Representative behavior</span><h2>{comparison.divergence.summary}</h2></div>
        <small>Examples explain behavior. Cohorts establish the result.</small>
      </header>
      <div className="path-lanes">
        {comparison.lanes.map((lane) => (
          <div className="path-lane" key={lane.mode}>
            <div><b>{lane.mode}</b><small>{formatAttempt(lane.attempt)} · {usd(lane.cost_usd, 5)} · {lane.calls} calls</small></div>
            <ol>
              {lane.milestones.map((milestone) => (
                <li className={milestone.index === comparison.divergence.index ? "is-divergence" : undefined} key={`${lane.mode}-${milestone.index}`}>
                  <span>{milestone.index}</span><b>{milestone.label}</b>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </section>
  );
}

function SamplesLens({
  comparison,
  selectedMode,
}: {
  comparison: ExperimentComparison;
  selectedMode: string | null;
}) {
  const samples = selectedMode
    ? comparison.samples.filter((sample) => sample.mode === selectedMode)
    : comparison.samples;
  return (
    <section className="experiment-panel samples-panel">
      <header><h2>Retained samples</h2><span>{samples.length} shown · setup failures and exclusions stay explicit</span></header>
      <div className="sample-table" role="table">
        <div role="row"><b>Arm</b><b>Attempt</b><b>Outcome</b><b>Cost</b><b>Turns</b><b>Calls</b><b>Session</b></div>
        {samples.map((sample) => (
          <div key={sample.run_id} role="row">
            <span>{sample.mode}</span><time>{formatAttempt(sample.attempt)}</time>
            <span>{sample.excluded ? "excluded" : sample.setup_failure ? "setup failure" : sample.success ? "verified success" : "agent failure"}</span>
            <b>{usd(sample.cost_usd, 6)}</b><span>{sample.turns}</span><span>{sample.calls}</span>
            <a href={`/sessions?run=${encodeURIComponent(sample.run_id)}`}>Open run</a>
          </div>
        ))}
      </div>
    </section>
  );
}

function DefinitionLens({ comparison }: { comparison: ExperimentComparison }) {
  return (
    <div className="definition-grid">
      <section className="experiment-panel">
        <header><h2>Immutable definition</h2><span>{comparison.definition.id}</span></header>
        <dl className="definition-facts">
          <div><dt>Objective</dt><dd>{comparison.definition.objective}</dd></div>
          <div><dt>Verified predicate</dt><dd>{comparison.definition.success_predicate}</dd></div>
          <div><dt>Starting state</dt><dd>{comparison.definition.starting_state}</dd></div>
          <div><dt>Reset</dt><dd>{comparison.definition.reset_strategy}</dd></div>
          <div><dt>Repetitions</dt><dd>{comparison.definition.repetitions_per_arm} per arm</dd></div>
          <div><dt>Maximum authorized spend</dt><dd>{usd(comparison.definition.effective_max_spend_usd, 2)}</dd></div>
        </dl>
      </section>
      <section className="experiment-panel">
        <header><h2>Registered configuration</h2><span>{comparison.registry.length} typed features</span></header>
        <div className="registry-list">
          {comparison.registry.map((feature) => (
            <div key={feature.id}>
              <span><b>{feature.label}</b><code>{feature.id}</code></span>
              <p>{feature.description}</p>
              <small>
                {feature.source} · {feature.kind}
                {feature.options.length ? ` · ${feature.options.join(", ")}` : ""}
                {" · "}
                {feature.execution_supported ? "runner-supported" : "observe only"}
              </small>
            </div>
          ))}
        </div>
      </section>
      <section className="experiment-panel validation-panel">
        <header><h2>Preflight</h2><span>{comparison.validation.execution_available ? "Execution available" : "Imported evidence only"}</span></header>
        <ul>
          {comparison.validation.checks.map((check) => <li key={check}><CheckCircle2 size={13} />{check}</li>)}
          {comparison.validation.issues.map((issue) => <li className="is-issue" key={issue}>{issue}</li>)}
        </ul>
        <div className="execution-boundary"><Play size={15} /><p><b>Paid execution is off.</b> Enabling local policy still requires validated spend confirmation.</p></div>
      </section>
    </div>
  );
}

function ReplayLens({ comparison }: { comparison: ExperimentComparison }) {
  return (
    <div className="replay-grid">
      <section className="experiment-panel">
        <header><h2>Rendering counterfactual</h2><span>No model call</span></header>
        {comparison.counterfactuals.map((item) => (
          <div className="counterfactual" key={item.mode}>
            <b>{item.mode}</b><span>{integer(item.observations)} observations</span>
            <span>{integer(item.bytes)} bytes</span><span>≈ {integer(item.estimated_tokens)} tokens</span>
            <strong>{item.delta_from_raw === 0 ? "baseline" : `+${(item.delta_from_raw * 100).toFixed(1)}% vs raw`}</strong>
          </div>
        ))}
      </section>
      <section className="experiment-panel">
        <header><h2>Parser replay</h2><span>Recorded wire, current rules</span></header>
        {comparison.parser_counterfactuals.map((item) => (
          <div className="counterfactual" key={item.mode}>
            <b>{item.mode}</b><span>{integer(item.frames)} frames</span>
            <span>{item.recorded_version} → {item.replayed_version}</span>
            <span>{item.replayed_typed} / {item.replayed_lines} typed</span>
            <strong>{item.typed_delta >= 0 ? "+" : ""}{item.typed_delta} typed lines</strong>
          </div>
        ))}
      </section>
    </div>
  );
}

function ExperimentStat({ label, value }: { label: string; value: string }) {
  return <div className="experiment-stat"><span>{label}</span><b>{value}</b></div>;
}

function changedFeatures(comparison: ExperimentComparison): ExperimentFeature[] {
  return comparison.registry.filter((feature) => (
    new Set(
      comparison.definition.arms.map((arm) => JSON.stringify(arm.values[feature.id])),
    ).size > 1
  ));
}

function isLens(value: string | null): value is Lens {
  return value !== null
    && ["compare", "paths", "samples", "definition", "replay"].includes(value);
}

function usd(value: number, digits: number): string {
  return `$${value.toFixed(digits)}`;
}

function integer(value: number): string {
  return Math.round(value).toLocaleString();
}

function formatValue(value: boolean | number | string | undefined): string {
  if (typeof value === "boolean") return value ? "enabled" : "disabled";
  return String(value ?? "unavailable");
}

function formatAttempt(value: string): string {
  const match = /^(\d{8})T(\d{6})Z/.exec(value);
  if (!match) return value;
  return `${match[1].slice(0, 4)}-${match[1].slice(4, 6)}-${match[1].slice(6)} ${match[2].slice(0, 2)}:${match[2].slice(2, 4)}:${match[2].slice(4)} UTC`;
}
