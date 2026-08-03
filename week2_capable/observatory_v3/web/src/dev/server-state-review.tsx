import { DatabaseZap } from "lucide-react"

import { useCapabilities } from "@/data/capabilities"

const SERVER_STATE_REVIEW_MARKER = "V3_SERVER_STATE_REVIEW_ONLY"

function CapabilitiesSummary() {
  const result = useCapabilities()

  if (result.status === "loading") {
    return <p data-testid="capabilities-state">loading</p>
  }
  if (result.status === "error") {
    return <p data-testid="capabilities-state">{result.error.kind} error</p>
  }
  if (result.status === "reconnecting") {
    return <p data-testid="capabilities-state">reconnecting</p>
  }

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <p data-testid="capabilities-state">{result.status}</p>
      <p>
        <span className="font-semibold text-content-primary">
          {result.data.features.length}
        </span>{" "}
        features
      </p>
      <p>
        <span className="font-semibold text-content-primary">
          {result.data.sources.length}
        </span>{" "}
        sources
      </p>
    </div>
  )
}

function CapabilitySources() {
  const result = useCapabilities()
  if (
    result.status === "loading" ||
    result.status === "error" ||
    result.status === "reconnecting"
  ) {
    return null
  }

  return (
    <ul className="mt-4 grid gap-2 sm:grid-cols-2">
      {result.data.sources.map((source) => (
        <li
          key={source.id}
          className="rounded-xl border border-line bg-canvas px-4 py-3"
        >
          <span className="font-medium text-content-primary">
            {source.label}
          </span>
          <span className="ml-2 text-xs text-content-muted">
            {source.state}
          </span>
        </li>
      ))}
    </ul>
  )
}

function ServerStateReview() {
  return (
    <section
      aria-labelledby="server-state-review"
      className="mx-auto w-full max-w-7xl px-5 pb-8 sm:px-8 lg:px-12"
    >
      <span hidden>{SERVER_STATE_REVIEW_MARKER}</span>
      <article className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <div className="grid size-9 place-items-center rounded-xl bg-accent-soft text-accent">
            <DatabaseZap aria-hidden="true" className="size-5" />
          </div>
          <div>
            <h2 id="server-state-review" className="font-semibold">
              Typed server state
            </h2>
            <p className="text-sm text-content-muted">
              Two consumers share one validated capabilities request.
            </p>
          </div>
        </div>
        <div
          aria-live="polite"
          className="mt-5 rounded-xl border border-line bg-canvas p-4 text-sm text-content-muted"
        >
          <CapabilitiesSummary />
          <CapabilitySources />
        </div>
      </article>
    </section>
  )
}

export { ServerStateReview }
