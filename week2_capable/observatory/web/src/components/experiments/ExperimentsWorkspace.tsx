import {
  ArrowRight,
  CheckCircle2,
  CircleDollarSign,
  FlaskConical,
  GitCompareArrows,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
  Split,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import "../../styles/experiments.css";
import type {
  ComparisonCohort,
  ComparisonMode,
  ExperimentArmDefinition,
  ExperimentDefinition,
  ExperimentFeature,
  RunComparison,
} from "../../data/comparison";
import { useComparison } from "../../data/useComparison";
import { StateBadge } from "../system/StateBadge";

type Props = {
  onOpenRun: (runId: string) => void;
  playerProfile: string;
};

type Lens = "compare" | "definition" | "run" | "samples" | "replay";

type ExperimentJobSample = {
  id: string;
  arm_id: string;
  ordinal: number;
  state: "queued" | "running" | "success" | "agent_failure" | "setup_failure" | "excluded";
  run_id: string | null;
  cost_usd: number | null;
  turns: number | null;
  calls: number | null;
  detail: string;
  effective_config: Record<string, boolean | number | string>;
};

type ExperimentJob = {
  id: string;
  player_profile: string;
  definition: ExperimentDefinition;
  state: "queued" | "running" | "stopping" | "stopped" | "completed" | "failed";
  confirmed_max_spend_usd: number;
  spent_usd: number;
  current_sample: string | null;
  samples: ExperimentJobSample[];
};

const modes: ComparisonMode[] = ["raw", "minimal", "full"];

export function ExperimentsWorkspace({ onOpenRun, playerProfile }: Props) {
  const { comparison, loading } = useComparison();
  const [lens, setLens] = useState<Lens>("compare");
  const [selectedMode, setSelectedMode] = useState<ComparisonMode>("minimal");
  const [forkOpen, setForkOpen] = useState(false);
  const [draft, setDraft] = useState<ExperimentDefinition | null>(null);
  const [jobs, setJobs] = useState<ExperimentJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const updateJob = useCallback((changed: ExperimentJob) => {
    setSelectedJobId(changed.id);
    setJobs((current) => [
      changed,
      ...current.filter((job) => job.id !== changed.id),
    ]);
  }, []);

  useEffect(() => {
    let timer = 0;
    const abort = new AbortController();
    const load = async () => {
      try {
        const response = await fetch("/api/experiments/jobs", {
          signal: abort.signal,
          cache: "no-store",
        });
        if (response.ok) {
          const payload = await response.json() as { jobs?: ExperimentJob[] };
          setJobs(payload.jobs ?? []);
        }
      } catch {
        // The workbench remains usable with imported evidence only.
      } finally {
        if (!abort.signal.aborted) timer = window.setTimeout(load, 2_000);
      }
    };
    void load();
    return () => {
      abort.abort();
      window.clearTimeout(timer);
    };
  }, []);

  if (loading) {
    return <div className="workspace-empty">Loading experiment evidence…</div>;
  }
  if (!comparison) {
    return (
      <div className="workspace-empty">
        <FlaskConical aria-hidden="true" />
        <h1>No experiment evidence is configured</h1>
        <p>
          Configure the benchmark evidence root to import completed cohorts.
          No result is invented when that source is unavailable.
        </p>
      </div>
    );
  }
  const selectedJob = jobs.find((job) => job.id === selectedJobId) ?? null;
  const activeDefinition = selectedJob?.definition ?? draft ?? comparison.definition;
  const startDraft = () => {
    setDraft(runnableDraft(comparison.definition));
    setSelectedJobId(null);
    setForkOpen(false);
    setLens("definition");
  };

  return (
    <div className="experiments-workspace">
      <aside className="experiment-rail" aria-label="Experiment definitions">
        <div className="rail-title">
          <span>
            <p className="eyebrow">Experiment library</p>
            <h2>Controlled tests</h2>
          </span>
          <button
            type="button"
            className="rail-new"
            onClick={startDraft}
            title="Create a small executable draft from the imported definition"
          >
            New
          </button>
        </div>
        <button
          className={`experiment-card${!draft && !selectedJob ? " is-selected" : ""}`}
          type="button"
          onClick={() => {
            setDraft(null);
            setSelectedJobId(null);
            setLens("compare");
          }}
        >
          <span className="experiment-card-top">
            <strong>{comparison.title}</strong>
            <StateBadge state="actual">Imported</StateBadge>
          </span>
          <span>{comparison.samples.length} samples · {comparison.definition.arms.length} arms</span>
          <small>Verified retained evidence</small>
        </button>
        <button
          className={`experiment-card${draft && !selectedJob ? " is-selected" : ""}`}
          type="button"
          onClick={() => {
            if (!draft) startDraft();
            else {
              setSelectedJobId(null);
              setLens("definition");
            }
          }}
        >
          <strong>{draft?.title ?? "One-variable fork"}</strong>
          <span>{draft ? `${draft.arms.length} arms · ${draft.repetitions_per_arm} repetition each` : "Start from this definition"}</span>
          <small>{draft ? "Executable draft · not started" : "Draft · no spend"}</small>
        </button>
        {jobs.slice(0, 3).map((job) => (
          <ExperimentJobCard
            job={job}
            key={job.id}
            selected={selectedJob?.id === job.id}
            onSelect={() => {
              setDraft(null);
              setSelectedJobId(job.id);
              setLens(job.state === "completed" ? "compare" : "run");
            }}
          />
        ))}
        {jobs.length > 3 ? (
          <details className="older-experiment-jobs">
            <summary>{jobs.length - 3} older jobs</summary>
            {jobs.slice(3).map((job) => (
              <ExperimentJobCard
                job={job}
                key={job.id}
                selected={selectedJob?.id === job.id}
                onSelect={() => {
                  setDraft(null);
                  setSelectedJobId(job.id);
                  setLens(job.state === "completed" ? "compare" : "run");
                }}
              />
            ))}
          </details>
        ) : null}
        <div className="experiment-rail-note">
          <ShieldCheck size={15} aria-hidden="true" />
          <span>
            <strong>Explicit confirmation</strong>
            <small>No paid sample can start from navigation or validation.</small>
          </span>
        </div>
      </aside>

      <section className="experiment-main">
        <ExperimentHeader
          comparison={comparison}
          definition={activeDefinition}
          job={selectedJob}
          onFork={() => setForkOpen((current) => !current)}
          onRun={() => {
            if (!draft) setDraft(runnableDraft(comparison.definition));
            setLens("run");
          }}
        />
        {forkOpen ? (
          <ForkPanel
            comparison={comparison}
            definition={activeDefinition}
            onClose={() => setForkOpen(false)}
            onFork={(fork) => {
              setDraft(fork);
            }}
          />
        ) : null}
        <Lifecycle
          comparison={comparison}
          definition={activeDefinition}
          job={selectedJob}
        />
        <nav className="experiment-lenses" aria-label="Experiment views">
          {([
            ["compare", "Compare"],
            ["definition", "Definition"],
            ["run", "Run queue"],
            ["samples", "Samples"],
            ["replay", "Counterfactual replay"],
          ] as const).map(([id, label]) => (
            <button
              aria-pressed={lens === id}
              key={id}
              onClick={() => {
                if (id === "run" && !draft) {
                  setDraft(runnableDraft(comparison.definition));
                }
                setLens(id);
              }}
              type="button"
            >
              {label}
            </button>
          ))}
        </nav>

        {lens === "compare" ? (
          selectedJob ? (
            <JobComparisonView
              job={selectedJob}
              onOpenRun={onOpenRun}
              onOpenSamples={() => setLens("samples")}
            />
          ) : (
            <ComparisonView
              comparison={comparison}
              selectedMode={selectedMode}
              onSelectMode={setSelectedMode}
              onOpenRun={onOpenRun}
              onOpenSamples={() => setLens("samples")}
            />
          )
        ) : lens === "definition" ? (
          <DefinitionView
            comparison={comparison}
            definition={activeDefinition}
            onChange={setDraft}
          />
        ) : lens === "run" ? (
          <RunView
            definition={activeDefinition}
            playerProfile={playerProfile}
            onOpenRun={onOpenRun}
            initialJob={selectedJob}
            onJobChange={updateJob}
          />
        ) : lens === "samples" ? (
          selectedJob ? (
            <JobSamplesView job={selectedJob} onOpenRun={onOpenRun} />
          ) : (
            <SamplesView comparison={comparison} onOpenRun={onOpenRun} />
          )
        ) : (
          <ReplayView comparison={comparison} />
        )}
      </section>
    </div>
  );
}

function ExperimentJobCard({
  job,
  selected,
  onSelect,
}: {
  job: ExperimentJob;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`experiment-card${selected ? " is-selected" : ""}`}
      type="button"
      onClick={onSelect}
    >
      <span className="experiment-card-top">
        <strong>{job.definition.title}</strong>
        <StateBadge state={job.state === "completed" ? "actual" : "incomplete"}>
          {job.state}
        </StateBadge>
      </span>
      <span>{job.samples.length} samples · {job.definition.arms.length} arms</span>
      <small>${job.spent_usd.toFixed(4)} retained spend · {job.player_profile}</small>
    </button>
  );
}

