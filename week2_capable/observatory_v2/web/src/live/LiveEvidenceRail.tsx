import type {
  Observed,
  Snapshot,
} from "../contracts";
import {
  cacheHit,
  formatAge,
  latestCommand,
  latestContextFill,
  observedNumber,
  projectSpend,
  responseTrend,
  tokensIn,
} from "./liveEvidence";
import { LiveFrictionBlock } from "./LiveFrictionBlock";
import type { LiveSnapshotState } from "./useLiveSnapshot";

const conditionPresentations: Record<string, {
  label: string;
  tone: "bad" | "warn";
}> = {
  hungry: { label: "Hungry", tone: "warn" },
  thirsty: { label: "Thirsty", tone: "warn" },
  drunk: { label: "Intoxicated", tone: "warn" },
  poisoned: { label: "Poisoned", tone: "bad" },
};

export function LiveEvidenceRail({
  captureStatus,
  connectionState,
  snapshot,
}: {
  captureStatus: string | null;
  connectionState: LiveSnapshotState;
  snapshot: Snapshot | null;
}) {
  if (snapshot === null) {
    return <p className="live-rail-empty">Waiting for retained evidence…</p>;
  }
  const fields = snapshot.player_status.fields;
  const posture = fields.posture?.value;
  const command = latestCommand(snapshot);
  const conditions = Object.entries(conditionPresentations).flatMap(([key, presentation]) => {
    const observed = fields[key];
    return observed?.value === true
      ? [{ key, observed, ...presentation }]
      : [];
  });
  return (
    <div className="live-rail-content">
      <RailBlock
        status={snapshot.following_live ? "live" : "history"}
        title="Now"
      >
        {typeof posture === "string" ? (
          <span
            className={`live-posture-pill${snapshot.combat ? " is-fighting" : ""}`}
            title={evidenceTitle(fields.posture)}
          >
            {snapshot.combat ? "fighting" : posture}
          </span>
        ) : snapshot.combat ? (
          <span className="live-posture-pill is-fighting">fighting</span>
        ) : null}
        <EvidenceText
          label="Latest tool action"
          value={snapshot.agent_belief?.text ?? "No tool action retained"}
          meta={snapshot.agent_belief === null
            ? null
            : formatAge(snapshot.agent_belief.observed_at)}
          title={snapshot.agent_belief?.evidence}
        />
        <EvidenceText label="Last command" value={command ?? "No command retained"} />
      </RailBlock>

      <RailBlock title="Character">
        <VitalBar
          label="HP"
          tone="hit"
          value={snapshot.vitals.hit}
          maximum={observedNumber(fields, "max_hit")}
        />
        <VitalBar
          label="Mana"
          tone="mana"
          value={snapshot.vitals.mana}
          maximum={observedNumber(fields, "max_mana")}
        />
        <VitalBar
          label="Move"
          tone="move"
          value={snapshot.vitals.move}
          maximum={observedNumber(fields, "max_move")}
        />
        <div className="live-character-facts">
          <ObservedFact label="Level" observed={fields.level} />
          <ObservedFact label="Gold" observed={fields.gold} />
        </div>
        {conditions.length === 0 ? null : (
          <div className="live-condition-list" aria-label="Observed conditions">
            {conditions.map(({ key, label, observed, tone }) => (
              <span
                className={`is-${tone}`}
                key={key}
                title={evidenceTitle(observed)}
              >
                {label}
              </span>
            ))}
          </div>
        )}
      </RailBlock>

      <RailBlock title="Live economics">
        <LiveEconomics snapshot={snapshot} />
      </RailBlock>
      <LiveFrictionBlock
        captureStatus={captureStatus}
        connectionState={connectionState}
        snapshot={snapshot}
      />
    </div>
  );
}

function RailBlock({
  children,
  status,
  title,
}: {
  children: React.ReactNode;
  status?: "live" | "history";
  title: string;
}) {
  return (
    <section className="live-rail-block">
      <header className="live-rail-block-heading">
        <h2>{title}</h2>
        {status === undefined ? null : (
          <span className={`live-rail-prefix-state is-${status}`}>
            <i aria-hidden="true" />
            {status === "live" ? "Live" : "Historical prefix"}
          </span>
        )}
      </header>
      {children}
    </section>
  );
}

function EvidenceText({
  label,
  meta,
  title,
  value,
}: {
  label: string;
  meta?: string | null;
  title?: string;
  value: string;
}) {
  return (
    <div className="live-evidence-text" title={title}>
      <small>{label}{meta === null || meta === undefined ? "" : ` · ${meta}`}</small>
      <strong>{value}</strong>
    </div>
  );
}

