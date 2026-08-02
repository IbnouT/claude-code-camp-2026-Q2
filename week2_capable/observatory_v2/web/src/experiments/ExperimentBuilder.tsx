import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CircleDollarSign,
  FlaskConical,
  Play,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { useMemo, useState } from "react";
import type {
  ExperimentCatalog,
  ExperimentDefinition,
  ExperimentFeature,
  ExperimentJob,
  ExperimentScenario,
  ExperimentValidation,
} from "../contracts";

type ArmDraft = {
  id: string;
  label: string;
  values: Record<string, boolean | number | string>;
};

type ValidationResult = {
  validation: ExperimentValidation;
  queue: string[];
};

export function ExperimentBuilder({
  catalog,
  onClose,
  onJobCreated,
}: {
  catalog: ExperimentCatalog;
  onClose: () => void;
  onJobCreated: (job: ExperimentJob) => void;
}) {
  const firstScenario = catalog.scenarios[0];
  const defaults = Object.fromEntries(
    catalog.registry.map((feature) => [feature.id, feature.default]),
  );
  const [scenarioId, setScenarioId] = useState(firstScenario?.id ?? "");
  const [title, setTitle] = useState("Configuration A/B comparison");
  const [objective, setObjective] = useState(firstScenario?.objective ?? "");
  const [predicate, setPredicate] = useState(
    firstScenario?.success_predicate ?? "",
  );
  const [arms, setArms] = useState<ArmDraft[]>([
    { id: "A", label: "Control", values: { ...defaults } },
    { id: "B", label: "Variant", values: { ...defaults } },
  ]);
  const [repetitions, setRepetitions] = useState(10);
  const [sampleCeiling, setSampleCeiling] = useState(() => Math.min(
    0.6,
    catalog.execution.max_spend_usd / 20,
  ));
  const [maxIterations, setMaxIterations] = useState(60);
  const [maxWallSeconds, setMaxWallSeconds] = useState(900);
  const [successTarget, setSuccessTarget] = useState(20);
  const [playerProfile, setPlayerProfile] = useState("poucet");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [validationError, setValidationError] = useState("");
  const [validating, setValidating] = useState(false);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [confirmedSpend, setConfirmedSpend] = useState("");
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState("");

  const scenario = catalog.scenarios.find((item) => item.id === scenarioId)
    ?? firstScenario;
  const effectiveMaxSpend = roundMoney(
    arms.length * repetitions * sampleCeiling,
  );
  const changed = catalog.registry.filter(
    (feature) => arms[0]?.values[feature.id] !== arms[1]?.values[feature.id],
  );
  const definition = useMemo<ExperimentDefinition | null>(() => {
    if (scenario === undefined) return null;
    return {
      id: definitionId(title, scenario.id),
      version: 1,
      title: title.trim(),
      objective: objective.trim(),
      success_predicate: predicate.trim(),
      journey: scenario.id,
      starting_state: scenario.starting_state,
      reset_strategy: scenario.reset_strategy,
      reset_identity: scenario.reset_identity,
      arms,
      repetitions_per_arm: repetitions,
      per_sample_spend_ceiling_usd: sampleCeiling,
      stop: {
        success_target: successTarget,
        verified_predicate_required: true,
        max_iterations_per_sample: maxIterations,
        max_wall_seconds_per_sample: maxWallSeconds,
        max_total_cost_usd: effectiveMaxSpend,
        operator_stop_enabled: true,
      },
      effective_max_spend_usd: effectiveMaxSpend,
      source: "executable_definition",
      parent_definition_id: null,
      changed_feature: changed.length === 1 ? changed[0].id : null,
    };
  }, [
    arms,
    changed,
    effectiveMaxSpend,
    maxIterations,
    maxWallSeconds,
    objective,
    predicate,
    repetitions,
    sampleCeiling,
    scenario,
    successTarget,
    title,
  ]);

  const invalidate = (): void => {
    setValidation(null);
    setValidationError("");
    setConfirmationOpen(false);
    setConfirmed(false);
    setConfirmedSpend("");
  };

  const changeScenario = (nextId: string): void => {
    const next = catalog.scenarios.find((item) => item.id === nextId);
    setScenarioId(nextId);
    if (next !== undefined) {
      setObjective(next.objective);
      setPredicate(next.success_predicate);
    }
    invalidate();
  };

  const updateArm = (
    armIndex: number,
    feature: ExperimentFeature,
    value: boolean | number | string,
  ): void => {
    setArms((current) => current.map((arm, index) => (
      index === armIndex
        ? { ...arm, values: { ...arm.values, [feature.id]: value } }
        : arm
    )));
    invalidate();
  };

  const validate = async (): Promise<void> => {
    if (definition === null) return;
    setValidating(true);
    setValidationError("");
    try {
      const response = await fetch("/api/experiments/validate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ definition }),
      });
      const payload = await response.json() as (
        ValidationResult & { detail?: string }
      );
      if (!response.ok) {
        throw new Error(payload.detail ?? `Validation returned ${response.status}`);
      }
      setValidation(payload);
    } catch (reason) {
      setValidationError(
        reason instanceof Error ? reason.message : "Validation failed",
      );
    } finally {
      setValidating(false);
    }
  };

  const start = async (): Promise<void> => {
    if (
      definition === null
      || validation?.validation.valid !== true
      || !confirmed
      || Number(confirmedSpend) !== effectiveMaxSpend
    ) return;
    setStarting(true);
    setRunError("");
    try {
      const response = await fetch("/api/experiments/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          request_id: `${definition.id}-${Date.now()}`,
          definition,
          player_profile: playerProfile,
          confirmed: true,
          confirmed_max_spend_usd: effectiveMaxSpend,
        }),
      });
      const payload = await response.json() as ExperimentJob & {
        detail?: string;
      };
      if (!response.ok) {
        throw new Error(payload.detail ?? `Run returned ${response.status}`);
      }
      onJobCreated(payload);
    } catch (reason) {
      setRunError(reason instanceof Error ? reason.message : "Run failed");
    } finally {
      setStarting(false);
    }
  };

  return (
    <section className="experiment-builder">
      <header className="experiment-builder-strip">
        <button type="button" onClick={onClose}>
          <ArrowLeft size={15} /> Experiment library
        </button>
        <div>
          <span>New controlled experiment</span>
          <h1>{title || "Untitled experiment"}</h1>
          <p>
            {changed.length === 0
              ? "Choose at least one configuration difference."
              : `${changed.length} controlled difference${changed.length === 1 ? "" : "s"} · ${arms.length * repetitions} planned runs`}
          </p>
        </div>
        <BuilderMetric label="Scenario" value={scenario?.id ?? "None"} />
        <BuilderMetric label="Runs" value={String(arms.length * repetitions)} />
        <BuilderMetric label="Maximum spend" value={usd(effectiveMaxSpend)} />
      </header>

      <div className="experiment-builder-body">
        <aside className="builder-outline">
          <span>Definition</span>
          <a href="#experiment-question"><b>1</b> Question and proof</a>
          <a href="#experiment-arms"><b>2</b> Configuration arms</a>
          <a href="#experiment-sampling"><b>3</b> Sampling and stops</a>
          <a href="#experiment-preflight"><b>4</b> Validate and run</a>
          <div className="builder-invariant">
            <ShieldCheck size={15} />
            <p>
              Each sample resets to <b>{scenario?.reset_identity ?? "no reset"}</b>.
              Success comes from retained gateway evidence, not the agent claim.
            </p>
          </div>
        </aside>

        <main className="builder-scroll">
          <BuilderSection
            icon={<FlaskConical size={16} />}
            id="experiment-question"
            number="01"
            title="Question and independent proof"
          >
            <div className="builder-form-grid">
              <BuilderField label="Definition title">
                <input
                  value={title}
                  onChange={(event) => {
                    setTitle(event.target.value);
                    invalidate();
                  }}
                />
              </BuilderField>
              <BuilderField label="Resettable scenario">
                <select
                  value={scenarioId}
                  onChange={(event) => changeScenario(event.target.value)}
                >
                  {catalog.scenarios.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id} · {item.label}
                    </option>
                  ))}
                </select>
              </BuilderField>
              <BuilderField className="is-wide" label="Question posed to the agent">
                <textarea
                  rows={2}
                  value={objective}
                  onChange={(event) => {
                    setObjective(event.target.value);
                    invalidate();
                  }}
                />
              </BuilderField>
              <BuilderField className="is-wide" label="Independent success predicate">
                <textarea
                  rows={2}
                  value={predicate}
                  onChange={(event) => {
                    setPredicate(event.target.value);
                    invalidate();
                  }}
                />
              </BuilderField>
            </div>
          </BuilderSection>

          <BuilderSection
            icon={<SlidersHorizontal size={16} />}
            id="experiment-arms"
            number="02"
            title="Configuration arms"
          >
            <p className="builder-section-intro">
              Both arms resolve the complete registry. Differences are
              highlighted, and each field names the contract that supplies it.
            </p>
            <div className="builder-arm-headings">
              <span>Configuration dimension</span>
              {arms.map((arm, armIndex) => (
                <label key={arm.id}>
                  <i>{arm.id}</i>
                  <input
                    aria-label={`Arm ${arm.id} label`}
                    value={arm.label}
                    onChange={(event) => {
                      setArms((current) => current.map((item, index) => (
                        index === armIndex
                          ? { ...item, label: event.target.value }
                          : item
                      )));
                      invalidate();
                    }}
                  />
                </label>
              ))}
            </div>
            <div className="builder-feature-matrix">
              {catalog.registry.map((feature) => {
                const differs = arms[0]?.values[feature.id]
                  !== arms[1]?.values[feature.id];
                return (
                  <div
                    className={differs ? "is-different" : undefined}
                    key={feature.id}
                  >
                    <div className="builder-feature-copy">
                      <span>
                        {feature.group}
                        {!feature.execution_supported ? <i>observe only</i> : null}
                      </span>
                      <b>{feature.label}</b>
                      <p>{feature.description}</p>
                      <small>{feature.source}</small>
                    </div>
                    {arms.map((arm, index) => (
                      <FeatureControl
                        arm={arm}
                        feature={feature}
                        key={arm.id}
                        onChange={(value) => updateArm(index, feature, value)}
                      />
                    ))}
                  </div>
                );
              })}
            </div>
          </BuilderSection>

          <BuilderSection
            icon={<Settings2 size={16} />}
            id="experiment-sampling"
            number="03"
            title="Sampling and stop boundaries"
          >
            <div className="builder-number-grid">
              <NumberField
                label="Runs per arm"
                min={1}
                value={repetitions}
                onChange={(value) => {
                  setRepetitions(value);
                  setSuccessTarget(arms.length * value);
                  invalidate();
                }}
              />
              <NumberField
                label="Per-run spend ceiling"
                min={0.01}
                step={0.01}
                value={sampleCeiling}
                onChange={(value) => {
                  setSampleCeiling(value);
                  invalidate();
                }}
              />
              <NumberField
                label="Maximum iterations"
                min={1}
                value={maxIterations}
                onChange={(value) => {
                  setMaxIterations(value);
                  updatePolicyLimit(value, arms, setArms);
                  invalidate();
                }}
              />
              <NumberField
                label="Wall time per run, seconds"
                min={1}
                value={maxWallSeconds}
                onChange={(value) => {
                  setMaxWallSeconds(value);
                  invalidate();
                }}
              />
              <NumberField
                label="Early success target"
                min={1}
                max={arms.length * repetitions}
                value={successTarget}
                onChange={(value) => {
                  setSuccessTarget(value);
                  invalidate();
                }}
              />
              <BuilderField label="Player profile">
                <input
                  value={playerProfile}
                  onChange={(event) => setPlayerProfile(event.target.value)}
                />
              </BuilderField>
            </div>
            <div className="builder-budget">
              <CircleDollarSign size={17} />
              <div>
                <span>Calculated maximum</span>
                <b>{usd(effectiveMaxSpend)}</b>
              </div>
              <p>
                {arms.length} arms × {repetitions} runs × {usd(sampleCeiling)}.
                Local policy ceiling: {usd(catalog.execution.max_spend_usd)}.
              </p>
            </div>
          </BuilderSection>

          <BuilderSection
            icon={<ShieldCheck size={16} />}
            id="experiment-preflight"
            number="04"
            title="Deterministic preflight"
          >
            <div className="builder-preflight">
              <div>
                <h3>Before any runner starts</h3>
                <p>
                  Validate the scenario, complete arm configurations, reset
                  identity, evidence predicate, stop criteria, and maximum spend.
                </p>
              </div>
              <button
                className="builder-primary"
                disabled={validating || definition === null}
                type="button"
                onClick={() => void validate()}
              >
                <ShieldCheck size={14} />
                {validating ? "Validating…" : "Validate definition"}
              </button>
            </div>
            {validationError ? (
              <p className="builder-error" role="alert">{validationError}</p>
            ) : null}
            {validation !== null ? (
              <ValidationPanel result={validation} />
            ) : null}

            {validation?.validation.valid ? (
              <div className="builder-run">
                <div>
                  <span>Execution gate</span>
                  <h3>
                    {catalog.execution.available
                      ? "Definition is ready for explicit confirmation"
                      : "Definition is valid, local execution is disabled"}
                  </h3>
                  <p>
                    Validation does not spend money. Starting the queued runs
                    requires a second confirmation of the exact ceiling.
                  </p>
                </div>
                {catalog.execution.available ? (
                  <button
                    className="builder-primary"
                    type="button"
                    onClick={() => setConfirmationOpen(true)}
                  >
                    <Play size={14} /> Prepare run
                  </button>
                ) : (
                  <span className="builder-policy">Local policy</span>
                )}
              </div>
            ) : null}

            {confirmationOpen ? (
              <div className="builder-confirm">
                <h3>Confirm paid execution</h3>
                <p>
                  Type the exact maximum, {usd(effectiveMaxSpend)}, and confirm
                  that the validated definition should enter the local queue.
                </p>
                <label>
                  <span>Maximum spend</span>
                  <input
                    inputMode="decimal"
                    value={confirmedSpend}
                    onChange={(event) => setConfirmedSpend(event.target.value)}
                  />
                </label>
                <label className="builder-check">
                  <input
                    checked={confirmed}
                    type="checkbox"
                    onChange={(event) => setConfirmed(event.target.checked)}
                  />
                  Start the validated, reset-isolated sample queue.
                </label>
                <button
                  className="builder-primary"
                  disabled={
                    starting
                    || !confirmed
                    || Number(confirmedSpend) !== effectiveMaxSpend
                  }
                  type="button"
                  onClick={() => void start()}
                >
                  <Play size={14} />
                  {starting ? "Starting…" : `Start ${arms.length * repetitions} runs`}
                </button>
              </div>
            ) : null}
            {runError ? <p className="builder-error" role="alert">{runError}</p> : null}
          </BuilderSection>
        </main>
      </div>
    </section>
  );
}

