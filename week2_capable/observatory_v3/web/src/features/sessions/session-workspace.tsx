import { MessageSquareTextIcon } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import type { SessionInvestigation } from "@/data/session-investigation"
import { cn } from "@/lib/utils"

import { SessionCost } from "./session-cost"
import { SessionMap } from "./session-map"
import { SessionStory } from "./session-story"
import {
  iterationKey,
  projectSessionStory,
  type SessionSelection,
  type SessionView,
  type StoryObjectiveEpoch,
} from "./story-projection"

type WorkspaceParams = {
  view: SessionView
  turn: number | null
  iteration: number | null
  event: string | null
  goal: number | null
}

type SessionWorkspaceProps = {
  investigation: SessionInvestigation | null
  loading: boolean
  error: string | null
  initialParams: WorkspaceParams
  onParamsChange: (params: WorkspaceParams) => void
  onSelectionChange: (recordId: string | null) => void
}

const views: { id: SessionView; label: string; description: string }[] = [
  {
    id: "story",
    label: "Story",
    description:
      "is the complete chronological record. Expand only as deep as needed.",
  },
  {
    id: "map",
    label: "Map",
    description:
      "replays the Live spatial view with the iteration that produced each state.",
  },
  {
    id: "cost",
    label: "Cost",
    description:
      "attributes every amount and returns to the exact response that produced it.",
  },
]

/**
 * The recorded session workspace: run header, view switch, and the
 * story, map, and cost views over one investigation.
 */