function VitalBar({
  label,
  maximum,
  tone,
  value,
}: {
  label: string;
  maximum: number | null;
  tone: "hit" | "mana" | "move";
  value: number | undefined;
}) {
  const observed = typeof value === "number";
  const ratio = observed && maximum !== null && maximum > 0
    ? Math.min(Math.max(value / maximum, 0), 1)
    : 0;
  return (
    <div className={`live-vital is-${tone}`}>
      <span>{label}</span>
      <strong>{observed
        ? maximum === null ? value : `${value} / ${maximum}`
        : "Not observed"}</strong>
      <span aria-hidden="true" className="live-vital-track">
        <i style={{ width: `${ratio * 100}%` }} />
      </span>
    </div>
  );
}

function ObservedFact({
  label,
  observed,
}: {
  label: string;
  observed: Observed | undefined;
}) {
  return (
    <div title={evidenceTitle(observed)}>
      <small>{label}</small>
      <strong>{observed === undefined ? "Not observed" : String(observed.value)}</strong>
    </div>
  );
}

function LiveEconomics({ snapshot }: { snapshot: Snapshot }) {
  const spend = projectSpend(snapshot);
  const ratio = spend.cap === null || spend.cap <= 0
    ? null
    : Math.max(spend.amount / spend.cap, 0);
  const latestCost = snapshot.economics.at(-1)?.cost_usd ?? null;
  const trend = responseTrend(snapshot.economics);
  const hit = cacheHit(snapshot.usage);
  const context = latestContextFill(snapshot);
  return (
    <>
      <div className="live-spend">
        <div>
          <small>{spend.scope === "turn" ? "Turn spend" : "Session spend"}</small>
          <strong>{money(spend.amount)}{spend.cap === null ? "" : ` / ${money(spend.cap)}`}</strong>
        </div>
        {ratio === null ? null : (
          <span aria-label={`${Math.round(ratio * 100)} percent of cap`} className="live-spend-track">
            <i style={{ width: `${Math.min(ratio, 1) * 100}%` }} />
          </span>
        )}
      </div>
      <div className="live-economics-grid">
        <EconomicFact
          label="Latest response"
          value={latestCost === null ? "Not retained" : money(latestCost)}
          meta={trend === null ? null : `${trend >= 0 ? "+" : ""}${Math.round(trend * 100)}% vs prior`}
        />
        <EconomicFact label="Tokens in" value={tokensIn(snapshot.usage).toLocaleString()} />
        <EconomicFact label="Tokens out" value={(snapshot.usage.output ?? 0).toLocaleString()} />
        <EconomicFact label="Cache hit" value={hit === null ? "Not observed" : `${Math.round(hit * 100)}%`} />
      </div>
      <CostSparkline values={snapshot.economics.slice(-20).map(({ cost_usd }) => cost_usd)} />
      {context === null ? null : (
        <div className="live-context-fill">
          <small>Latest response context</small>
          <strong>{Math.round(context * 100)}%</strong>
          <span><i style={{ width: `${Math.min(Math.max(context, 0), 1) * 100}%` }} /></span>
        </div>
      )}
    </>
  );
}

function EconomicFact({
  label,
  meta,
  value,
}: {
  label: string;
  meta?: string | null;
  value: string;
}) {
  return (
    <div>
      <small>{label}</small>
      <strong>{value}</strong>
      {meta === null || meta === undefined ? null : <em>{meta}</em>}
    </div>
  );
}

function CostSparkline({ values }: { values: number[] }) {
  const width = 240;
  const height = 36;
  const maximum = Math.max(...values, 0.000001);
  const points = values.map((value, index) => {
    const x = values.length <= 1 ? 0 : index * width / (values.length - 1);
    const y = height - value / maximum * (height - 4) - 2;
    return `${x},${y}`;
  }).join(" ");
  return (
    <figure className="live-cost-sparkline">
      <figcaption>Cost per response: last 20</figcaption>
      {values.length === 0 ? <span>No response costs retained</span> : (
        <svg aria-label="Cost per response sparkline" role="img" viewBox={`0 0 ${width} ${height}`}>
          <polyline points={points} />
        </svg>
      )}
    </figure>
  );
}

function money(value: number): string {
  return `$${value.toFixed(value < 0.01 ? 4 : 3)}`;
}

function evidenceTitle(observed: Observed | undefined): string | undefined {
  if (observed === undefined) return undefined;
  return `${observed.method} · sequence ${observed.sequence}`;
}
