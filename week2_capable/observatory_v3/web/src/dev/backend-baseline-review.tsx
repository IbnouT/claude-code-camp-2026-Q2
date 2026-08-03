import { useEffect, useState } from "react"
import {
  ArrowRight,
  CheckCircle2,
  Database,
  FileJson,
  ScanSearch,
  TimerReset,
  TriangleAlert,
} from "lucide-react"

import baselineSource from "./backend-baseline.json?raw"
import readinessSource from "./backend-readiness.json?raw"

interface Metric {
  p50_ms: number
  p95_ms: number
  payload_bytes?: number
  rows_read?: number
  sessions_hydrated_per_request?: number
}

interface ReadinessMetricValue extends Metric {
  samples: number
}

interface BaselineEvidence {
  schema: "observatory.backend-baseline.v1"
  measurement: {
    repetitions: number
    percentiles: {
      p50: "median"
      p95: "nearest_rank"
    }
  }
  provenance: {
    fixture: string
    sanitized: boolean
    sessions: number
    target_gateway_events: number
    target_agent_records: number
    target_agent_log_bytes: number
    unrelated_gateway_events: number
    unrelated_agent_records: number
    unrelated_agent_log_bytes: number
    target_operator_messages: number
    target_lifecycle_records: number
    registry_schema: {
      version: number
      version_state: string
    }
    gateway_schema: {
      version: number
    }
  }
  metrics: {
    catalog: Metric
    selected_session_lookup: Metric & {
      unrelated_sessions_hydrated: number
    }
    reconnect_gateway_read: Metric
    incremental_gateway_read: Metric
    live_projection: Metric
    investigation_projection: Metric
    investigation_serialization: Metric & {
      payload_bytes: number
    }
  }
  failure_modes: {
    unrelated_session_scan: {
      reproduced: boolean
      unrelated_sessions_hydrated: number
    }
    full_history_fold: {
      reproduced: boolean
      gateway_events_folded: number
      agent_records_folded: number
    }
    unbounded_payload: {
      reproduced: boolean
      investigation_payload_bytes: number
    }
    partial_line: {
      reproduced: boolean
      current_behavior: string
    }
  }
  readiness_markers: {
    server_catalog_json_ready_p50_ms: number
    server_detail_json_ready_p50_ms: number
  }
}

interface ReadinessEvidence {
  schema: "observatory.backend-readiness.v1"
  browser_gate: {
    artifact: string
    cache_state: string
    production_build: boolean
    samples: number
  }
  fixture: {
    agent_records: number
    digest_sha256: string
    gateway_events: number
    sessions: number
  }
  rebuild: {
    identity_stable: boolean
    source_loss: boolean
  }
  resources: {
    cold_useful_content_ms: number
    concurrent_projection_generation: number
    event_loop_delay: ReadinessMetricValue
    payload_bytes: {
      catalog: number
      live: number
      summary: number
    }
    stopped_session: {
      recurring_refresh_requests: number
    }
    warm: {
      catalog: ReadinessMetricValue
      live: ReadinessMetricValue
      summary: ReadinessMetricValue
    }
  }
  scenarios: {
    cold: boolean
    concurrent: boolean
    long_session: boolean
    running_session: boolean
    stopped_session: boolean
    warm: boolean
  }
  system: {
    materializer_capacity: number
    peak_traced_memory_bytes: number
    storage_worker_capacity: number
  }
}

const parseStarted = performance.now()
const baseline = readBaseline(baselineSource)
const readiness = readReadiness(readinessSource)
const parsedAt = performance.now()

const path = [
  {
    label: "Registry",
    value: `${baseline.provenance.sessions} sessions`,
    detail: "unversioned schema",
    icon: Database,
  },
  {
    label: "Selected lookup",
    value: `${baseline.metrics.selected_session_lookup.p50_ms.toFixed(2)} ms`,
    detail: `${baseline.metrics.selected_session_lookup.unrelated_sessions_hydrated} unrelated hydrated`,
    icon: ScanSearch,
  },
  {
    label: "Full read",
    value: `${baseline.metrics.reconnect_gateway_read.p50_ms.toFixed(2)} ms`,
    detail: `${formatInteger(baseline.provenance.target_gateway_events)} events`,
    icon: TimerReset,
  },
  {
    label: "Projection",
    value: `${baseline.metrics.investigation_projection.p50_ms.toFixed(2)} ms`,
    detail: `${formatInteger(baseline.provenance.target_agent_records)} agent records folded`,
    icon: FileJson,
  },
] as const