function RunView({
  definition,
  playerProfile,
  onOpenRun,
  initialJob,
  onJobChange,
}: {
  definition: ExperimentDefinition;
  playerProfile: string;
  onOpenRun: (runId: string) => void;
  initialJob: ExperimentJob | null;
  onJobChange: (job: ExperimentJob) => void;
}) {
  const [validation, setValidation] = useState<{
    valid: boolean;
    issues: string[];
  } | null>(null);
  const [queue, setQueue] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<ExperimentJob | null>(initialJob);

  useEffect(() => {
    if (!job || !["queued", "running", "stopping"].includes(job.state)) return;
    const poll = window.setInterval(() => {
      void fetch(`/api/experiments/jobs/${encodeURIComponent(job.id)}`)
        .then(async (response) => {
          if (!response.ok) throw new Error("Job status unavailable");
          const changed = await response.json() as ExperimentJob;
          setJob(changed);
          onJobChange(changed);
        })
        .catch(() => setResult("Job status unavailable"));
    }, 1000);
    return () => window.clearInterval(poll);
  }, [job?.id, job?.state, onJobChange]);

  useEffect(() => {
    setJob(initialJob);
  }, [initialJob?.id]);

  useEffect(() => {
    setValidation(null);
    setQueue([]);
    setConfirmed(false);
    if (!initialJob || initialJob.definition.id !== definition.id) {
      setJob(null);
    }
    setResult(null);
  }, [definition.id, definition.version]);

  const validate = () => {
    setBusy(true);
    setResult(null);
    void fetch("/api/experiments/validate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ definition }),
    })
      .then(async (response) => {
        const payload = await response.json() as {
          validation?: { valid: boolean; issues: string[] };
          queue?: string[];
          detail?: string;
        };
        if (!response.ok || !payload.validation) {
          throw new Error(payload.detail ?? "Validation unavailable");
        }
        setValidation(payload.validation);
        setQueue(payload.queue ?? []);
      })
      .catch((reason: unknown) => {
        setResult(reason instanceof Error ? reason.message : "Validation unavailable");
      })
      .finally(() => setBusy(false));
  };

  const requestRun = () => {
    if (!confirmed || !validation?.valid) return;
    setBusy(true);
    void fetch("/api/experiments/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        definition,
        player_profile: playerProfile,
        confirmed: true,
        confirmed_max_spend_usd: definition.effective_max_spend_usd,
      }),
    })
      .then(async (response) => {
        const payload = await response.json() as ExperimentJob & {
          detail?: string;
        };
        if (!response.ok || !payload.id) {
          throw new Error(payload.detail ?? "Run rejected");
        }
        setJob(payload);
        onJobChange(payload);
        setResult("Controlled run queued");
      })
      .catch((reason: unknown) => {
        setResult(reason instanceof Error ? reason.message : "Run request unavailable");
      })
      .finally(() => setBusy(false));
  };

  const controlJob = (action: "stop" | "resume") => {
    if (!job) return;
    setBusy(true);
    void fetch(`/api/experiments/jobs/${encodeURIComponent(job.id)}/control`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action }),
    })
      .then(async (response) => {
        const payload = await response.json() as ExperimentJob & {
          detail?: string;
        };
        if (!response.ok || !payload.id) {
          throw new Error(payload.detail ?? `${action} rejected`);
        }
        setJob(payload);
        onJobChange(payload);
        setResult(action === "stop" ? "Stop requested" : "Run resumed");
      })
      .catch((reason: unknown) => {
        setResult(reason instanceof Error ? reason.message : `${action} unavailable`);
      })
      .finally(() => setBusy(false));
  };

  const visibleSamples = job?.samples ?? queue.map((id) => ({
    id,
    arm_id: id.split("-")[0] ?? "unknown",
    ordinal: 0,
    state: "queued" as const,
    run_id: null,
    cost_usd: null,
    turns: null,
    calls: null,
    detail: "Waiting for execution",
    effective_config: {},
  }));
  const activeSample = job?.samples.find((sample) => sample.id === job.current_sample);

  return (
    <div className="experiment-content run-grid">
      <section className="experiment-section run-preflight">
        <p className="eyebrow">Step 1 · Validate</p>
        <h2>Prove comparability before spend</h2>
        <p>
          Validation checks registered fields, reset identity, queue identity,
          six stop criteria, and the configured local spend ceiling.
        </p>
        <button className="secondary-button" type="button" onClick={validate} disabled={busy}>
          <ShieldCheck size={14} /> Validate effective definition
        </button>
        {validation ? (
          <div className={validation.valid ? "run-valid" : "run-invalid"} role="status">
            <strong>{validation.valid ? "Validation passed" : "Validation blocked"}</strong>
            {validation.issues.map((issue) => <span key={issue}>{issue}</span>)}
          </div>
        ) : null}
      </section>
      <section className="experiment-section run-confirm">
        <p className="eyebrow">Step 2 · Confirm</p>
        <h2>Maximum spend is ${definition.effective_max_spend_usd.toFixed(2)}</h2>
        <dl>
          <div><dt>Reset</dt><dd><code>{definition.reset_identity}</code></dd></div>
          <div><dt>Player</dt><dd><code>{playerProfile || "not selected"}</code></dd></div>
          <div><dt>Samples</dt><dd>{queue.length || definition.arms.length * definition.repetitions_per_arm}</dd></div>
          <div><dt>Per sample</dt><dd>${definition.per_sample_spend_ceiling_usd.toFixed(2)}</dd></div>
        </dl>
        <details className="effective-config">
          <summary>Review exact effective configuration</summary>
          {definition.arms.map((arm) => (
            <div key={arm.id}>
              <strong>{arm.label}</strong>
              <code>{JSON.stringify(arm.values)}</code>
            </div>
          ))}
          <p>
            {definition.stop.max_iterations_per_sample} iterations ·{" "}
            {definition.stop.max_wall_seconds_per_sample} seconds · verified
            predicate required
          </p>
        </details>
        <label className="confirm-check">
          <input
            type="checkbox"
            checked={confirmed}
            disabled={!validation?.valid || !playerProfile}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          I confirm this exact definition, reset identity, and maximum spend.
        </label>
        <button
          className="primary-button"
          type="button"
          disabled={!confirmed || !playerProfile || busy}
          onClick={requestRun}
        >
          <Play size={14} /> Start controlled run
        </button>
        {result ? <p className="run-result" role="alert">{result}</p> : null}
      </section>
      <section className="experiment-section run-queue">
        <div className="section-heading-row">
          <span><p className="eyebrow">Step 3 · Queue</p><h2>Deterministic sample order</h2></span>
          <div>
            <button
              type="button"
              disabled={!job || !["queued", "running"].includes(job.state) || busy}
              onClick={() => controlJob("stop")}
            >
              <Pause size={13} /> Stop safely
            </button>
            <button
              type="button"
              disabled={!job || job.state !== "stopped" || busy}
              onClick={() => controlJob("resume")}
            >
              <Play size={13} /> Resume
            </button>
          </div>
        </div>
        {visibleSamples.length ? (
          <ol>
            {visibleSamples.slice(0, 9).map((sample) => (
              <li key={sample.id}>
                <code>{sample.id}</code>
                <span>{sample.state.replace("_", " ")}</span>
              </li>
            ))}
            {visibleSamples.length > 9 ? (
              <li><span>+ {visibleSamples.length - 9} more stable samples</span></li>
            ) : null}
          </ol>
        ) : (
          <p>Validate to generate stable arm and repetition identities.</p>
        )}
      </section>
      <section className="experiment-section run-watch">
        <p className="eyebrow">Step 4 · Watch one sample</p>
        <h2>{activeSample ? activeSample.id : job ? `Job ${job.state}` : "No sample is running"}</h2>
        {job ? (
          <>
            <dl>
              <div><dt>Job</dt><dd><code>{job.id}</code></dd></div>
              <div><dt>Spend</dt><dd>${job.spent_usd.toFixed(4)} / ${job.confirmed_max_spend_usd.toFixed(2)}</dd></div>
              <div><dt>State</dt><dd>{job.state}</dd></div>
            </dl>
            {activeSample ? <p>{activeSample.detail}</p> : null}
            {job.samples.filter((sample) => sample.run_id).map((sample) => (
              <button
                className="text-button"
                key={sample.id}
                type="button"
                onClick={() => sample.run_id && onOpenRun(sample.run_id)}
              >
                Open {sample.id} in Sessions <ArrowRight size={13} />
              </button>
            ))}
          </>
        ) : (
          <p>
            A running sample reuses the Live cockpit while queue controls remain
            here. Setup failure and agent outcome never share a state.
          </p>
        )}
      </section>
    </div>
  );
}

