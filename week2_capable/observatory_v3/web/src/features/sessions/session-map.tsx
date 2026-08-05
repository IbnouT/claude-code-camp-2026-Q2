import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PauseIcon,
  PlayIcon,
  SkipBackIcon,
  SkipForwardIcon,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { useLiveView } from "@/data/live-view"
import type { SessionInvestigation } from "@/data/session-investigation"
import { cn } from "@/lib/utils"

import { LiveMap } from "@/features/live/map/live-map"

import {
  recordIndexForIteration,
  type SessionSelection,
  type StoryIteration,
  type StoryModel,
  type StoryObjectiveEpoch,
} from "./story-projection"

type SessionMapProps = {
  investigation: SessionInvestigation
  selection: SessionSelection
  story: StoryModel
  focusedGoalNumber: number | null
  onGoalSelect: (epoch: StoryObjectiveEpoch) => void
  onOpenStory: () => void
  onSelect: (selection: SessionSelection) => void
}

const AUTOPLAY_MS = 900

/** The gateway sequence bound of the prefix ending at the record index. */
function throughSequenceForIndex(
  records: SessionInvestigation["records"],
  selectedIndex: number
): number {
  const throughIndex = selectedIndex < 0 ? records.length - 1 : selectedIndex
  let through = 0
  for (let index = 0; index <= throughIndex; index += 1) {
    const record = records[index]
    if (record.source === "gateway" && typeof record.sequence === "number") {
      through = Math.max(through, record.sequence)
    }
  }
  return through
}

function clock(value: string): string {
  const parsed = Date.parse(value)
  if (!Number.isFinite(parsed)) return "time unavailable"
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  }).format(parsed)
}

function usd(value: number): string {
  return `$${value.toFixed(6)}`
}

/**
 * The map replay: the Live spatial view driven by the selected
 * iteration's prefix, with the iteration rail steering it.
 */