function SessionWorkspace({
  investigation,
  loading,
  error,
  initialParams,
  onParamsChange,
  onSelectionChange,
}: SessionWorkspaceProps) {
  const [view, setView] = useState<SessionView>(initialParams.view)
  const [search, setSearch] = useState("")
  const [selection, setSelection] = useState<SessionSelection>({
    turn: initialParams.turn,
    iteration: initialParams.iteration,
    recordId: initialParams.event,
  })
  const [focusedGoalNumber, setFocusedGoalNumber] = useState<number | null>(
    initialParams.goal
  )
  const story = useMemo(
    () => (investigation === null ? null : projectSessionStory(investigation)),
    [investigation]
  )

  useEffect(() => {
    if (story === null || story.turns.length === 0) return
    const iterationExists =
      selection.turn !== null &&
      selection.iteration !== null &&
      story.byIteration.has(iterationKey(selection.turn, selection.iteration))
    if (iterationExists) {
      const selected = story.byIteration.get(
        iterationKey(selection.turn as number, selection.iteration as number)
      )
      if (selected !== undefined && focusedGoalNumber === null) {
        setFocusedGoalNumber(selected.objectiveEpoch)
      }
      return
    }
    const focusedGoal =
      story.objectiveEpochs.find(
        (epoch) => epoch.number === focusedGoalNumber
      ) ??
      story.objectiveEpochs.at(-1) ??
      null
    const first =
      focusedGoal?.firstIteration ?? story.turns[0]?.iterations[0] ?? null
    setFocusedGoalNumber(focusedGoal?.number ?? null)
    setSelection({
      turn: first?.turn ?? null,
      iteration: first?.number ?? null,
      recordId: null,
    })
  }, [focusedGoalNumber, selection.iteration, selection.turn, story])

  useEffect(() => {
    onParamsChange({
      view,
      turn: selection.turn,
      iteration: selection.iteration,
      event: selection.recordId,
      goal: focusedGoalNumber,
    })
  }, [focusedGoalNumber, onParamsChange, selection, view])

  useEffect(() => {
    onSelectionChange(selection.recordId)
  }, [onSelectionChange, selection.recordId])

  if (loading) {
    return <WorkspaceState text="Building the complete session story…" />
  }
  if (error !== null) {
    return <WorkspaceState error text={error} />
  }
  if (investigation === null || story === null) {
    return (
      <WorkspaceState text="Select a recorded session to read its complete run." />
    )
  }

  const activeView =
    views.find((candidate) => candidate.id === view) ?? views[0]
  const duration =
    investigation.run.duration_ms ?? sessionDuration(investigation)
  const iterationCount = story.turns.reduce(
    (total, turn) => total + turn.iterations.length,
    0
  )
  const focusedGoal =
    story.objectiveEpochs.find((epoch) => epoch.number === focusedGoalNumber) ??
    story.objectiveEpochs.at(-1) ??
    null
  const handleSelect = (next: SessionSelection): void => {
    if (next.turn !== null && next.iteration !== null) {
      const iteration = story.byIteration.get(
        iterationKey(next.turn, next.iteration)
      )
      if (iteration !== undefined) {
        setFocusedGoalNumber(iteration.objectiveEpoch)
      }
    }
    setSelection(next)
  }
  const handleGoalSelect = (epoch: StoryObjectiveEpoch): void => {
    setFocusedGoalNumber(epoch.number)
    setSelection({
      turn: epoch.firstIteration?.turn ?? epoch.record?.turn ?? null,
      iteration:
        epoch.firstIteration?.number ?? epoch.record?.iteration ?? null,
      recordId: null,
    })
  }

  return (
    <main className="min-h-0 flex-1">
      <section className="border-b border-line bg-[linear-gradient(180deg,var(--surface),var(--canvas))]">
        <div className="mx-auto grid w-[min(1180px,calc(100%-48px))] grid-cols-[minmax(360px,1fr)_auto] gap-7 pt-[15px] pb-[13px] max-[900px]:w-[calc(100%-28px)] max-[900px]:grid-cols-1">
          <div>
            <span className="text-[12px] font-[750] tracking-[0.11em] text-accent uppercase">
              {focusedGoal === null
                ? "Recorded session"
                : `Goal ${focusedGoal.number} of ${story.objectiveEpochs.length}`}
            </span>
            <h1 className="mt-[2px] mb-[4px] text-[clamp(22px,2.3vw,28px)] leading-[1.18] tracking-[-0.03em] text-content-primary">
              {sentenceCase(
                focusedGoal?.title ??
                  investigation.objective ??
                  investigation.run.label
              )}
            </h1>
            <p className="m-0 text-[14px] text-content-muted">
              {formatRunSubtitle(investigation)}
              {" · "}
              {captureLabel(investigation)}
            </p>
          </div>
          <dl className="m-0 grid grid-cols-[repeat(3,minmax(104px,1fr))] self-center overflow-hidden rounded-[13px] border border-line bg-surface">
            <div className="min-w-[110px] border-r border-line px-3.5 py-[9px]">
              <dt className="text-[12px] text-content-quiet">Duration</dt>
              <dd className="m-0 text-[16px] font-bold text-content-primary">
                {formatDuration(duration)}
              </dd>
            </div>
            <div className="min-w-[110px] border-r border-line px-3.5 py-[9px]">
              <dt className="text-[12px] text-content-quiet">Iterations</dt>
              <dd className="m-0 text-[16px] font-bold text-content-primary">
                {formatInteger(iterationCount)}
              </dd>
            </div>
            <div className="min-w-[110px] px-3.5 py-[9px]">
              <dt className="text-[12px] text-content-quiet">Total cost</dt>
              <dd className="m-0 text-[16px] font-bold text-warning">
                {usd(investigation.cost.total_usd)}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <div className="sticky top-(--header-height) z-[18] flex min-h-[58px] items-center gap-3.5 border-b border-line bg-canvas px-[max(24px,calc((100%-1180px)/2))] max-[900px]:flex-wrap max-[900px]:px-3.5 max-[900px]:py-2">
        <nav
          aria-label="Session views"
          className="flex rounded-[11px] border border-line bg-surface p-1"
        >
          {views.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={view === item.id ? "page" : undefined}
              className={cn(
                "min-w-[92px] cursor-pointer rounded-[9px] border border-transparent bg-transparent px-[13px] py-[7px] text-content-muted",
                view === item.id &&
                  "border-line-strong bg-surface-soft text-content-primary"
              )}
              onClick={() => {
                if (item.id === "story") {
                  setSelection((current) => ({ ...current, recordId: null }))
                }
                setView(item.id)
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <p className="m-0 text-content-muted max-[900px]:hidden">
          <strong className="text-content-primary">{activeView.label}</strong>{" "}
          {activeView.description}
        </p>
        <span className="flex-1" />
        {view === "story" ? (
          <input
            aria-label="Filter Story evidence"
            type="search"
            placeholder="Filter Story evidence"
            value={search}
            className="w-[260px] rounded-[9px] border border-line bg-surface px-3 py-[9px] text-content-primary outline-none placeholder:text-content-quiet max-[900px]:w-auto max-[900px]:flex-1"
            onChange={(event) => setSearch(event.target.value)}
          />
        ) : null}
      </div>

      <div className="min-h-0">
        {view === "story" ? (
          <SessionStory
            investigation={investigation}
            search={search}
            selection={selection}
            story={story}
            focusedGoalNumber={focusedGoalNumber}
            onOpenCost={() => setView("cost")}
            onGoalSelect={handleGoalSelect}
            onSelect={handleSelect}
          />
        ) : null}
        {view === "map" ? (
          <SessionMap
            investigation={investigation}
            selection={selection}
            story={story}
            focusedGoalNumber={focusedGoalNumber}
            onGoalSelect={handleGoalSelect}
            onOpenStory={() => setView("story")}
            onSelect={handleSelect}
          />
        ) : null}
        {view === "cost" ? (
          <SessionCost
            investigation={investigation}
            selection={selection}
            onOpenStory={() => setView("story")}
            onSelect={handleSelect}
          />
        ) : null}
      </div>
    </main>
  )
}

function WorkspaceState({
  error = false,
  text,
}: {
  error?: boolean
  text: string
}) {
  return (
    <main
      className={cn(
        "grid min-h-[calc(100vh-var(--header-height))] place-content-center justify-items-center gap-2 bg-canvas p-10 text-center text-content-muted",
        error && "text-[#ff8a82]"
      )}
    >
      <MessageSquareTextIcon aria-hidden="true" className="size-7" />
      <strong className="text-[18px] text-content-primary">
        {error ? "Session unavailable" : "Sessions"}
      </strong>
      <p className="m-0 max-w-[440px]">{text}</p>
    </main>
  )
}

function formatRunSubtitle(investigation: SessionInvestigation): string {
  const start =
    investigation.run.created_at ?? investigation.records[0]?.at ?? ""
  const end =
    investigation.run.ended_at ?? investigation.records.at(-1)?.at ?? ""
  const lifecycle = (
    investigation.run.lifecycle ??
    (investigation.run.success ? "completed" : "stopped")
  ).toLowerCase()
  const reason = investigation.run.stop_reason?.trim().toLowerCase() ?? ""
  const outcome =
    lifecycle === "stopped" && reason === "cooperative"
      ? "stopped cooperatively"
      : reason
        ? `${lifecycle}: ${reason}`
        : lifecycle
  return `${formatTimestamp(start)} · ${outcome} at ${formatTime(end)}`
}

function captureLabel(investigation: SessionInvestigation): string {
  if (investigation.capture_gaps.length > 0) {
    return [
      "Retained evidence with",
      investigation.capture_gaps.length,
      `explicit gap${investigation.capture_gaps.length === 1 ? "" : "s"}`,
    ].join(" ")
  }
  const status = investigation.run.capture_status?.trim()
  if (status) return `${capitalize(status)} evidence capture`
  return "Complete retained evidence"
}

function sessionDuration(investigation: SessionInvestigation): number | null {
  const stamps = investigation.records
    .map((record) => Date.parse(record.at))
    .filter(Number.isFinite)
  if (stamps.length < 2) return null
  return Math.max(...stamps) - Math.min(...stamps)
}

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value || "Time unavailable"
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  })
    .format(date)
    .replace(/, (?=\d{1,2}:)/, " at ")
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value || "time unavailable"
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date)
}

function formatDuration(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "Unavailable"
  if (value < 1_000) return `${Math.round(value)} ms`
  const seconds = value / 1_000
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.floor(seconds % 60)
  return `${minutes}m ${String(remainder).padStart(2, "0")}s`
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US").format(value)
}

function usd(value: number): string {
  return `$${value.toFixed(6)}`
}

function capitalize(value: string): string {
  return value ? `${value[0]?.toUpperCase()}${value.slice(1)}` : value
}

function sentenceCase(value: string): string {
  return value ? `${value[0]?.toUpperCase()}${value.slice(1)}` : value
}

export { SessionWorkspace, type SessionWorkspaceProps, type WorkspaceParams }