function ExperimentHeader({
  comparison,
  definition,
  job,
  onFork,
  onRun,
}: {
  comparison: RunComparison;
  definition: ExperimentDefinition;
  job: ExperimentJob | null;
  onFork: () => void;
  onRun: () => void;
}) {
  return (
    <header className="experiment-header">
      <div>
        <div className="experiment-title-line">
          <h1>{definition.title}</h1>
          <StateBadge state={job?.state === "completed" || (job === null && definition.source === "imported_evidence" && comparison.validation.valid) ? "actual" : "incomplete"}>
            {job ? job.state : definition.source === "executable_definition" ? "Draft" : comparison.validation.valid ? "Comparable" : "Needs repair"}
          </StateBadge>
        </div>
        <p><strong>Use case:</strong> {definition.objective}</p>
        <p className="experiment-predicate">
          Success is independently verified when {definition.success_predicate.toLowerCase()}
        </p>
      </div>
      <div className="experiment-actions">
        <button className="secondary-button" type="button" onClick={onFork}>
          <Split size={14} aria-hidden="true" /> Fork one variable
        </button>
        <button className="primary-button" onClick={onRun} type="button">
          <Play size={14} aria-hidden="true" /> Run new samples
        </button>
        <small>Validation and explicit spend confirmation are required</small>
      </div>
    </header>
  );
}