const failureModes = [
  {
    label: "Unrelated-session scan",
    value: `${baseline.failure_modes.unrelated_session_scan.unrelated_sessions_hydrated} unrelated sessions`,
    detail: "Selected lookup hydrates the complete registry.",
  },
  {
    label: "Full-history fold",
    value: `${formatInteger(
      baseline.failure_modes.full_history_fold.gateway_events_folded +
        baseline.failure_modes.full_history_fold.agent_records_folded
    )} records`,
    detail: "Every detail request rebuilds the complete projection.",
  },
  {
    label: "Unbounded detail payload",
    value: formatBytes(
      baseline.failure_modes.unbounded_payload.investigation_payload_bytes
    ),
    detail: "The investigation response has no bounded hierarchy.",
  },
  {
    label: "Interrupted JSONL",
    value: baseline.failure_modes.partial_line.current_behavior,
    detail: "One incomplete final line rejects the agent history.",
  },
] as const

export function BackendBaselineReview() {
  const [browserReadyMs, setBrowserReadyMs] = useState<number | null>(null)

  useEffect(() => {
    let paintFrame = 0
    const renderFrame = requestAnimationFrame(() => {
      paintFrame = requestAnimationFrame(() => {
        setBrowserReadyMs(performance.now() - parseStarted)
      })
    })
    return () => {
      cancelAnimationFrame(renderFrame)
      cancelAnimationFrame(paintFrame)
    }
  }, [])

  return (
    <section
      aria-labelledby="backend-baseline-title"
      className="border-b border-line py-7"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-accent uppercase">
            Landing 2 · Measured current path
          </p>
          <h2
            id="backend-baseline-title"
            className="mt-2 text-2xl font-semibold tracking-tight"
          >
            Backend contract baseline
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-content-muted">
            Sanitized deterministic evidence reproduces the current failure
            modes before backend behavior changes. Values are measurements, not
            targets.
          </p>
        </div>
        <div className="rounded-xl border border-line bg-surface px-4 py-3 text-right">
          <p className="text-xs text-content-muted">Browser parse and paint</p>
          <p
            className="mt-1 font-mono text-sm text-content-primary"
            data-browser-ready-ms={browserReadyMs?.toFixed(2)}
            data-testid="browser-ready"
          >
            {browserReadyMs === null
              ? "Measuring"
              : `${browserReadyMs.toFixed(2)} ms`}
          </p>
          <p className="mt-1 text-[0.7rem] text-content-muted">
            JSON parse {Math.max(0, parsedAt - parseStarted).toFixed(2)} ms
          </p>
        </div>
      </div>

      <article
        className="mt-6 rounded-2xl border border-success bg-surface p-5"
        data-testid="backend-readiness"
      >
        <div className="flex items-start gap-3">
          <CheckCircle2
            aria-hidden="true"
            className="mt-0.5 size-5 text-success"
          />
          <div>
            <h3 className="font-semibold text-content-primary">
              B9 bounded browser-ready path
            </h3>
            <p className="mt-1 text-sm text-content-muted">
              Measured on the maintained 38-session fixture. Latency is reported
              evidence, not an invented threshold.
            </p>
          </div>
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <ReadinessMetric
            label="Cold useful content"
            value={`${readiness.resources.cold_useful_content_ms.toFixed(2)} ms`}
            detail={`${formatInteger(readiness.fixture.agent_records + readiness.fixture.gateway_events)} retained records`}
          />
          <ReadinessMetric
            label="Warm summary p50 / p95"
            value={`${readiness.resources.warm.summary.p50_ms.toFixed(2)} / ${readiness.resources.warm.summary.p95_ms.toFixed(2)} ms`}
            detail={`${readiness.resources.warm.summary.samples} measured runs`}
          />
          <ReadinessMetric
            label="Warm Live p50 / p95"
            value={`${readiness.resources.warm.live.p50_ms.toFixed(2)} / ${readiness.resources.warm.live.p95_ms.toFixed(2)} ms`}
            detail={formatBytes(readiness.resources.payload_bytes.live)}
          />
          <ReadinessMetric
            label="Event-loop delay p95"
            value={`${readiness.resources.event_loop_delay.p95_ms.toFixed(2)} ms`}
            detail={`${readiness.system.storage_worker_capacity} storage workers, ${readiness.system.materializer_capacity} flights`}
          />
        </dl>
        <ul className="mt-5 grid gap-2 text-xs text-content-muted sm:grid-cols-2 xl:grid-cols-4">
          <li>One projection generation serves concurrent cold readers.</li>
          <li>
            Stopped recurring refreshes:{" "}
            {readiness.resources.stopped_session.recurring_refresh_requests}.
          </li>
          <li>
            Rebuild identity stable:{" "}
            {readiness.rebuild.identity_stable ? "yes" : "no"}.
          </li>
          <li>
            Production Chromium: {readiness.browser_gate.samples} measured runs.
          </li>
        </ul>
        <p className="mt-4 font-mono text-[0.68rem] text-content-muted">
          Fixture {readiness.fixture.digest_sha256.slice(0, 16)} · peak traced
          memory {formatBytes(readiness.system.peak_traced_memory_bytes)}
        </p>
      </article>

      <ol
        aria-label="Measured backend request path"
        className="mt-6 grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr]"
      >
        {path.map(({ label, value, detail, icon: Icon }, index) => (
          <li key={label} className="contents">
            <article className="rounded-2xl border border-line bg-surface p-4">
              <Icon aria-hidden="true" className="size-5 text-accent" />
              <p className="mt-4 text-xs font-semibold tracking-wide text-content-muted uppercase">
                {label}
              </p>
              <p className="mt-1 font-mono text-base font-semibold text-content-primary">
                {value}
              </p>
              <p className="mt-1 text-xs leading-5 text-content-muted">
                {detail}
              </p>
            </article>
            {index < path.length - 1 ? (
              <ArrowRight
                aria-hidden="true"
                className="mx-auto hidden size-5 self-center text-line-strong lg:block"
              />
            ) : null}
          </li>
        ))}
      </ol>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_1.1fr]">
        <article className="rounded-2xl border border-warning bg-warning-soft p-5">
          <div className="flex items-center gap-3">
            <TriangleAlert aria-hidden="true" className="size-5 text-warning" />
            <div>
              <h3 className="font-semibold">Reproduced failure modes</h3>
              <p className="text-sm text-warning">
                B1 through B5 must remove these measured costs
              </p>
            </div>
          </div>
          <dl className="mt-5 grid gap-3 sm:grid-cols-2">
            {failureModes.map(({ label, value, detail }) => (
              <div
                key={label}
                className="rounded-xl border border-line bg-canvas p-4"
              >
                <dt className="text-xs text-content-muted">{label}</dt>
                <dd className="mt-1 font-mono text-sm font-semibold text-warning">
                  {value}
                </dd>
                <dd className="mt-2 text-xs leading-5 text-content-muted">
                  {detail}
                </dd>
              </div>
            ))}
          </dl>
        </article>

        <article className="overflow-hidden rounded-2xl border border-line bg-surface">
          <div className="border-b border-line px-5 py-4">
            <h3 className="font-semibold">Measured operations</h3>
            <p className="text-sm text-content-muted">
              {baseline.measurement.repetitions} repetitions, median p50,
              nearest-rank p95
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-xs text-content-muted">
                <tr>
                  <th className="px-5 py-3 font-medium">Operation</th>
                  <th className="px-3 py-3 font-medium">p50</th>
                  <th className="px-3 py-3 font-medium">p95</th>
                  <th className="px-5 py-3 text-right font-medium">Work</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                <MetricRow
                  label="Catalog"
                  metric={baseline.metrics.catalog}
                  work={`${baseline.provenance.sessions} sessions`}
                />
                <MetricRow
                  label="Selected lookup"
                  metric={baseline.metrics.selected_session_lookup}
                  work={`${baseline.provenance.sessions} hydrated`}
                />
                <MetricRow
                  label="Reconnect history"
                  metric={baseline.metrics.reconnect_gateway_read}
                  work={`${formatInteger(baseline.provenance.target_gateway_events)} rows`}
                />
                <MetricRow
                  label="Incremental read"
                  metric={baseline.metrics.incremental_gateway_read}
                  work="5 rows"
                />
                <MetricRow
                  label="Investigation projection"
                  metric={baseline.metrics.investigation_projection}
                  work={`${formatInteger(
                    baseline.provenance.target_gateway_events +
                      baseline.provenance.target_agent_records
                  )} folded`}
                />
                <MetricRow
                  label="Investigation serialization"
                  metric={baseline.metrics.investigation_serialization}
                  work={formatBytes(
                    baseline.metrics.investigation_serialization.payload_bytes
                  )}
                />
              </tbody>
            </table>
          </div>
          <div className="grid gap-px border-t border-line bg-line sm:grid-cols-2">
            <div className="bg-canvas px-5 py-3">
              <p className="text-xs text-content-muted">
                Catalog JSON ready p50
              </p>
              <p className="mt-1 font-mono text-sm text-content-primary">
                {baseline.readiness_markers.server_catalog_json_ready_p50_ms.toFixed(
                  2
                )}{" "}
                ms
              </p>
            </div>
            <div className="bg-canvas px-5 py-3">
              <p className="text-xs text-content-muted">
                Detail JSON ready p50
              </p>
              <p className="mt-1 font-mono text-sm text-content-primary">
                {baseline.readiness_markers.server_detail_json_ready_p50_ms.toFixed(
                  2
                )}{" "}
                ms
              </p>
            </div>
          </div>
        </article>
      </div>

      <p className="mt-4 text-xs leading-5 text-content-muted">
        Fixture: {baseline.provenance.fixture}. Registry schema{" "}
        {baseline.provenance.registry_schema.version} (
        {baseline.provenance.registry_schema.version_state}), gateway schema{" "}
        {baseline.provenance.gateway_schema.version}. Agent, operator,
        lifecycle, stopped-session, and partial-line evidence are retained. The
        calibrated envelope includes{" "}
        {formatInteger(baseline.provenance.unrelated_gateway_events)} unrelated
        gateway events and{" "}
        {formatInteger(baseline.provenance.unrelated_agent_records)} unrelated
        agent records.
      </p>
    </section>
  )
}

