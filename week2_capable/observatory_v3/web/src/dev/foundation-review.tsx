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

const FOUNDATION_REVIEW_MARKER = "V3_FOUNDATION_REVIEW_ONLY"

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
    <main className="min-h-svh bg-neutral-950 text-neutral-100">
      <div className="mx-auto flex min-h-svh w-full max-w-7xl flex-col px-5 py-8 sm:px-8 lg:px-12 lg:py-10">
        <header className="flex flex-col gap-5 border-b border-neutral-800 pb-7 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.18em] text-cyan-300 uppercase">
              <Workflow aria-hidden="true" className="size-4" />
              Boukensha Observatory
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              Observatory architecture
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-neutral-400 sm:text-base">
              A development-only surface for measured architecture and quality
              gates before product routes are introduced.
            </p>
          </div>
          <div className="w-fit rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1.5 text-xs font-medium text-cyan-200">
            Landing 2 · Backend baseline
          </div>
        </header>

        <BackendBaselineReview />

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
              className="rounded-2xl border border-neutral-800 bg-neutral-900/70 p-5"
            >
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold tracking-[0.16em] text-neutral-500 uppercase">
                  {label}
                </p>
                <Icon aria-hidden="true" className="size-5 text-cyan-300" />
              </div>
              <p className="mt-5 text-lg font-semibold text-neutral-100">
                {value}
              </p>
              <p className="mt-1 text-sm leading-6 text-neutral-400">
                {detail}
              </p>
            </article>
          ))}
        </section>

        <section className="grid flex-1 gap-5 pb-8 lg:grid-cols-[1.3fr_0.7fr]">
          <article className="rounded-2xl border border-neutral-800 bg-neutral-900/70 p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-xl bg-emerald-400/10 text-emerald-300">
                <CheckCircle2 aria-hidden="true" className="size-5" />
              </div>
              <div>
                <h2 className="font-semibold">Foundation gates</h2>
                <p className="text-sm text-neutral-500">
                  Automated before product work begins
                </p>
              </div>
            </div>
            <ul className="mt-6 grid gap-3 sm:grid-cols-2">
              {gateLabels.map((label) => (
                <li
                  key={label}
                  className="flex items-center gap-3 rounded-xl border border-neutral-800 bg-neutral-950/60 px-4 py-3 text-sm text-neutral-300"
                >
                  <span
                    aria-hidden="true"
                    className="size-2 rounded-full bg-emerald-300"
                  />
                  {label}
                </li>
              ))}
            </ul>
          </article>

          <article className="rounded-2xl border border-neutral-800 bg-neutral-900/70 p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-xl bg-amber-400/10 text-amber-300">
                <Gauge aria-hidden="true" className="size-5" />
              </div>
              <div>
                <h2 className="font-semibold">Fast Refresh probe</h2>
                <p className="text-sm text-neutral-500">
                  State must survive a source update
                </p>
              </div>
            </div>
            <label
              htmlFor="hmr-probe"
              className="mt-6 block text-sm font-medium text-neutral-300"
            >
              HMR state probe
            </label>
            <input
              id="hmr-probe"
              value={probe}
              onChange={(event) => setProbe(event.currentTarget.value)}
              placeholder="Type before a source edit"
              className="mt-2 h-11 w-full rounded-xl border border-neutral-700 bg-neutral-950 px-3 text-sm text-neutral-100 outline-none placeholder:text-neutral-600 focus-visible:border-cyan-300 focus-visible:ring-2 focus-visible:ring-cyan-300/20"
            />
            <p
              data-testid="foundation-marker"
              className="mt-4 font-mono text-[0.7rem] tracking-wide text-neutral-600"
            >
              {FOUNDATION_REVIEW_MARKER}
            </p>
          </article>
        </section>

        <footer className="border-t border-neutral-800 pt-5 text-xs leading-5 text-neutral-600">
          This review surface is available only in development and is excluded
          from the production module graph.
        </footer>
      </div>
    </main>
  )
}