function ForkPanel({
  comparison,
  definition,
  onClose,
  onFork,
}: {
  comparison: RunComparison;
  definition: ExperimentDefinition;
  onClose: () => void;
  onFork: (definition: ExperimentDefinition) => void;
}) {
  const [arm, setArm] = useState(definition.arms[1]?.id ?? "raw");
  const [featureId, setFeatureId] = useState("render.mode");
  const [value, setValue] = useState("full");
  const [fork, setFork] = useState<ExperimentDefinition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const feature = comparison.registry.find((item) => item.id === featureId)
    ?? comparison.registry[0];

  return (
    <section className="fork-panel" aria-labelledby="fork-title">
      <div>
        <p className="eyebrow">Controlled fork</p>
        <h2 id="fork-title">Change exactly one registered value</h2>
        <p>Everything else, including reset identity and stop criteria, keeps its provenance.</p>
      </div>
      <label>
        Arm
        <select value={arm} onChange={(event) => setArm(event.target.value)}>
          {definition.arms.map((item) => (
            <option value={item.id} key={item.id}>{item.label}</option>
          ))}
        </select>
      </label>
      <label>
        Feature
        <select
          value={featureId}
          onChange={(event) => {
            const next = comparison.registry.find(
              (item) => item.id === event.target.value,
            );
            setFeatureId(event.target.value);
            setValue(String(next?.default ?? ""));
          }}
        >
          {comparison.registry.map((item) => (
            <option value={item.id} key={item.id}>{item.label}</option>
          ))}
        </select>
      </label>
      <label>
        New value
        {feature?.kind === "enum" ? (
          <select value={value} onChange={(event) => setValue(event.target.value)}>
            {feature.options.map((option) => <option key={option}>{option}</option>)}
          </select>
        ) : (
          <input value={value} onChange={(event) => setValue(event.target.value)} />
        )}
      </label>
      <div className="fork-actions">
        <button
          className="primary-button"
          type="button"
          onClick={() => {
            setError(null);
            void fetch("/api/experiments/fork", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                definition,
                arm_id: arm,
                feature_id: featureId,
                value: typedValue(feature, value),
              }),
            })
              .then(async (response) => {
                const payload = await response.json() as ExperimentDefinition & {
                  detail?: string;
                };
                if (!response.ok) throw new Error(payload.detail ?? "Fork rejected");
                setFork(payload);
                onFork(payload);
              })
              .catch((reason: unknown) => {
                setError(reason instanceof Error ? reason.message : "Fork rejected");
              });
          }}
        >
          Create immutable fork
        </button>
        <button className="text-button" type="button" onClick={onClose}>Close</button>
      </div>
      {fork ? (
        <p className="fork-result" role="status">
          Fork ready: <code>{fork.id}</code> · parent <code>{fork.parent_definition_id}</code>
          {" "}· changed <code>{fork.changed_feature}</code>
        </p>
      ) : null}
      {error ? <p className="fork-error" role="alert">{error}</p> : null}
    </section>
  );
}

function typedValue(
  feature: ExperimentFeature | undefined,
  value: string,
): boolean | number | string {
  if (feature?.kind === "boolean") return value === "true";
  if (feature?.kind === "integer") return Number.parseInt(value, 10);
  if (feature?.kind === "number") return Number.parseFloat(value);
  return value;
}

function Lifecycle({
  comparison,
  definition,
  job,
}: {
  comparison: RunComparison;
  definition: ExperimentDefinition;
  job: ExperimentJob | null;
}) {
  const isDraft = definition.source === "executable_definition";
  const steps = [
    ["Define", "Versioned objective and arms"],
    ["Validate", job ? "Validated definition retained" : isDraft ? "Run preflight required" : comparison.validation.comparable ? "Comparable evidence" : "Blocked"],
    ["Confirm", job ? `$${job.confirmed_max_spend_usd.toFixed(2)} confirmed` : "Required before paid work"],
    ["Run", job ? job.state : isDraft ? "Available after local policy permits" : "Imported evidence is read-only"],
    ["Compare", job ? `${job.samples.filter((sample) => sample.run_id).length} retained samples` : `${comparison.samples.length} retained samples`],
  ];
  return (
    <ol className="experiment-lifecycle" aria-label="Experiment lifecycle">
      {steps.map(([label, detail], index) => {
        const complete = job
          ? index < 3
            || (index === 3 && ["running", "stopping", "stopped", "completed"].includes(job.state))
            || (index === 4 && job.samples.some((sample) => sample.run_id))
          : index < 2 || index === 4;
        return (
          <li className={complete ? "is-complete" : "is-unavailable"} key={label}>
            <span>{complete ? <CheckCircle2 /> : index === 3 ? <Pause /> : index + 1}</span>
            <div><strong>{label}</strong><small>{detail}</small></div>
          </li>
        );
      })}
    </ol>
  );
}