function MetricRow({
  label,
  metric,
  work,
}: {
  label: string
  metric: Metric
  work: string
}) {
  return (
    <tr>
      <th className="px-5 py-3 font-medium text-content-muted">{label}</th>
      <td className="px-3 py-3 font-mono text-content-muted">
        {metric.p50_ms.toFixed(2)} ms
      </td>
      <td className="px-3 py-3 font-mono text-content-muted">
        {metric.p95_ms.toFixed(2)} ms
      </td>
      <td className="px-5 py-3 text-right font-mono text-content-muted">
        {work}
      </td>
    </tr>
  )
}

function ReadinessMetric({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail: string
}) {
  return (
    <div className="rounded-xl border border-line bg-canvas p-4">
      <dt className="text-xs text-content-muted">{label}</dt>
      <dd className="mt-1 font-mono text-sm font-semibold text-content-primary">
        {value}
      </dd>
      <dd className="mt-2 text-xs leading-5 text-content-muted">{detail}</dd>
    </div>
  )
}

function readBaseline(source: string): BaselineEvidence {
  const value: unknown = JSON.parse(source)
  if (
    typeof value !== "object" ||
    value === null ||
    !("schema" in value) ||
    value.schema !== "observatory.backend-baseline.v1"
  ) {
    throw new Error("Unsupported backend baseline evidence")
  }
  return value as BaselineEvidence
}

function readReadiness(source: string): ReadinessEvidence {
  const value: unknown = JSON.parse(source)
  if (
    typeof value !== "object" ||
    value === null ||
    !("schema" in value) ||
    value.schema !== "observatory.backend-readiness.v1"
  ) {
    throw new Error("Unsupported backend readiness evidence")
  }
  return value as ReadinessEvidence
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US").format(value)
}

function formatBytes(value: number): string {
  return `${(value / (1024 * 1024)).toFixed(2)} MiB`
}
