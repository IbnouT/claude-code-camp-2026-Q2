import { useMemo } from "react";
import type {
  SessionCostPoint,
  SessionEvidenceRecord,
  SessionInvestigation,
} from "../contracts";
import type { SessionSelection } from "./storyProjection";
import styles from "./SessionCost.module.css";

function cx(...names: string[]): string {
  return names.map((name) => styles[name]).filter(Boolean).join(" ");
}

type Props = {
  investigation: SessionInvestigation;
  selection: SessionSelection;
  onOpenStory: () => void;
  onSelect: (selection: SessionSelection) => void;
};

type AttributedPoint = SessionCostPoint & {
  record: SessionEvidenceRecord | null;
};

export function SessionCost({
  investigation,
  selection,
  onOpenStory,
  onSelect,
}: Props) {
  const points = useMemo(() => {
    const records = new Map(
      investigation.records.map((record) => [record.id, record]),
    );
    return investigation.cost.points.map((point): AttributedPoint => ({
      ...point,
      record: records.get(point.record_id) ?? null,
    }));
  }, [investigation]);
  const expensive = useMemo(
    () => [...points].sort((left, right) => right.cost_usd - left.cost_usd),
    [points],
  );
  const maximumCost = Math.max(...points.map((point) => point.cost_usd), 0);
  const tokenTotal = (
    investigation.cost.fresh_input_tokens
    + investigation.cost.cache_read_tokens
    + investigation.cost.cache_write_tokens
    + investigation.cost.output_tokens
  );
  const choose = (point: AttributedPoint): void => {
    onSelect({
      turn: point.record?.turn ?? null,
      iteration: point.iteration,
      recordId: point.record_id,
    });
    onOpenStory();
  };

  return (
    <section className={cx("session-cost-view")}  aria-label="Session cost">
      <header className={cx("session-cost-heading")} >
        <span className={cx("story-eyebrow")} >Session cost</span>
        <h2>
          {usd(investigation.cost.total_usd)} across {points.length} model
          {" "}response{points.length === 1 ? "" : "s"}
        </h2>
        <p>
          Every amount is attributed once. Select a bar or row to return to
          the response in its iteration story.
        </p>
      </header>

      <div className={cx("session-cost-grid")} >
        <article className={cx("session-cost-panel", "is-chart")} >
          <header>
            <div>
              <h3>Cost by response over time</h3>
              <p>Chronological model calls, from session start to stop.</p>
            </div>
            <span>{investigation.cost.complete ? "Reconciled" : "Partial"}</span>
          </header>
          {points.length === 0 ? (
            <div className={cx("session-cost-empty")}>
              No response-level cost points were retained.
            </div>
          ) : (
            <div
              aria-label="Cost by response"
              className={cx("session-cost-chart")}
              role="list"
            >
              {points.map((point, index) => (
                <button
                  aria-label={[
                    `Response ${index + 1}`,
                    point.iteration === null
                      ? "iteration unavailable"
                      : `iteration ${point.iteration}`,
                    usd(point.cost_usd),
                  ].join(", ")}
                  aria-pressed={selection.recordId === point.record_id}
                  key={point.record_id}
                  role="listitem"
                  style={{
                    "--cost-height": maximumCost <= 0
                      ? "2%"
                      : `${Math.max(point.cost_usd / maximumCost * 100, 2)}%`,
                  } as React.CSSProperties}
                  title={`Iteration ${point.iteration ?? "?"} · ${usd(point.cost_usd)}`}
                  type="button"
                  onClick={() => choose(point)}
                />
              ))}
            </div>
          )}
          <div className={cx("session-cost-axis")} >
            <span>Start</span>
            <span>Response {Math.max(points.length, 1)}</span>
          </div>
        </article>

        <article className={cx("session-cost-panel", "is-tokens")} >
          <header>
            <div>
              <h3>Token composition</h3>
              <p>Retained usage behind the reconciled response cost.</p>
            </div>
            <strong>{formatInteger(tokenTotal)} tok</strong>
          </header>
          <TokenRow
            color="fresh"
            label="Fresh input"
            total={tokenTotal}
            value={investigation.cost.fresh_input_tokens}
          />
          <TokenRow
            color="read"
            label="Cache read"
            total={tokenTotal}
            value={investigation.cost.cache_read_tokens}
          />
          <TokenRow
            color="write"
            label="Cache write"
            total={tokenTotal}
            value={investigation.cost.cache_write_tokens}
          />
          <TokenRow
            color="output"
            label="Output"
            total={tokenTotal}
            value={investigation.cost.output_tokens}
          />
          <dl className={cx("session-cost-reconciliation")} >
            <div>
              <dt>Response total</dt>
              <dd>{usd(investigation.cost.response_total_usd)}</dd>
            </div>
            <div>
              <dt>Raw response total</dt>
              <dd>{usd(investigation.cost.raw_response_total_usd)}</dd>
            </div>
            <div>
              <dt>Reconciliation delta</dt>
              <dd>{signedUsd(investigation.cost.reconciliation_delta_usd)}</dd>
            </div>
          </dl>
        </article>

        <article className={cx("session-cost-panel", "is-expensive")} >
          <header>
            <div>
              <h3>Most expensive responses</h3>
              <p>Open the exact response and the causal work around it.</p>
            </div>
          </header>
          <div className={cx("session-expensive-list")} >
            {expensive.slice(0, 12).map((point, index) => (
              <button
                aria-pressed={selection.recordId === point.record_id}
                key={point.record_id}
                type="button"
                onClick={() => choose(point)}
              >
                <span className={cx("session-cost-rank")} >{index + 1}</span>
                <span>
                  <strong>
                    Iteration {point.iteration ?? "?"} · Model response
                  </strong>
                  <small>
                    {formatTimestamp(point.record?.at)}
                    {" · "}
                    {formatInteger(point.context_tokens)} context tok
                  </small>
                </span>
                <b>{usd(point.cost_usd)}</b>
              </button>
            ))}
          </div>
        </article>
      </div>

      <footer className={cx("session-cost-footnote")} >
        <strong>Cost completeness</strong>
        <span>{investigation.cost.completeness_detail}</span>
      </footer>
    </section>
  );
}

function TokenRow({
  color,
  label,
  total,
  value,
}: {
  color: "fresh" | "read" | "write" | "output";
  label: string;
  total: number;
  value: number;
}) {
  return (
    <div className={cx("session-token-row")} >
      <div>
        <span>{label}</span>
        <strong>{formatInteger(value)}</strong>
      </div>
      <span className={cx("session-token-track")} >
        <span
          className={cx(`is-${color}`)}
          style={{ width: total <= 0 ? "0%" : `${value / total * 100}%` }}
        />
      </span>
    </div>
  );
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 0,
  }).format(value);
}

function formatTimestamp(value: string | undefined): string {
  if (!value) return "Timestamp unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  }).format(date);
}

function usd(value: number): string {
  return `$${value.toFixed(6)}`;
}

function signedUsd(value: number): string {
  if (Math.abs(value) < 0.0000005) return "$0.000000";
  return `${value > 0 ? "+" : "−"}$${Math.abs(value).toFixed(6)}`;
}