function ComparisonView({
  comparison,
  selectedMode,
  onSelectMode,
  onOpenRun,
  onOpenSamples,
}: {
  comparison: RunComparison;
  selectedMode: ComparisonMode;
  onSelectMode: (mode: ComparisonMode) => void;
  onOpenRun: (runId: string) => void;
  onOpenSamples: () => void;
}) {
  const selected = comparison.cohorts.find((item) => item.mode === selectedMode)
    ?? comparison.cohorts[0];
  const cheapest = useMemo(
    () => [...comparison.cohorts].sort((a, b) => a.cost_mean - b.cost_mean)[0],
    [comparison.cohorts],
  );
  return (
    <div className="experiment-content">
      <section className="experiment-section">
        <div className="section-heading-row">
          <span>
            <p className="eyebrow">Arms</p>
            <h2>One controlled difference</h2>
          </span>
          <p>Only the model-facing gateway result changes. Model, tools, reset, and objective stay fixed.</p>
        </div>
        <div className="experiment-arms">
          {comparison.definition.arms.map((arm) => {
            const cohort = comparison.cohorts.find((item) => item.mode === arm.id);
            return cohort ? (
              <ArmCard
                arm={arm}
                cohort={cohort}
                features={comparison.registry}
                selected={selectedMode === arm.id}
                onSelect={() => onSelectMode(arm.id as ComparisonMode)}
                key={arm.id}
              />
            ) : null;
          })}
        </div>
      </section>

      <section className="experiment-section">
        <div className="section-heading-row">
          <span><p className="eyebrow">Outcome</p><h2>Performance and cost</h2></span>
          <p>Every aggregate opens the samples and exclusions that produced it.</p>
        </div>
        <div className="comparison-metrics">
          <MetricComparison
            cohorts={comparison.cohorts}
            label="Verified success"
            value={(item) => `${item.successes}/${item.samples}`}
            magnitude={(item) => item.successes / item.samples}
            onOpen={onOpenSamples}
          />
          <MetricComparison
            cohorts={comparison.cohorts}
            label="Mean cost / run"
            value={(item) => `$${item.cost_mean.toFixed(4)} ± ${item.cost_stdev.toFixed(4)}`}
            magnitude={(item) => item.cost_mean}
            lower
            onOpen={onOpenSamples}
          />
          <MetricComparison
            cohorts={comparison.cohorts}
            label="Mean tool calls"
            value={(item) => `${item.calls_mean.toFixed(1)} ± ${item.calls_stdev.toFixed(1)}`}
            magnitude={(item) => item.calls_mean}
            lower
            onOpen={onOpenSamples}
          />
          <MetricComparison
            cohorts={comparison.cohorts}
            label="Corrective calls"
            value={(item) => String(item.corrective_calls)}
            magnitude={(item) => item.corrective_calls}
            lower
            onOpen={onOpenSamples}
          />
        </div>
        <div className="experiment-verdict">
          <CircleDollarSign aria-hidden="true" />
          <span>
            <strong>{cheapest.mode} is cheapest, not automatically “best.”</strong>
            <p>
              All arms succeeded. Cost differences overlap cohort variability,
              so the workbench keeps distributions and evidence visible instead
              of manufacturing a winner.
            </p>
          </span>
        </div>
      </section>

      <section className="experiment-split">
        <div className="experiment-section">
          <p className="eyebrow">First semantic divergence</p>
          <h2>{comparison.divergence.summary}</h2>
          <div className="divergence-lanes">
            {modes.map((mode) => (
              <div key={mode}>
                <b>{mode}</b>
                <span>{comparison.divergence.actions[mode]}</span>
                <button
                  type="button"
                  onClick={() => {
                    const run = comparison.samples.find((sample) => sample.mode === mode);
                    if (run) onOpenRun(run.run_id);
                  }}
                >
                  Open representative run <ArrowRight size={12} />
                </button>
              </div>
            ))}
          </div>
        </div>
        <div className="experiment-section attention-economics">
          <p className="eyebrow">Attention economics · {selected.mode}</p>
          <h2>What consumed the context</h2>
          <dl>
            <div><dt>Fresh input</dt><dd>{Math.round(selected.attention.fresh_tokens).toLocaleString()}</dd></div>
            <div><dt>Cache read</dt><dd>{Math.round(selected.attention.cache_read_tokens).toLocaleString()}</dd></div>
            <div><dt>Cache write</dt><dd>{Math.round(selected.attention.cache_write_tokens).toLocaleString()}</dd></div>
            <div><dt>Output</dt><dd>{Math.round(selected.attention.output_tokens).toLocaleString()}</dd></div>
            <div><dt>Result payload</dt><dd>{Math.round(selected.attention.result_chars).toLocaleString()} chars</dd></div>
            <div><dt>Movement share</dt><dd>{Math.round(selected.attention.movement_share * 100)}%</dd></div>
          </dl>
        </div>
      </section>
    </div>
  );
}

function ArmCard({
  arm,
  cohort,
  features,
  selected,
  onSelect,
}: {
  arm: ExperimentArmDefinition;
  cohort: ComparisonCohort;
  features: ExperimentFeature[];
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`experiment-arm${selected ? " is-selected" : ""}`}
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="arm-heading">
        <b>{arm.label}</b><small>{cohort.samples} runs</small>
      </span>
      {features.slice(0, 4).map((feature) => (
        <span className="arm-value" key={feature.id}>
          <span><small>{feature.group}</small>{feature.label}</span>
          <strong>{String(arm.values[feature.id] ?? feature.default)}</strong>
        </span>
      ))}
    </button>
  );
}