function SessionMap({
  investigation,
  selection,
  story,
  focusedGoalNumber,
  onGoalSelect,
  onOpenStory,
  onSelect,
}: SessionMapProps) {
  const iterations = useMemo<StoryIteration[]>(
    () => story.turns.flatMap((turn) => turn.iterations),
    [story]
  )
  const currentIndex = iterations.findIndex(
    (item) =>
      item.turn === selection.turn && item.number === selection.iteration
  )
  const current = currentIndex < 0 ? null : iterations[currentIndex]
  const through = useMemo(() => {
    const recordIndex = recordIndexForIteration(
      investigation.records,
      selection.turn,
      selection.iteration
    )
    return throughSequenceForIndex(investigation.records, recordIndex)
  }, [investigation.records, selection.iteration, selection.turn])
  const view = useLiveView(
    through > 0 ? investigation.agent_session_id : undefined,
    through
  )
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [openGoals, setOpenGoals] = useState<Set<number>>(() => new Set())
  const previousEpochRef = useRef<number | null>(null)
  const selectedRowRef = useRef<HTMLButtonElement | null>(null)

  const goTo = (index: number) => {
    const target =
      iterations[Math.max(0, Math.min(iterations.length - 1, index))]
    if (target === undefined) return
    onSelect({ turn: target.turn, iteration: target.number, recordId: null })
  }

  useEffect(() => {
    if (!playing) return
    if (currentIndex >= iterations.length - 1) {
      setPlaying(false)
      return
    }
    const timer = window.setTimeout(() => {
      const target = iterations[currentIndex + 1]
      if (target !== undefined) {
        onSelect({
          turn: target.turn,
          iteration: target.number,
          recordId: null,
        })
      }
    }, AUTOPLAY_MS)
    return () => window.clearTimeout(timer)
  }, [currentIndex, iterations, onSelect, playing])

  useEffect(() => {
    const epoch = current?.objectiveEpoch ?? null
    // Groups start collapsed. Only crossing into another epoch opens it.
    if (
      epoch !== null &&
      previousEpochRef.current !== null &&
      epoch !== previousEpochRef.current
    ) {
      setOpenGoals((goals) => new Set(goals).add(epoch))
    }
    previousEpochRef.current = epoch
  }, [current?.objectiveEpoch])

  useEffect(() => {
    selectedRowRef.current?.scrollIntoView({ block: "nearest" })
  }, [current?.id])

  if (iterations.length === 0) {
    return (
      <div className="m-7 rounded-[12px] border border-dashed border-line-strong p-8 text-center text-content-muted">
        This session has no retained iteration to replay.
      </div>
    )
  }

  const focusedEpoch =
    story.objectiveEpochs.find((epoch) => epoch.number === focusedGoalNumber) ??
    null

  return (
    <section
      aria-label="Session map replay"
      className="grid h-[calc(100vh-225px)] min-h-[420px] grid-cols-[minmax(0,1fr)_410px] overflow-hidden bg-[#071017] max-[900px]:h-auto max-[900px]:grid-cols-1"
    >
      <div className="relative min-h-0 min-w-0 overflow-hidden bg-[#071017] bg-[image:radial-gradient(circle_at_52%_48%,rgb(38_74_98/25%),transparent_38%),linear-gradient(#0a151e_1px,transparent_1px),linear-gradient(90deg,#0a151e_1px,transparent_1px)] bg-[size:auto,40px_40px,40px_40px] max-[900px]:h-[58vh]">
        <div className="absolute inset-0 bottom-[76px] min-h-0 min-w-0">
          <LiveMap
            view={view.data?.view ?? null}
            reconnecting={false}
            selectedRoomId={selectedRoomId}
            onSelectRoom={setSelectedRoomId}
          />
        </div>
        <div className="absolute inset-x-0 bottom-0 z-[15] grid h-[76px] grid-cols-[auto_minmax(140px,1fr)_auto] items-center gap-4 border-t border-line bg-surface px-[18px]">
          <div className="flex gap-[7px]">
            <TransportButton
              label="First iteration"
              disabled={currentIndex <= 0}
              onClick={() => goTo(0)}
            >
              <SkipBackIcon aria-hidden="true" className="size-[17px]" />
            </TransportButton>
            <TransportButton
              label="Previous iteration"
              disabled={currentIndex <= 0}
              onClick={() => goTo(currentIndex - 1)}
            >
              <ChevronLeftIcon aria-hidden="true" className="size-[18px]" />
            </TransportButton>
            <TransportButton
              play
              label={playing ? "Pause replay" : "Play replay"}
              disabled={!playing && currentIndex >= iterations.length - 1}
              onClick={() => setPlaying((value) => !value)}
            >
              {playing ? (
                <PauseIcon aria-hidden="true" className="size-[17px]" />
              ) : (
                <PlayIcon aria-hidden="true" className="size-[17px]" />
              )}
            </TransportButton>
            <TransportButton
              label="Next iteration"
              disabled={currentIndex >= iterations.length - 1}
              onClick={() => goTo(currentIndex + 1)}
            >
              <ChevronRightIcon aria-hidden="true" className="size-[18px]" />
            </TransportButton>
            <TransportButton
              label="Last iteration"
              disabled={currentIndex >= iterations.length - 1}
              onClick={() => goTo(iterations.length - 1)}
            >
              <SkipForwardIcon aria-hidden="true" className="size-[17px]" />
            </TransportButton>
          </div>
          <input
            aria-label="Replay iteration"
            type="range"
            min={0}
            max={Math.max(0, iterations.length - 1)}
            value={Math.max(0, currentIndex)}
            disabled={iterations.length < 2}
            className="w-full accent-(--accent)"
            onChange={(event) => goTo(Number(event.target.value))}
          />
          <div className="text-right">
            <strong className="block">
              {current === null
                ? "No iteration"
                : `Turn ${current.turn} · Iteration ${current.number} (${currentIndex + 1} of ${iterations.length})`}
            </strong>
            <span className="text-[13px] text-content-muted">
              {current === null
                ? ""
                : `${clock(current.startedAt)}${current.roomTitle ? ` · ${current.roomTitle}` : ""}`}
            </span>
          </div>
        </div>
      </div>
      <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-l border-line bg-canvas max-[900px]:border-t max-[900px]:border-l-0">
        <header className="border-b border-line px-[18px] pt-[18px] pb-3.5">
          <span className="text-[12px] font-[750] tracking-[0.11em] text-accent uppercase">
            Map replay
          </span>
          <h2 className="mt-[2px] mb-[4px] text-[20px] font-bold">
            Follow the run in space
          </h2>
          <p className="m-0 text-content-muted">
            The selected iteration, current room, traveled path, and room detail
            move together.
          </p>
        </header>
        <div className="flex-1 overflow-auto p-3 max-[900px]:max-h-[360px]">
          {story.objectiveEpochs.map((epoch) => {
            const expanded = openGoals.has(epoch.number)
            const focused = epoch.number === focusedGoalNumber
            const epochIterations = iterations.filter(
              (iteration) => iteration.objectiveEpoch === epoch.number
            )
            return (
              <section
                key={epoch.id}
                aria-label={`Map goal ${epoch.number}: ${epoch.title}`}
              >
                <div
                  className={cn(
                    "my-2 grid w-full grid-cols-[minmax(0,1fr)_36px] border-l-[3px] border-l-warning bg-[rgb(239_196_108/8%)] text-content-primary",
                    focused && "border-l-accent bg-accent-soft"
                  )}
                >
                  <button
                    type="button"
                    aria-expanded={expanded}
                    aria-label={`Jump to Goal ${epoch.number}: ${epoch.title}`}
                    className="grid min-w-0 cursor-pointer grid-cols-[auto_minmax(0,1fr)] gap-x-[9px] gap-y-0.5 px-2.5 py-2 text-left text-content-primary [&:hover_strong]:text-accent"
                    onClick={() => {
                      onGoalSelect(epoch)
                      setOpenGoals((goals) => new Set(goals).add(epoch.number))
                    }}
                  >
                    <small className="self-center text-[11px] font-[750] tracking-[0.07em] text-warning uppercase">
                      Goal {epoch.number}
                    </small>
                    <span className="min-w-0">
                      <strong className="block truncate">{epoch.title}</strong>
                      <small className="block text-[11px] text-content-muted">
                        {epochIterations.length} iteration
                        {epochIterations.length === 1 ? "" : "s"} ·{" "}
                        {epoch.nudges.length} nudge
                        {epoch.nudges.length === 1 ? "" : "s"}
                      </small>
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-expanded={expanded}
                    aria-label={`Toggle Goal ${epoch.number} iterations`}
                    className="grid cursor-pointer place-items-center border-l border-[rgb(239_196_108/16%)] text-content-muted hover:text-accent"
                    onClick={() =>
                      setOpenGoals((goals) => {
                        const next = new Set(goals)
                        if (next.has(epoch.number)) next.delete(epoch.number)
                        else next.add(epoch.number)
                        return next
                      })
                    }
                  >
                    <ChevronRightIcon
                      aria-hidden="true"
                      className={cn("size-4", expanded && "rotate-90")}
                    />
                  </button>
                </div>
                {expanded
                  ? epochIterations.map((iteration) => {
                      const active = iteration.id === current?.id
                      return (
                        <button
                          key={iteration.id}
                          ref={active ? selectedRowRef : undefined}
                          type="button"
                          aria-current={active ? "step" : undefined}
                          className={cn(
                            "mb-2 grid w-full cursor-pointer grid-cols-[38px_1fr_auto] items-center gap-2.5 rounded-[11px] border border-line bg-surface p-3 text-left",
                            active && "border-[#39716f] bg-[#102020]"
                          )}
                          onClick={() =>
                            onSelect({
                              turn: iteration.turn,
                              iteration: iteration.number,
                              recordId: null,
                            })
                          }
                        >
                          <span className="text-[18px] font-extrabold text-accent">
                            {iteration.number}
                          </span>
                          <span className="min-w-0">
                            <strong className="block">{iteration.title}</strong>
                            <small className="block truncate text-[12px] text-content-muted">
                              {iteration.roomTitle ?? iteration.subtitle}
                            </small>
                          </span>
                          <b className="text-[12px] text-warning">
                            {usd(iteration.costUsd)}
                          </b>
                        </button>
                      )
                    })
                  : null}
              </section>
            )
          })}
        </div>
        <div className="mx-3 mt-1 mb-3 rounded-[12px] border border-line-strong bg-surface-raised p-4">
          {focusedEpoch === null ? null : (
            <span className="mb-1.5 block text-[11px] font-bold tracking-[0.04em] text-warning">
              Goal {focusedEpoch.number} · {focusedEpoch.title}
              {focusedEpoch.nudges.length > 0
                ? ` · ${focusedEpoch.nudges.length} nudge${focusedEpoch.nudges.length === 1 ? "" : "s"} active`
                : ""}
            </span>
          )}
          <h3 className="mt-0 mb-[7px] text-[17px] font-bold">
            {current === null
              ? "No iteration selected"
              : `Turn ${current.turn} · Iteration ${current.number}${current.roomTitle ? ` · ${current.roomTitle}` : ""}`}
          </h3>
          <p className="mt-0 mb-3 text-content-muted">
            {current === null
              ? ""
              : `${clock(current.startedAt)} · ${current.title}`}
          </p>
          <button
            type="button"
            className="w-full cursor-pointer rounded-[8px] border border-[#31515a] bg-[#102127] p-[9px] text-accent"
            onClick={() => {
              if (current !== null) {
                onSelect({
                  turn: current.turn,
                  iteration: current.number,
                  recordId:
                    current.responseIds[0] ?? current.records[0]?.id ?? null,
                })
              }
              onOpenStory()
            }}
          >
            Open the complete iteration story →
          </button>
        </div>
      </aside>
    </section>
  )
}

function TransportButton({
  label,
  disabled,
  onClick,
  play = false,
  children,
}: {
  label: string
  disabled: boolean
  onClick: () => void
  play?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      className={cn(
        "grid h-10 min-w-10 cursor-pointer place-items-center rounded-[9px] border border-line-strong bg-surface p-0 disabled:cursor-default disabled:opacity-[0.38]",
        play && "border-accent bg-accent text-[#06201f]"
      )}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

export { SessionMap, type SessionMapProps }