function BuilderSection({
  children,
  icon,
  id,
  number,
  title,
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  id: string;
  number: string;
  title: string;
}) {
  return (
    <section className="builder-section" id={id}>
      <header>
        <span>{number}</span>
        {icon}
        <h2>{title}</h2>
      </header>
      <div>{children}</div>
    </section>
  );
}

function BuilderField({
  children,
  className,
  label,
}: {
  children: React.ReactNode;
  className?: string;
  label: string;
}) {
  return (
    <label className={`builder-field ${className ?? ""}`}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function NumberField({
  label,
  max,
  min,
  onChange,
  step,
  value,
}: {
  label: string;
  max?: number;
  min: number;
  onChange: (value: number) => void;
  step?: number;
  value: number;
}) {
  return (
    <BuilderField label={label}>
      <input
        max={max}
        min={min}
        step={step ?? 1}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </BuilderField>
  );
}

function FeatureControl({
  arm,
  feature,
  onChange,
}: {
  arm: ArmDraft;
  feature: ExperimentFeature;
  onChange: (value: boolean | number | string) => void;
}) {
  const value = arm.values[feature.id];
  if (feature.kind === "boolean") {
    return (
      <label className="builder-toggle">
        <input
          checked={value === true}
          type="checkbox"
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{value === true ? "Enabled" : "Disabled"}</span>
      </label>
    );
  }
  if (feature.kind === "enum") {
    return (
      <select
        aria-label={`${arm.label} ${feature.label}`}
        value={String(value)}
        onChange={(event) => onChange(event.target.value)}
      >
        {feature.options.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    );
  }
  return (
    <input
      aria-label={`${arm.label} ${feature.label}`}
      max={feature.maximum ?? undefined}
      min={feature.minimum ?? undefined}
      step={feature.kind === "integer" ? 1 : feature.kind === "number" ? 0.01 : undefined}
      type={feature.kind === "integer" || feature.kind === "number" ? "number" : "text"}
      value={String(value)}
      onChange={(event) => onChange(
        feature.kind === "integer"
          ? Number.parseInt(event.target.value, 10)
          : feature.kind === "number"
            ? Number(event.target.value)
            : event.target.value,
      )}
    />
  );
}

function ValidationPanel({ result }: { result: ValidationResult }) {
  const valid = result.validation.valid;
  return (
    <div className={`builder-validation ${valid ? "is-valid" : "is-invalid"}`}>
      <header>
        {valid
          ? <CheckCircle2 size={17} />
          : <AlertTriangle size={17} />}
        <div>
          <b>{valid ? "Definition is valid" : "Definition needs repair"}</b>
          <span>
            {result.queue.length} deterministic sample identities planned
          </span>
        </div>
      </header>
      {result.validation.issues.length > 0 ? (
        <ul>
          {result.validation.issues.map((issue) => <li key={issue}>{issue}</li>)}
        </ul>
      ) : (
        <ul>
          {result.validation.checks.map((check) => <li key={check}>{check}</li>)}
        </ul>
      )}
    </div>
  );
}

function BuilderMetric({ label, value }: { label: string; value: string }) {
  return (
    <span className="builder-metric">
      <small>{label}</small>
      <b>{value}</b>
    </span>
  );
}

function updatePolicyLimit(
  value: number,
  arms: ArmDraft[],
  setArms: React.Dispatch<React.SetStateAction<ArmDraft[]>>,
): void {
  if (!arms.some((arm) => "policy.max_iterations" in arm.values)) return;
  setArms((current) => current.map((arm) => ({
    ...arm,
    values: { ...arm.values, "policy.max_iterations": value },
  })));
}

function definitionId(title: string, scenarioId: string): string {
  const slug = title
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, "-")
    .replaceAll(/^-|-$/g, "")
    .slice(0, 48) || "experiment";
  return `${scenarioId.toLowerCase()}-${slug}`;
}

function roundMoney(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function usd(value: number): string {
  return `$${value.toFixed(2)}`;
}