function MetricComparison({
  cohorts,
  label,
  value,
  magnitude,
  lower = false,
  onOpen,
}: {
  cohorts: ComparisonCohort[];
  label: string;
  value: (item: ComparisonCohort) => string;
  magnitude: (item: ComparisonCohort) => number;
  lower?: boolean;
  onOpen: () => void;
}) {
  const max = Math.max(...cohorts.map(magnitude), 0.0001);
  const best = [...cohorts].sort((a, b) => (
    lower ? magnitude(a) - magnitude(b) : magnitude(b) - magnitude(a)
  ))[0]?.mode;
  return (
    <button className="comparison-metric" type="button" onClick={onOpen}>
      <h3>{label}</h3>
      {cohorts.map((cohort) => (
        <div className="metric-row" key={cohort.mode}>
          <b>{cohort.mode}</b>
          <span><i style={{ width: `${Math.max(3, magnitude(cohort) / max * 100)}%` }} /></span>
          <code>{value(cohort)}</code>
          {cohort.mode === best ? <small>best</small> : null}
        </div>
      ))}
      <span className="metric-open">Open contributing samples <ArrowRight size={11} /></span>
    </button>
  );
}

function DefinitionView({
  comparison,
  definition,
  onChange,
}: {
  comparison: RunComparison;
  definition: ExperimentDefinition;
  onChange: (definition: ExperimentDefinition) => void;
}) {
  const [selectedArm, setSelectedArm] = useState(definition.arms[0]?.id ?? "");
  const arm = definition.arms.find((item) => item.id === selectedArm)
    ?? definition.arms[0];
  const updateNumber = (
    field: "repetitions_per_arm" | "per_sample_spend_ceiling_usd",
    raw: string,
  ) => {
    const value = field === "repetitions_per_arm"
      ? Number.parseInt(raw, 10)
      : Number.parseFloat(raw);
    if (!Number.isFinite(value) || value <= 0) return;
    onChange(repriceDefinition({ ...definition, [field]: value }));
  };
  return (
    <div className="experiment-content definition-grid">
      <section className="experiment-section definition-summary">
        <p className="eyebrow">{definition.source === "imported_evidence" ? "Imported immutable definition" : "Executable draft"} · v{definition.version}</p>
        <h2>Scenario and budget</h2>
        <div className="definition-fields">
          <label>
            Title
            <input
              value={definition.title}
              onChange={(event) => onChange({ ...definition, title: event.target.value })}
            />
          </label>
          <label>
            Plain-language objective
            <textarea
              value={definition.objective}
              onChange={(event) => onChange({ ...definition, objective: event.target.value })}
            />
          </label>
          <label>
            Independently verified predicate
            <textarea
              value={definition.success_predicate}
              onChange={(event) => onChange({ ...definition, success_predicate: event.target.value })}
            />
          </label>
          <label>
            Starting state
            <input
              value={definition.starting_state}
              onChange={(event) => onChange({ ...definition, starting_state: event.target.value })}
            />
          </label>
          <label>
            Verified reset identity
            <input
              value={definition.reset_identity}
              onChange={(event) => onChange({ ...definition, reset_identity: event.target.value })}
            />
          </label>
          <label>
            Repetitions per arm
            <input
              min="1"
              type="number"
              value={definition.repetitions_per_arm}
              onChange={(event) => updateNumber("repetitions_per_arm", event.target.value)}
            />
          </label>
          <label>
            Per-sample ceiling, USD
            <input
              min="0.01"
              step="0.01"
              type="number"
              value={definition.per_sample_spend_ceiling_usd}
              onChange={(event) => updateNumber("per_sample_spend_ceiling_usd", event.target.value)}
            />
          </label>
          <p className="definition-spend">
            Maximum spend <strong>${definition.effective_max_spend_usd.toFixed(2)}</strong>
          </p>
        </div>
      </section>
      <section className="experiment-section registry-panel">
        <p className="eyebrow">Typed configuration registry</p>
        <h2>Controls generated from contracts</h2>
        <p>Each field names its owning source. Unknown flags cannot silently enter a run.</p>
        <label>
          Arm to configure
          <select value={arm?.id ?? ""} onChange={(event) => setSelectedArm(event.target.value)}>
            {definition.arms.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <div className="registry-fields">
          {comparison.registry.map((feature) => {
            const value = arm?.values[feature.id] ?? feature.default;
            const update = (next: boolean | number | string) => {
              if (!arm) return;
              onChange({
                ...definition,
                source: "executable_definition",
                arms: definition.arms.map((item) => (
                  item.id === arm.id
                    ? { ...item, values: { ...item.values, [feature.id]: next } }
                    : item
                )),
              });
            };
            return (
              <label key={feature.id}>
                <span><strong>{feature.label}</strong><small>{feature.source} · {feature.id}</small></span>
                {feature.kind === "enum" ? (
                  <select value={String(value)} onChange={(event) => update(event.target.value)}>
                    {feature.options.map((option) => <option key={option}>{option}</option>)}
                  </select>
                ) : feature.kind === "boolean" ? (
                  <input
                    type="checkbox"
                    checked={Boolean(value)}
                    onChange={(event) => update(event.target.checked)}
                  />
                ) : (
                  <input
                    value={String(value)}
                    type={feature.kind === "text" ? "text" : "number"}
                    min={feature.minimum ?? undefined}
                    max={feature.maximum ?? undefined}
                    onChange={(event) => update(typedValue(feature, event.target.value))}
                  />
                )}
              </label>
            );
          })}
        </div>
      </section>
      <section className="experiment-section validation-panel">
        <p className="eyebrow">Preflight</p>
        <h2>{comparison.validation.valid ? "Comparable evidence" : "Validation blocked"}</h2>
        <ul>
          {comparison.validation.checks.map((check) => <li key={check}><CheckCircle2 />{check}</li>)}
          {comparison.validation.issues.map((issue) => <li className="is-issue" key={issue}><TriangleAlert />{issue}</li>)}
        </ul>
      </section>
      <section className="experiment-section stop-panel">
        <p className="eyebrow">Six stop criteria</p>
        <h2>Every boundary is explicit and retained</h2>
        <div className="stop-fields">
          <label>
            Verified predicate required
            <input type="checkbox" checked={definition.stop.verified_predicate_required} disabled />
          </label>
          <label>
            Success target
            <input
              min="1"
              max={definition.arms.length * definition.repetitions_per_arm}
              type="number"
              value={definition.stop.success_target}
              onChange={(event) => {
                const value = Number.parseInt(event.target.value, 10);
                if (value > 0) onChange({
                  ...definition,
                  stop: { ...definition.stop, success_target: value },
                });
              }}
            />
          </label>
          <label>
            Iterations per sample
            <input
              min="1"
              type="number"
              value={definition.stop.max_iterations_per_sample}
              onChange={(event) => {
                const value = Number.parseInt(event.target.value, 10);
                if (value > 0) onChange({
                  ...definition,
                  stop: { ...definition.stop, max_iterations_per_sample: value },
                });
              }}
            />
          </label>
          <label>
            Wall seconds per sample
            <input
              min="1"
              type="number"
              value={definition.stop.max_wall_seconds_per_sample}
              onChange={(event) => {
                const value = Number.parseInt(event.target.value, 10);
                if (value > 0) onChange({
                  ...definition,
                  stop: { ...definition.stop, max_wall_seconds_per_sample: value },
                });
              }}
            />
          </label>
          <label>
            Maximum total cost
            <output>${definition.stop.max_total_cost_usd.toFixed(2)}</output>
          </label>
          <label>
            Operator stop available
            <input type="checkbox" checked={definition.stop.operator_stop_enabled} disabled />
          </label>
        </div>
      </section>
    </div>
  );
}

function JobComparisonView({
  job,
  onOpenRun,
  onOpenSamples,
}: {
  job: ExperimentJob;
  onOpenRun: (runId: string) => void;
  onOpenSamples: () => void;
}) {
  const arms = job.definition.arms.map((arm) => {
    const samples = job.samples.filter((sample) => sample.arm_id === arm.id);
    const completed = samples.filter((sample) => (
      ["success", "agent_failure", "setup_failure", "excluded"].includes(sample.state)
    ));
    const outcomes = samples.filter((sample) => (
      sample.state === "success" || sample.state === "agent_failure"
    ));
    const priced = samples.filter((sample) => sample.cost_usd !== null);
    const totalCost = priced.reduce((total, sample) => total + (sample.cost_usd ?? 0), 0);
    return {
      arm,
      samples,
      completed,
      outcomes,
      successes: samples.filter((sample) => sample.state === "success").length,
      setupFailures: samples.filter((sample) => sample.state === "setup_failure").length,
      agentFailures: samples.filter((sample) => sample.state === "agent_failure").length,
      meanCost: priced.length ? totalCost / priced.length : null,
      meanTurns: meanOptional(samples.map((sample) => sample.turns)),
      meanCalls: meanOptional(samples.map((sample) => sample.calls)),
    };
  });
  return (
    <div className="experiment-content">
      <section className="experiment-section">
        <div className="section-heading-row">
          <span>
            <p className="eyebrow">Collected cohort · {job.state}</p>
            <h2>Results from this controlled definition</h2>
          </span>
          <p>
            Incomplete arms remain visibly incomplete. No provisional leader is
            promoted to a verdict.
          </p>
        </div>
        <div className="experiment-arms">
          {arms.map((summary) => (
            <button
              className="experiment-arm"
              key={summary.arm.id}
              type="button"
              onClick={onOpenSamples}
            >
              <span className="arm-heading">
                <b>{summary.arm.label}</b>
                <small>{summary.completed.length}/{summary.samples.length} outcomes</small>
              </span>
              <span className="arm-value">
                <span><small>objective</small>Verified success</span>
                <strong>
                  {summary.outcomes.length
                    ? `${summary.successes}/${summary.outcomes.length}`
                    : "—"}
                </strong>
              </span>
              <span className="arm-value">
                <span><small>cost</small>Mean per priced sample</span>
                <strong>{summary.meanCost === null ? "—" : `$${summary.meanCost.toFixed(4)}`}</strong>
              </span>
              <span className="arm-value">
                <span><small>effort</small>Turns / calls</span>
                <strong>{formatMean(summary.meanTurns)} / {formatMean(summary.meanCalls)}</strong>
              </span>
              <span className="arm-value">
                <span><small>failures</small>Setup / agent</span>
                <strong>{summary.setupFailures} / {summary.agentFailures}</strong>
              </span>
            </button>
          ))}
        </div>
      </section>
      <section className="experiment-split">
        <div className="experiment-section">
          <p className="eyebrow">Comparison readiness</p>
          <h2>{job.state === "completed" ? "Cohort retained" : "Collection still in progress"}</h2>
          <p>
            Semantic divergence uses retained Sessions evidence. Open any
            completed sample to inspect its room, tool, objective, verified
            state, and cost sequence.
          </p>
          {job.samples.filter((sample) => sample.run_id).slice(0, 3).map((sample) => (
            <button
              className="text-button"
              key={sample.id}
              type="button"
              onClick={() => sample.run_id && onOpenRun(sample.run_id)}
            >
              Open {sample.id} in Sessions <ArrowRight size={13} />
            </button>
          ))}
        </div>
        <div className="experiment-section attention-economics">
          <p className="eyebrow">Budget ledger</p>
          <h2>Spend remains bounded</h2>
          <dl>
            <div><dt>Confirmed maximum</dt><dd>${job.confirmed_max_spend_usd.toFixed(2)}</dd></div>
            <div><dt>Retained spend</dt><dd>${job.spent_usd.toFixed(4)}</dd></div>
            <div><dt>Remaining headroom</dt><dd>${Math.max(0, job.confirmed_max_spend_usd - job.spent_usd).toFixed(4)}</dd></div>
            <div><dt>Stable samples</dt><dd>{job.samples.length}</dd></div>
          </dl>
        </div>
      </section>
    </div>
  );
}

function JobSamplesView({
  job,
  onOpenRun,
}: {
  job: ExperimentJob;
  onOpenRun: (runId: string) => void;
}) {
  return (
    <section className="experiment-section samples-panel">
      <div className="section-heading-row">
        <span><p className="eyebrow">Job samples</p><h2>Every planned repetition remains visible</h2></span>
        <p>Setup failure and agent outcome are separate states.</p>
      </div>
      <div className="sample-table-wrap">
        <table>
          <thead><tr><th>Arm</th><th>Sample</th><th>State</th><th>Turns</th><th>Calls</th><th>Cost</th><th /></tr></thead>
          <tbody>
            {job.samples.map((sample) => (
              <tr key={sample.id}>
                <td><b>{sample.arm_id}</b></td>
                <td><code>{sample.id}</code></td>
                <td>{sample.state.replace("_", " ")}</td>
                <td>{sample.turns ?? "—"}</td>
                <td>{sample.calls ?? "—"}</td>
                <td>{sample.cost_usd === null ? "—" : `$${sample.cost_usd.toFixed(4)}`}</td>
                <td>
                  <button
                    type="button"
                    disabled={!sample.run_id}
                    onClick={() => sample.run_id && onOpenRun(sample.run_id)}
                  >
                    {sample.run_id ? "Open in Sessions" : "No retained run yet"} <ArrowRight />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function meanOptional(values: (number | null)[]): number | null {
  const present = values.filter((value): value is number => value !== null);
  return present.length
    ? present.reduce((total, value) => total + value, 0) / present.length
    : null;
}

function formatMean(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

function runnableDraft(definition: ExperimentDefinition): ExperimentDefinition {
  return repriceDefinition({
    ...definition,
    id: `${definition.id}-pilot`,
    version: 1,
    title: `${definition.title} pilot`,
    repetitions_per_arm: 1,
    source: "executable_definition",
    parent_definition_id: null,
    changed_feature: null,
    stop: {
      ...definition.stop,
      success_target: definition.arms.length,
    },
  });
}

function repriceDefinition(definition: ExperimentDefinition): ExperimentDefinition {
  const maximum = Number((
    definition.arms.length
    * definition.repetitions_per_arm
    * definition.per_sample_spend_ceiling_usd
  ).toFixed(8));
  return {
    ...definition,
    effective_max_spend_usd: maximum,
    stop: {
      ...definition.stop,
      max_total_cost_usd: maximum,
      success_target: Math.min(
        definition.stop.success_target,
        definition.arms.length * definition.repetitions_per_arm,
      ),
    },
  };
}

function SamplesView({
  comparison,
  onOpenRun,
}: {
  comparison: RunComparison;
  onOpenRun: (runId: string) => void;
}) {
  return (
    <section className="experiment-section samples-panel">
      <div className="section-heading-row">
        <span><p className="eyebrow">Cohort members</p><h2>Every aggregate has a denominator</h2></span>
        <p>Setup failures and exclusions stay visible and never count as agent outcomes.</p>
      </div>
      <div className="sample-table-wrap">
        <table>
          <thead><tr><th>Arm</th><th>Attempt</th><th>State</th><th>Turns</th><th>Calls</th><th>Cost</th><th /></tr></thead>
          <tbody>
            {comparison.samples.map((sample) => (
              <tr key={sample.run_id}>
                <td><b>{sample.mode}</b></td>
                <td><code>{sample.attempt}</code></td>
                <td>{sample.setup_failure ? "Setup failure" : sample.excluded ? "Excluded" : sample.success ? "Success" : "Agent failure"}</td>
                <td>{sample.turns}</td>
                <td>{sample.calls}</td>
                <td>${sample.cost_usd.toFixed(4)}</td>
                <td><button type="button" onClick={() => onOpenRun(sample.run_id)}>Open in Sessions <ArrowRight /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ReplayView({ comparison }: { comparison: RunComparison }) {
  return (
    <div className="experiment-content replay-grid">
      <section className="experiment-section replay-warning">
        <RotateCcw aria-hidden="true" />
        <span>
          <p className="eyebrow">Counterfactual interpretation</p>
          <h2>Same retained evidence, different projector</h2>
          <p>
            This replay changes rendering or parser interpretation only. It
            cannot claim how the agent would have behaved under that policy.
            Behavioral claims require a controlled run.
          </p>
        </span>
      </section>
      <section className="experiment-section">
        <p className="eyebrow">Rendering replay</p>
        <h2>Payload applied to identical observations</h2>
        <div className="counterfactual-cards">
          {comparison.counterfactuals.map((item) => (
            <article key={item.mode}>
              <b>{item.mode}</b>
              <strong>{item.estimated_tokens.toLocaleString()} estimated tokens</strong>
              <span>{item.observations} observations · {item.bytes.toLocaleString()} bytes</span>
              <small>{Math.round(item.delta_from_raw * 100)}% vs raw</small>
            </article>
          ))}
        </div>
      </section>
      <section className="experiment-section">
        <p className="eyebrow">Parser replay</p>
        <h2>Recorded parser versus current rules</h2>
        <div className="parser-replays">
          {comparison.parser_counterfactuals.map((item) => (
            <article key={item.mode}>
              <GitCompareArrows aria-hidden="true" />
              <span><b>{item.mode}</b><small>{item.frames} wire frames</small></span>
              <dl>
                <div><dt>Recorded typed</dt><dd>{item.recorded_typed}</dd></div>
                <div><dt>Replayed typed</dt><dd>{item.replayed_typed}</dd></div>
                <div><dt>Delta</dt><dd>{item.typed_delta >= 0 ? "+" : ""}{item.typed_delta}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
