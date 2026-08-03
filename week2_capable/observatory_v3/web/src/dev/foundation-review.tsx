import { useState } from "react"
import {
  Blocks,
  CheckCircle2,
  Gauge,
  GitBranch,
  ShieldCheck,
  Workflow,
} from "lucide-react"

import { BackendBaselineReview } from "./backend-baseline-review"
import { PrimitiveReview } from "./primitive-review"
import { TokenReviewGallery } from "./token-review"

const FOUNDATION_REVIEW_MARKER = "V3_FOUNDATION_REVIEW_HMR_CHECK"

const foundationFacts = [
  {
    label: "Runtime",
    value: "React 19 · Vite 8 · TypeScript 6",
    detail: "Node 24 LTS with exact dependency pins",
    icon: Blocks,
  },
  {
    label: "Architecture",
    value: "Isolated client application",
    detail: "No v2 runtime imports or copied feature code",
    icon: GitBranch,
  },
  {
    label: "Verification",
    value: "Full-source automated gates",
    detail: "Types, lint, format, tests, browser, accessibility",
    icon: ShieldCheck,
  },
] as const

const gateLabels = [
  "Exact dependency graph",
  "Strict TypeScript",
  "Oxlint with React and accessibility",
  "Vitest and Testing Library",
  "Playwright and axe",
  "Production bundle isolation",
] as const

export function App() {
  const [probe, setProbe] = useState("")

  return (
    <main className="min-h-svh bg-canvas text-content-primary">
      <div className="mx-auto flex min-h-svh w-full max-w-7xl flex-col px-5 py-8 sm:px-8 lg:px-12 lg:py-10">
        <header className="flex flex-col gap-5 border-b border-line pb-7 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.18em] text-accent uppercase">
              <Workflow aria-hidden="true" className="size-4" />
              Boukensha Observatory
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              Observatory architecture
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-content-muted sm:text-base">
              A development-only surface for measured architecture and quality
              gates before product routes are introduced.
            </p>
          </div>
          <div className="w-fit rounded-full border border-accent bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent">
            Landing 2 · Backend baseline
          </div>
        </header>

        <BackendBaselineReview />

        <TokenReviewGallery />

        <PrimitiveReview />

        <section
          aria-labelledby="foundation-status"
          className="grid gap-4 py-7 md:grid-cols-3"
        >
          <h2 id="foundation-status" className="sr-only">
            Foundation status
          </h2>
          {foundationFacts.map(({ label, value, detail, icon: Icon }) => (
            <article
              key={label}
              className="rounded-2xl border border-line bg-surface p-5"
            >
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold tracking-[0.16em] text-content-muted uppercase">
                  {label}
                </p>
                <Icon aria-hidden="true" className="size-5 text-accent" />
              </div>
              <p className="mt-5 text-lg font-semibold text-content-primary">
                {value}
              </p>
              <p className="mt-1 text-sm leading-6 text-content-muted">
                {detail}
              </p>
            </article>
          ))}
        </section>

        <section className="grid flex-1 gap-5 pb-8 lg:grid-cols-[1.3fr_0.7fr]">
          <article className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-xl bg-success-soft text-success">
                <CheckCircle2 aria-hidden="true" className="size-5" />
              </div>
              <div>
                <h2 className="font-semibold">Foundation gates</h2>
                <p className="text-sm text-content-muted">
                  Automated before product work begins
                </p>
              </div>
            </div>
            <ul className="mt-6 grid gap-3 sm:grid-cols-2">
              {gateLabels.map((label) => (
                <li
                  key={label}
                  className="flex items-center gap-3 rounded-xl border border-line bg-canvas px-4 py-3 text-sm text-content-muted"
                >
                  <span
                    aria-hidden="true"
                    className="size-2 rounded-full bg-success"
                  />
                  {label}
                </li>
              ))}
            </ul>
          </article>

          <article className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-xl bg-warning-soft text-warning">
                <Gauge aria-hidden="true" className="size-5" />
              </div>
              <div>
                <h2 className="font-semibold">Fast Refresh probe</h2>
                <p className="text-sm text-content-muted">
                  State must survive a source update
                </p>
              </div>
            </div>
            <label
              htmlFor="hmr-probe"
              className="mt-6 block text-sm font-medium text-content-muted"
            >
              HMR state probe
            </label>
            <input
              id="hmr-probe"
              value={probe}
              onChange={(event) => setProbe(event.currentTarget.value)}
              placeholder="Type before a source edit"
              className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-canvas px-3 text-sm text-content-primary outline-none placeholder:text-content-muted focus-visible:border-accent focus-visible:[box-shadow:var(--focus-ring)]"
            />
            <p
              data-testid="foundation-marker"
              className="mt-4 font-mono text-[0.7rem] tracking-wide text-content-muted"
            >
              {FOUNDATION_REVIEW_MARKER}
            </p>
          </article>
        </section>

        <footer className="border-t border-line pt-5 text-xs leading-5 text-content-muted">
          This review surface is available only in development and is excluded
          from the production module graph.
        </footer>
      </div>
    </main>
  )
}
