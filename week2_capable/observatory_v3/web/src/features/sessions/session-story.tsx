import {
  ChevronRight,
  FileJson2,
  Flag,
  GitBranch,
  MessageSquareText,
  Wrench,
} from "lucide-react"
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
  type RefObject,
  type SetStateAction,
} from "react"

import type { SessionInvestigation } from "@/data/session-investigation"
import { cn } from "@/lib/utils"

import {
  activeNudgeForIteration,
  evidenceText,
  iterationKey,
  recordFields,
  segmentTurnsByNudges,
  type EvidenceFields,
  type SessionEvidenceRecord,
  type SessionSelection,
  type StoryIteration,
  type StoryModel,
  type StoryObjectiveEpoch,
  type StoryStep,
  type StoryToolCycle,
  type StoryTurn,
} from "./story-projection"

type SessionStoryProps = {
  investigation: SessionInvestigation
  story: StoryModel
  selection: SessionSelection
  focusedGoalNumber: number | null
  search: string
  onGoalSelect: (epoch: StoryObjectiveEpoch) => void
  onSelect: (selection: SessionSelection) => void
  onOpenCost: () => void
}

const eyebrowClass =
  "text-[12px] font-[750] tracking-[0.11em] text-accent uppercase"

const contentCardClass =
  "rounded-[11px] border border-line bg-surface-raised px-[15px] py-[13px] whitespace-pre-wrap text-content-primary [overflow-wrap:anywhere]"

const terminalPreClass =
  "m-0 max-h-[440px] overflow-auto rounded-[10px] border border-[#1b2933] bg-(--terminal-canvas) px-[15px] py-[14px] font-mono text-[13px] leading-[1.65] whitespace-pre-wrap text-[#d7e3e8] [overflow-wrap:anywhere]"

const detailPreClass =
  "mt-[13px] mb-0 max-h-[480px] overflow-auto rounded-[8px] bg-canvas p-[13px] font-mono text-[12px] leading-[1.55] whitespace-pre-wrap text-content-muted"

const recordStackClass = "grid gap-[10px] pt-[13px]"

const detailClass = "mt-[9px] rounded-[10px] border border-line bg-surface"

const detailSummaryClass =
  "flex min-h-[42px] cursor-pointer list-none items-center gap-[7px] px-[12px] font-[650] text-accent after:ml-auto after:content-['›'] [&::-webkit-details-marker]:hidden [[open]>&]:after:rotate-90"

const availabilityClass =
  "rounded-[9px] border border-line bg-surface-raised px-[14px] py-[12px] text-[12px] leading-[1.5] text-content-muted"

const rawRecordClass = "rounded-[9px] border border-line bg-surface p-[12px]"

function SessionStory({
  investigation,
  story,
  selection,
  focusedGoalNumber,
  search,
  onGoalSelect,
  onSelect,
  onOpenCost,
}: SessionStoryProps) {
  const firstIteration = story.turns[0]?.iterations[0]?.number ?? null
  const firstTurn = story.turns[0]?.iterations[0]?.turn ?? null
  const [openIterations, setOpenIterations] = useState<Set<string>>(
    () =>
      new Set(
        selection.iteration === null || selection.turn === null
          ? firstIteration === null || firstTurn === null
            ? []
            : [iterationKey(firstTurn, firstIteration)]
          : [iterationKey(selection.turn, selection.iteration)]
      )
  )
  const selectedIteration =
    selection.turn !== null && selection.iteration !== null
      ? story.byIteration.get(iterationKey(selection.turn, selection.iteration))
      : undefined
  const selectedNudge =
    selectedIteration === undefined
      ? null
      : activeNudgeForIteration(
          story.objectiveEpochs.find(
            (epoch) => epoch.number === selectedIteration.objectiveEpoch
          ),
          selectedIteration
        )
  const [openGoals, setOpenGoals] = useState<Set<number>>(
    () =>
      new Set(
        selection.recordId !== null && selectedIteration !== undefined
          ? [selectedIteration.objectiveEpoch]
          : []
      )
  )
  const [openNudges, setOpenNudges] = useState<Set<string>>(
    () =>
      new Set(
        selection.recordId !== null && selectedNudge !== null
          ? [selectedNudge.record.id]
          : []
      )
  )
  const selectedRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (selection.turn === null || selection.iteration === null) return
    const key = iterationKey(selection.turn, selection.iteration)
    setOpenIterations((current) => {
      if (current.has(key)) return current
      return new Set([...current, key])
    })
  }, [selection.iteration, selection.turn])

  useEffect(() => {
    if (selection.recordId === null) return
    if (typeof selectedRef.current?.scrollIntoView !== "function") return
    selectedRef.current.scrollIntoView({
      behavior: "smooth",
      block: "center",
    })
  }, [selection.iteration, selection.recordId, selection.turn])

  const normalizedSearch = search.trim().toLowerCase()
  const turns = useMemo(() => {
    if (!normalizedSearch) return story.turns
    return story.turns
      .map((turn) => ({
        ...turn,
        iterations: turn.iterations.filter((iteration) =>
          [
            iteration.title,
            iteration.subtitle,
            iteration.roomTitle,
            ...iteration.records.map(
              (record) => `${record.label} ${record.preview}`
            ),
          ]
            .join(" ")
            .toLowerCase()
            .includes(normalizedSearch)
        ),
      }))
      .filter((turn) => turn.iterations.length > 0)
  }, [normalizedSearch, story.turns])
  const chapters = useMemo(
    () =>
      story.objectiveEpochs
        .map((epoch) => {
          const chapterMatches =
            normalizedSearch &&
            [epoch.title, ...epoch.nudges.map((nudge) => nudge.instruction)]
              .join(" ")
              .toLowerCase()
              .includes(normalizedSearch)
          const sourceTurns = chapterMatches ? story.turns : turns
          return {
            epoch,
            turns: sourceTurns
              .map((turn): StoryTurn => {
                const iterations = turn.iterations.filter(
                  (iteration) => iteration.objectiveEpoch === epoch.number
                )
                return {
                  ...turn,
                  startedAt: iterations[0]?.startedAt ?? turn.startedAt,
                  endedAt: iterations.at(-1)?.endedAt ?? turn.endedAt,
                  durationMs: iterations.reduce(
                    (total, iteration) => total + iteration.durationMs,
                    0
                  ),
                  costUsd: iterations.reduce(
                    (total, iteration) => total + iteration.costUsd,
                    0
                  ),
                  iterations,
                }
              })
              .filter((turn) => turn.iterations.length > 0),
          }
        })
        .filter((chapter) => !normalizedSearch || chapter.turns.length > 0),
    [normalizedSearch, story.objectiveEpochs, story.turns, turns]
  )
  const matchingIterations = chapters.reduce(
    (total, chapter) =>
      total +
      chapter.turns.reduce(
        (chapterTotal, turn) => chapterTotal + turn.iterations.length,
        0
      ),
    0
  )

  const startAt =
    investigation.run.created_at ??
    story.startRecords[0]?.at ??
    story.turns[0]?.startedAt ??
    ""
  return (
    <section
      aria-label="Complete session story"
      className="mx-auto w-[min(1060px,calc(100%-48px))] pt-[30px] pb-[100px] max-[900px]:w-[calc(100%-28px)]"
    >
      <div className="mb-[26px] grid grid-cols-[1fr_320px] gap-[18px] max-[900px]:grid-cols-1">
        <article className="rounded-[15px] border border-line bg-surface px-[22px] py-[20px] shadow-popover">
          <span className={eyebrowClass}>
            Session start · {formatClock(startAt, true)}
          </span>
          <h2 className="mt-[4px] mb-[9px] text-[20px] font-bold">
            {story.objectiveEpochs.length} objective
            {story.objectiveEpochs.length === 1 ? "" : "s"} shaped this session
          </h2>
          <p className="m-0 text-content-muted">
            {sentenceCase(
              story.objectiveEpochs[0]?.title ??
                investigation.objective ??
                "No initial objective was retained."
            )}{" "}
            The run used {investigation.model ?? "an unlabelled model"} with{" "}
            {toolCountAtStart(story.startRecords)} available tools.
          </p>
        </article>
        <button
          className="rounded-[15px] border border-line bg-surface px-[19px] py-[17px] text-left text-content-primary shadow-popover"
          type="button"
          onClick={onOpenCost}
        >
          <span className="text-content-muted">Model activity</span>
          <strong className="block text-[25px] text-warning">
            {responseCount(investigation)} responses
          </strong>
          <span className="text-content-muted">
            {formatInteger(totalTokens(investigation))} retained tokens
          </span>
          <small className="mt-[8px] block text-[13px] text-accent">
            Explore the {usd(investigation.cost.total_usd)} cost →
          </small>
        </button>
      </div>

      {normalizedSearch ? (
        <output className="mx-auto mb-[12px] block w-[min(1180px,calc(100%-48px))] text-[13px] text-content-muted">
          {matchingIterations} matching iteration
          {matchingIterations === 1 ? "" : "s"} for “{search}”. Matching goals
          and nudges are expanded.
        </output>
      ) : null}

      {normalizedSearch && matchingIterations === 0 ? (
        <div className="rounded-[12px] border border-dashed border-line-strong p-[30px] text-center text-content-muted">
          No retained Story evidence contains “{search}”. The complete recording
          remains available when the filter is cleared.
        </div>
      ) : null}

      {chapters.map(({ epoch, turns: chapterTurns }) => {
        const expanded = normalizedSearch
          ? chapterTurns.length > 0
          : openGoals.has(epoch.number)
        const current = epoch.number === story.objectiveEpochs.at(-1)?.number
        const focused = epoch.number === focusedGoalNumber
        const segments = segmentTurnsByNudges(epoch, chapterTurns)
        const totalIterationCount = story.turns.reduce(
          (total, turn) =>
            total +
            turn.iterations.filter(
              (iteration) => iteration.objectiveEpoch === epoch.number
            ).length,
          0
        )
        return (
          <section
            aria-label={`Goal ${epoch.number}: ${sentenceCase(epoch.title)}`}
            className={cn(
              "mb-[22px] rounded-[15px] border border-line bg-surface px-[20px] pb-[22px] shadow-popover",
              current && "border-[#39716f]",
              focused &&
                "border-accent shadow-[0_0_0_1px_rgb(104_225_220/14%),var(--elevation-popover)]",
              !expanded && "pb-0"
            )}
            key={epoch.id}
          >
            <GoalChapterHeader
              current={current}
              epoch={epoch}
              expanded={expanded}
              focused={focused}
              iterationCount={totalIterationCount}
              onFocus={() => {
                onGoalSelect(epoch)
                setOpenGoals((existing) => {
                  const next = new Set(existing)
                  if (next.has(epoch.number)) next.delete(epoch.number)
                  else next.add(epoch.number)
                  return next
                })
              }}
              onToggle={() =>
                setOpenGoals((existing) => {
                  const next = new Set(existing)
                  if (next.has(epoch.number)) next.delete(epoch.number)
                  else next.add(epoch.number)
                  return next
                })
              }
            />
            {expanded && chapterTurns.length === 0 ? (
              <p className="mt-[20px] mb-0 rounded-[10px] border border-dashed border-line-strong p-[13px] text-content-muted">
                No retained iteration followed this applied goal.
              </p>
            ) : null}
            {expanded ? (
              <>
                <StoryTurns
                  openIterations={openIterations}
                  selection={selection}
                  selectedRef={selectedRef}
                  turns={segments.beforeFirstNudge}
                  onOpenIterationsChange={setOpenIterations}
                  onSelect={onSelect}
                />
                {segments.nudges.map(({ message, turns: nudgeTurns }) => {
                  const nudgeExpanded = normalizedSearch
                    ? nudgeTurns.length > 0
                    : openNudges.has(message.record.id)
                  const nudgeIterationCount = nudgeTurns.reduce(
                    (total, turn) => total + turn.iterations.length,
                    0
                  )
                  return (
                    <section
                      aria-label={`Nudge: ${sentenceCase(message.instruction)}`}
                      className="mt-[20px] ml-[36px] overflow-hidden rounded-[12px] border border-line-strong bg-surface max-[900px]:ml-0"
                      key={message.record.id}
                    >
                      <button
                        aria-expanded={nudgeExpanded}
                        className="grid w-full grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-[10px] border-0 bg-surface-raised px-[13px] py-[11px] text-left text-content-primary hover:bg-surface-soft max-[900px]:grid-cols-[34px_minmax(0,1fr)]"
                        type="button"
                        onClick={() => {
                          setOpenNudges((existing) => {
                            const next = new Set(existing)
                            if (next.has(message.record.id)) {
                              next.delete(message.record.id)
                            } else {
                              next.add(message.record.id)
                            }
                            return next
                          })
                          onSelect({
                            turn: message.record.turn,
                            iteration: message.record.iteration,
                            recordId: message.record.id,
                          })
                        }}
                      >
                        <span
                          aria-hidden="true"
                          className="grid h-[30px] w-[30px] place-items-center rounded-[9px] bg-accent-soft text-accent"
                        >
                          <MessageSquareText size={16} />
                        </span>
                        <span>
                          <small className="block text-[12px] text-content-muted">
                            Nudge · applied{" "}
                            {formatClock(message.record.at, true)}
                          </small>
                          <strong className="block">
                            {sentenceCase(message.instruction)}
                          </strong>
                        </span>
                        <span className="inline-flex items-center gap-[7px] text-[12px] whitespace-nowrap text-content-muted max-[900px]:col-start-2">
                          {nudgeIterationCount} iteration
                          {nudgeIterationCount === 1 ? "" : "s"}
                          <ChevronRight
                            aria-hidden="true"
                            className={cn(nudgeExpanded && "rotate-90")}
                            size={16}
                          />
                        </span>
                      </button>
                      {nudgeExpanded ? (
                        <StoryTurns
                          inNudge
                          openIterations={openIterations}
                          selection={selection}
                          selectedRef={selectedRef}
                          turns={nudgeTurns}
                          onOpenIterationsChange={setOpenIterations}
                          onSelect={onSelect}
                        />
                      ) : null}
                    </section>
                  )
                })}
              </>
            ) : null}
          </section>
        )
      })}

      <StoryTerminal
        captureGaps={investigation.capture_gaps}
        investigation={investigation}
        records={story.terminalRecords}
      />
    </section>
  )
}

function StoryTurns({
  inNudge = false,
  openIterations,
  selection,
  selectedRef,
  turns,
  onOpenIterationsChange,
  onSelect,
}: {
  inNudge?: boolean
  openIterations: Set<string>
  selection: SessionSelection
  selectedRef: RefObject<HTMLElement | null>
  turns: StoryTurn[]
  onOpenIterationsChange: Dispatch<SetStateAction<Set<string>>>
  onSelect: (selection: SessionSelection) => void
}) {
  return turns.map((turn) => (
    <section
      className={cn(
        "relative mt-[22px] pl-[36px] before:absolute before:top-[20px] before:-bottom-[25px] before:left-[12px] before:w-[2px] before:bg-[linear-gradient(var(--line-strong),var(--line))] before:content-['']",
        inNudge && "mx-[14px] mt-[16px]"
      )}
      key={`${turn.number}:${turn.iterations[0]?.id ?? "empty"}`}
    >
      <header className="relative mb-[12px] flex items-center gap-[12px] before:absolute before:-left-[30px] before:h-[14px] before:w-[14px] before:rounded-full before:border-[3px] before:border-canvas before:bg-accent before:shadow-[0_0_0_1px_#2c6968] before:content-['']">
        <h3 className="m-0 text-[18px] font-bold">Turn {turn.number}</h3>
        <span className="text-[13px] text-content-muted">
          {formatClock(turn.startedAt, true)} to{" "}
          {formatClock(turn.endedAt, true)}
          {" · "}
          {turn.iterations.length} iteration
          {turn.iterations.length === 1 ? "" : "s"}
        </span>
        <b className="ml-auto font-bold text-warning">{usd(turn.costUsd)}</b>
      </header>
      {turn.iterations.map((iteration) => (
        <StoryIterationCard
          iteration={iteration}
          key={iteration.id}
          open={openIterations.has(
            iterationKey(iteration.turn, iteration.number)
          )}
          selected={
            selection.turn === iteration.turn &&
            selection.iteration === iteration.number
          }
          selectedRecordId={selection.recordId}
          selectedRef={
            selection.turn === iteration.turn &&
            selection.iteration === iteration.number
              ? selectedRef
              : undefined
          }
          onSelect={onSelect}
          onToggle={() => {
            const key = iterationKey(iteration.turn, iteration.number)
            onOpenIterationsChange((current) => {
              const next = new Set(current)
              if (next.has(key)) next.delete(key)
              else next.add(key)
              return next
            })
            onSelect({
              turn: iteration.turn,
              iteration: iteration.number,
              recordId: null,
            })
          }}
        />
      ))}
    </section>
  ))
}

function GoalChapterHeader({
  current,
  epoch,
  expanded,
  focused,
  iterationCount,
  onFocus,
  onToggle,
}: {
  current: boolean
  epoch: StoryObjectiveEpoch
  expanded: boolean
  focused: boolean
  iterationCount: number
  onFocus: () => void
  onToggle: () => void
}) {
  return (
    <header
      className={cn(
        "-mx-[20px] grid grid-cols-[minmax(0,1fr)_auto] items-center gap-[13px] bg-surface-raised px-[20px] py-[18px] max-[900px]:grid-cols-[minmax(0,1fr)]",
        expanded ? "rounded-t-[15px]" : "rounded-[15px]"
      )}
    >
      <button
        aria-expanded={expanded}
        aria-label={`Select Goal ${epoch.number}: ${sentenceCase(epoch.title)}`}
        className="group grid min-w-0 grid-cols-[42px_minmax(0,1fr)] items-center gap-[13px] border-0 bg-transparent p-0 text-left text-content-primary"
        type="button"
        onClick={onFocus}
      >
        <span
          aria-hidden="true"
          className={cn(
            "grid h-[40px] w-[40px] place-items-center rounded-[11px]",
            current
              ? "bg-accent-soft text-accent"
              : "bg-[rgb(239_196_108/12%)] text-warning"
          )}
        >
          <Flag size={18} />
        </span>
        <span>
          <span className={eyebrowClass}>
            Goal {epoch.number}
            {focused ? " · selected" : current ? " · latest" : ""}
          </span>
          <strong className="mt-[2px] mb-[3px] block text-[19px] group-hover:text-accent">
            {sentenceCase(epoch.title)}
          </strong>
          <small className="block text-[13px] text-content-muted">
            Applied {formatClock(epoch.startedAt, true)}
            {" · "}
            {epoch.nudges.length} nudge{epoch.nudges.length === 1 ? "" : "s"}
            {" · "}
            {iterationCount} iteration{iterationCount === 1 ? "" : "s"}
          </small>
        </span>
      </button>
      <div className="flex items-center gap-[7px] max-[900px]:flex-wrap">
        <button
          aria-expanded={expanded}
          aria-label={`${expanded ? "Collapse" : "Expand"} Goal ${epoch.number}`}
          className="inline-flex min-h-[34px] items-center gap-[5px] rounded-[8px] border border-line-strong bg-surface-raised px-[10px] text-[12px] text-content-muted hover:border-[#39716f] hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-50"
          type="button"
          onClick={onToggle}
        >
          <ChevronRight
            aria-hidden="true"
            className={cn(expanded && "rotate-90")}
            size={16}
          />
          {expanded ? "Collapse" : "Expand"}
        </button>
      </div>
    </header>
  )
}

function StoryIterationCard({
  iteration,
  open,
  selected,
  selectedRecordId,
  selectedRef,
  onSelect,
  onToggle,
}: {
  iteration: StoryIteration
  open: boolean
  selected: boolean
  selectedRecordId: string | null
  selectedRef?: RefObject<HTMLElement | null>
  onSelect: (selection: SessionSelection) => void
  onToggle: () => void
}) {
  return (
    <article
      className={cn(
        "mb-[12px] overflow-clip rounded-[14px] border border-line bg-surface transition-[border-color,box-shadow] duration-[160ms]",
        selected &&
          "border-[#39716f] shadow-[0_0_0_1px_rgb(104_225_220/14%),var(--elevation-popover)]"
      )}
      ref={selectedRef}
    >
      <button
        aria-expanded={open}
        className="grid w-full grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-[13px] border-0 bg-transparent px-[17px] py-[15px] text-left text-content-primary hover:bg-surface-raised max-[900px]:grid-cols-[40px_1fr]"
        type="button"
        onClick={onToggle}
      >
        <span className="grid h-[38px] w-[38px] place-items-center rounded-[10px] bg-accent-soft font-extrabold text-accent">
          {iteration.number}
        </span>
        <span className="min-w-0">
          <strong className="block overflow-hidden text-[16px] text-ellipsis whitespace-nowrap">
            {iteration.title}
          </strong>
          <span className="block overflow-hidden text-[13px] text-ellipsis whitespace-nowrap text-content-muted">
            {iteration.subtitle}
          </span>
        </span>
        <span className="flex items-center gap-[14px] text-[13px] whitespace-nowrap text-content-muted max-[900px]:col-start-2 max-[900px]:flex-wrap">
          <time dateTime={iteration.startedAt}>
            {formatClock(iteration.startedAt, true)}
          </time>
          <span>{formatDuration(iteration.durationMs)}</span>
          <span>
            {iteration.toolCalls} tool call
            {iteration.toolCalls === 1 ? "" : "s"}
          </span>
          <b className="font-bold text-warning">{usd(iteration.costUsd)}</b>
          <ChevronRight
            className={cn(
              "text-content-quiet transition-transform duration-[160ms]",
              open && "rotate-90"
            )}
            size={18}
          />
        </span>
      </button>
      {open ? (
        <div className="border-t border-line bg-surface-raised pt-[4px] pr-[18px] pb-[22px] pl-[70px] max-[900px]:pl-[18px]">
          {iteration.steps.map((step, index) => (
            <StoryStepView
              iteration={iteration.number}
              key={stepKey(step, index)}
              selectedRecordId={selectedRecordId}
              step={step}
              turn={iteration.turn}
              onSelect={onSelect}
            />
          ))}
          {iteration.captureGaps.length > 0 ? (
            <CaptureGaps gaps={iteration.captureGaps} />
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

function StoryStepView({
  iteration,
  turn,
  selectedRecordId,
  step,
  onSelect,
}: {
  iteration: number
  turn: number
  selectedRecordId: string | null
  step: StoryStep
  onSelect: (selection: SessionSelection) => void
}) {
  if (step.type === "tool") {
    return (
      <ToolCycle
        cycle={step.cycle}
        iteration={iteration}
        selectedRecordId={selectedRecordId}
        turn={turn}
        onSelect={onSelect}
      />
    )
  }
  const record = step.record
  if (record.kind === "prompt") {
    return (
      <CausalStep
        dot="input"
        record={record}
        selected={selectedRecordId === record.id}
        subtitle={promptSummary(record)}
        title="Input available to the model"
        onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
      >
        <MessagePreview record={record} />
        <StoryDetail summary="Exact model request, system prompt, messages, and tool schemas">
          <MessageBody record={record} />
          <ToolSurface record={record} />
          <Provenance record={record} />
        </StoryDetail>
      </CausalStep>
    )
  }
  if (record.kind === "plan" || record.kind === "reasoning") {
    return (
      <CausalStep
        dot="plan"
        record={record}
        selected={selectedRecordId === record.id}
        subtitle="retained text"
        title={
          record.kind === "reasoning" ? "Retained reasoning" : "Agent plan"
        }
        onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
      >
        <div className={contentCardClass}>{evidenceText(record)}</div>
        <EvidenceDetail record={record} />
      </CausalStep>
    )
  }
  if (record.kind === "response") {
    return (
      <CausalStep
        dot="model"
        record={record}
        selected={selectedRecordId === record.id}
        subtitle={responseSubtitle(record)}
        title="Model response"
        onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
      >
        <div className={contentCardClass}>{responseText(record)}</div>
        <ResponseEconomics record={record} />
        <EvidenceDetail record={record} />
      </CausalStep>
    )
  }
  if (record.kind === "retry" || record.kind === "limit_reached") {
    return (
      <CausalStep
        dot="signal"
        record={record}
        selected={selectedRecordId === record.id}
        subtitle="Execution signal"
        title={record.label}
        onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
      >
        <div className={cn(availabilityClass, "border-[#665530] bg-[#1b1911]")}>
          {evidenceText(record)}
        </div>
        <EvidenceDetail record={record} />
      </CausalStep>
    )
  }
  return (
    <CausalStep
      dot="input"
      record={record}
      selected={selectedRecordId === record.id}
      subtitle={`${record.source} · ${record.form}`}
      title={record.label}
      onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
    >
      <div className={contentCardClass}>{evidenceText(record)}</div>
      <EvidenceDetail record={record} />
    </CausalStep>
  )
}

function ToolCycle({
  cycle,
  iteration,
  turn,
  selectedRecordId,
  onSelect,
}: {
  cycle: StoryToolCycle
  iteration: number
  turn: number
  selectedRecordId: string | null
  onSelect: (selection: SessionSelection) => void
}) {
  const originalMudText = toolOriginalText(cycle)
  const parserText = cycle.parserInputs
    .map(evidenceText)
    .filter(Boolean)
    .join("\n\n")
  const deliveredText = toolDeliveredText(cycle)
  const stages = cycle.agentResult?.fields?.stages
  const hasTransformStages = typeof stages === "object" && stages !== null
  return (
    <>
      <CausalStep
        dot="tool"
        record={cycle.call}
        selected={selectedRecordId === cycle.call.id}
        subtitle="agent → gateway → Telnet → MUD"
        title={`Tool call · ${toolName(cycle.call)}`}
        onSelect={() =>
          onSelect({
            turn,
            iteration,
            recordId: cycle.call.id,
          })
        }
      >
        <div className={cn(contentCardClass, "font-mono")}>
          {toolName(cycle.call)}(
          {formatJson(recordFields(cycle.call).args ?? {})})
        </div>
        <StoryDetail summary="Transport path and timing">
          <TransportPath cycle={cycle} />
          {cycle.wires.map((wire) => (
            <StoryDetail
              key={wire.id}
              summary={
                <>
                  {wire.label} · {numberField(recordFields(wire).bytes)} bytes ·{" "}
                  {formatClock(wire.at, true)}
                </>
              }
            >
              <WireEvidencePlaceholder />
              <Provenance record={wire} />
            </StoryDetail>
          ))}
          <EvidenceDetail record={cycle.call} />
        </StoryDetail>
      </CausalStep>

      <CausalStep
        dot="world"
        record={cycle.wireTexts[0] ?? cycle.agentResult ?? cycle.call}
        selected={cycle.wireTexts.some(
          (record) => record.id === selectedRecordId
        )}
        subtitle={
          cycle.wireTexts.length > 0
            ? "original decoded text before parsing"
            : "best retained original text"
        }
        title="MUD response"
        onSelect={() =>
          onSelect({
            turn,
            iteration,
            recordId:
              cycle.wireTexts[0]?.id ?? cycle.agentResult?.id ?? cycle.call.id,
          })
        }
      >
        {originalMudText ? (
          <pre className={terminalPreClass}>{originalMudText}</pre>
        ) : (
          <div className={availabilityClass}>
            Original MUD text was not retained for this tool cycle.
          </div>
        )}
        {cycle.wireTexts.map((record) => (
          <EvidenceDetail key={record.id} record={record} />
        ))}
      </CausalStep>

      <CausalStep
        dot="world"
        record={cycle.parserInputs[0] ?? cycle.observations[0] ?? cycle.call}
        selected={[
          ...cycle.parserInputs,
          ...cycle.observations,
          ...cycle.stateChanges,
        ].some((record) => record.id === selectedRecordId)}
        subtitle="before and after remain connected"
        title="Transformation and structured observation"
        onSelect={() =>
          onSelect({
            turn,
            iteration,
            recordId:
              cycle.parserInputs[0]?.id ??
              cycle.observations[0]?.id ??
              cycle.call.id,
          })
        }
      >
        <div className="grid grid-cols-[minmax(0,1fr)_38px_minmax(0,1fr)] items-stretch gap-[10px] max-[900px]:grid-cols-1">
          <div className="min-w-0 rounded-[10px] border border-line bg-surface p-[13px]">
            <h4 className="mb-[8px] text-[13px] font-bold">Parser input</h4>
            {parserText ? (
              <pre className="m-0 max-h-[360px] overflow-auto font-mono text-[12px] leading-[1.55] whitespace-pre-wrap text-content-muted">
                {parserText}
              </pre>
            ) : (
              <Availability gap="mud_text_transform_stages_not_retained" />
            )}
          </div>
          <span className="grid place-items-center text-[22px] text-accent max-[900px]:rotate-90">
            →
          </span>
          <div className="min-w-0 rounded-[10px] border border-line bg-surface p-[13px]">
            <h4 className="mb-[8px] text-[13px] font-bold">
              Typed observations and state
            </h4>
            {cycle.observations.length + cycle.stateChanges.length > 0 ? (
              <ObservationList
                records={[...cycle.observations, ...cycle.stateChanges]}
              />
            ) : (
              <Availability gap="parsed_observations_not_retained" />
            )}
          </div>
        </div>
        <StoryDetail
          bodyClassName={recordStackClass}
          summary="Open each parsed record and state change"
        >
          {[
            ...cycle.parserInputs,
            ...cycle.observations,
            ...cycle.stateChanges,
          ].map((record) => (
            <article className={rawRecordClass} key={record.id}>
              <header className="mb-[8px] flex justify-between gap-[12px]">
                <strong>{record.label}</strong>
                <time
                  className="font-mono text-[11px] text-content-muted"
                  dateTime={record.at}
                >
                  {formatClock(record.at, true)}
                </time>
              </header>
              <pre className={detailPreClass}>
                {JSON.stringify(record.fields, null, 2)}
              </pre>
              <Provenance record={record} />
            </article>
          ))}
        </StoryDetail>
      </CausalStep>

      <CausalStep
        dot="tool"
        record={cycle.agentResult ?? cycle.gatewayResults[0] ?? cycle.call}
        selected={[
          ...cycle.gatewayResults,
          ...(cycle.agentResult ? [cycle.agentResult] : []),
        ].some((record) => record.id === selectedRecordId)}
        subtitle="exact content retained in the agent log"
        title="Result delivered upstream"
        onSelect={() =>
          onSelect({
            turn,
            iteration,
            recordId:
              cycle.agentResult?.id ??
              cycle.gatewayResults[0]?.id ??
              cycle.call.id,
          })
        }
      >
        {deliveredText ? (
          <pre className={terminalPreClass}>{deliveredText}</pre>
        ) : (
          <Availability gap="tool_result_transform_stages_not_retained" />
        )}
        {hasTransformStages ? (
          <TransformationStages stages={stages as EvidenceFields} />
        ) : null}
        {cycle.agentResult ? (
          <EvidenceDetail record={cycle.agentResult} />
        ) : null}
      </CausalStep>
    </>
  )
}

const dotFill: Record<string, string> = {
  input: "bg-[#73b9ff]",
  plan: "bg-[#b9a8ff]",
  model: "bg-warning",
  tool: "bg-accent",
  world: "bg-[#8cdda7]",
  signal: "bg-[#ff8a82]",
}

function CausalStep({
  children,
  dot,
  record,
  selected,
  subtitle,
  title,
  onSelect,
}: {
  children: ReactNode
  dot: "input" | "plan" | "model" | "tool" | "world" | "signal"
  record: SessionEvidenceRecord
  selected: boolean
  subtitle: string
  title: string
  onSelect: () => void
}) {
  return (
    <section
      className={cn(
        "relative pt-[16px] pl-[32px] before:absolute before:top-0 before:-bottom-[16px] before:left-[8px] before:w-px before:bg-line-strong before:content-[''] last-of-type:before:bottom-[24px]",
        selected &&
          "-mx-[10px] mt-[8px] rounded-[11px] border border-[#39716f] bg-accent-soft pt-[14px] pr-[10px] pb-[12px] pl-[42px] before:left-[18px]"
      )}
      data-record-id={record.id}
    >
      <button
        aria-label={`Select ${title}`}
        className={cn(
          "absolute top-[22px] left-[2px] z-[2] h-[13px] w-[13px] rounded-full border-[3px] border-surface-raised p-0 shadow-[0_0_0_1px_var(--line-strong)]",
          dotFill[dot],
          selected && "top-[20px] left-[12px]"
        )}
        type="button"
        onClick={onSelect}
      />
      <header className="mb-[7px] flex items-baseline gap-[10px]">
        <strong className="text-[15px]">{title}</strong>
        <span className="text-[13px] text-content-muted">{subtitle}</span>
        <time
          className="ml-auto text-[13px] text-content-quiet"
          dateTime={record.at}
        >
          {formatClock(record.at, true)}
        </time>
      </header>
      {children}
    </section>
  )
}

function StoryDetail({
  bodyClassName,
  children,
  summary,
}: {
  bodyClassName?: string
  children: ReactNode
  summary: ReactNode
}) {
  return (
    <details className={detailClass}>
      <summary className={detailSummaryClass}>{summary}</summary>
      <div
        className={cn(
          "border-t border-line px-[13px] pb-[13px] [overflow-wrap:anywhere] text-content-muted",
          bodyClassName
        )}
      >
        {children}
      </div>
    </details>
  )
}

function WireEvidencePlaceholder() {
  return (
    <div>
      <button
        className="flex items-center gap-[7px] rounded-[8px] border border-line-strong bg-canvas px-[11px] py-[9px] text-accent disabled:cursor-not-allowed disabled:opacity-50"
        disabled
        title="Wire evidence lands with the v1 wire route"
        type="button"
      >
        <FileJson2 size={15} /> Open exact socket content
      </button>
    </div>
  )
}

function MessagePreview({ record }: { record: SessionEvidenceRecord }) {
  const messages = arrayField(recordFields(record).messages)
  const last = messages.at(-1)
  if (typeof last !== "object" || last === null) {
    return <div className={contentCardClass}>{record.preview}</div>
  }
  const role = stringField(last, "role") ?? "message"
  const content = messageContent((last as EvidenceFields).content)
  return (
    <div className={contentCardClass}>
      <strong>{capitalize(role)}</strong>
      <p className="m-0">{content || record.preview}</p>
    </div>
  )
}

function MessageBody({ record }: { record: SessionEvidenceRecord }) {
  const messages = arrayField(recordFields(record).messages)
  if (messages.length === 0) {
    return <pre className={detailPreClass}>{record.preview}</pre>
  }
  return (
    <div className={recordStackClass}>
      {messages.map((message, index) => {
        const object =
          typeof message === "object" && message !== null
            ? (message as EvidenceFields)
            : {}
        return (
          // Prompt messages carry no identity and never reorder, the
          // positional key is the stable one.
          // oxlint-disable-next-line no-array-index-key
          <article key={`${String(object.role)}:${index}`}>
            <strong className="mb-[6px] ml-[3px] block text-[11px] text-accent uppercase">
              {capitalize(String(object.role ?? "message"))}
            </strong>
            <pre className={detailPreClass}>
              {messageContent(object.content)}
            </pre>
          </article>
        )
      })}
    </div>
  )
}

function ToolSurface({ record }: { record: SessionEvidenceRecord }) {
  const tools = arrayField(recordFields(record).tools)
  return (
    <details className={detailClass}>
      <summary className={detailSummaryClass}>
        {tools.length} available tool{tools.length === 1 ? "" : "s"}
      </summary>
      <div className="flex flex-wrap gap-[7px] px-[12px] pb-[12px]">
        {tools.map((tool) => (
          <code
            className="rounded-[6px] border border-line bg-canvas px-[8px] py-[5px] text-[11px] text-content-muted"
            key={String(tool)}
          >
            {String(tool)}
          </code>
        ))}
      </div>
    </details>
  )
}

function ResponseEconomics({ record }: { record: SessionEvidenceRecord }) {
  const usage = objectField(recordFields(record).usage)
  const input =
    numberValue(usage.input_tokens) +
    numberValue(usage.cache_creation_input_tokens) +
    numberValue(usage.cache_read_input_tokens)
  const output = numberValue(usage.output_tokens)
  return (
    <div className="mt-[9px] grid grid-cols-[repeat(5,minmax(0,1fr))] gap-px overflow-hidden rounded-[10px] border border-line bg-line max-[900px]:grid-cols-2">
      <EconomicsCell
        label="Duration"
        value={formatDuration(record.duration_ms)}
      />
      <EconomicsCell label="Input" value={`${formatInteger(input)} tok`} />
      <EconomicsCell label="Output" value={`${formatInteger(output)} tok`} />
      <EconomicsCell label="Context" value={`${formatInteger(input)} tok`} />
      <EconomicsCell cost label="Cost" value={usd(record.cost_usd)} />
    </div>
  )
}

function EconomicsCell({
  cost = false,
  label,
  value,
}: {
  cost?: boolean
  label: string
  value: string
}) {
  return (
    <div className="bg-surface px-[11px] py-[10px]">
      <span className="block text-[11px] text-content-quiet uppercase">
        {label}
      </span>
      <strong className={cn("text-[13px]", cost && "text-warning")}>
        {value}
      </strong>
    </div>
  )
}

function TransportPath({ cycle }: { cycle: StoryToolCycle }) {
  const gateway = cycle.gatewayCall
  return (
    <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-[9px] pt-[13px] max-[900px]:grid-cols-1">
      <TransportNode
        icon={
          <GitBranch className="row-start-1 row-end-3 text-accent" size={17} />
        }
        label="Agent call"
        value={cycle.call.source_ref}
      />
      <ChevronRight
        className="max-[900px]:rotate-90 max-[900px]:justify-self-center"
        size={18}
      />
      <TransportNode
        icon={
          <Wrench className="row-start-1 row-end-3 text-accent" size={17} />
        }
        label="Gateway"
        value={gateway?.trace_id ?? "trace unavailable"}
      />
      <ChevronRight
        className="max-[900px]:rotate-90 max-[900px]:justify-self-center"
        size={18}
      />
      <TransportNode
        icon={
          <MessageSquareText
            className="row-start-1 row-end-3 text-accent"
            size={17}
          />
        }
        label="Command"
        value={
          cycle.commands.map((record) => evidenceText(record)).join(", ") ||
          "command body unavailable"
        }
      />
    </div>
  )
}

function TransportNode({
  icon,
  label,
  value,
}: {
  icon: ReactNode
  label: string
  value: string
}) {
  return (
    <div className="grid min-w-0 grid-cols-[auto_1fr] gap-x-[8px] gap-y-[3px] rounded-[9px] border border-line bg-canvas p-[11px]">
      {icon}
      <span className="text-[10px] text-content-quiet uppercase">{label}</span>
      <strong className="overflow-hidden font-mono text-[11px] font-normal text-ellipsis whitespace-nowrap">
        {value}
      </strong>
    </div>
  )
}

function ObservationList({ records }: { records: SessionEvidenceRecord[] }) {
  return (
    <dl className="m-0 grid gap-[7px]">
      {records.map((record) => (
        <div
          className="grid grid-cols-[120px_1fr] gap-[9px] border-b border-line pb-[7px]"
          key={record.id}
        >
          <dt className="text-[10px] text-content-quiet uppercase">
            {observationLabel(record)}
          </dt>
          <dd className="m-0 text-[12px] text-content-primary">
            {observationValue(record)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function TransformationStages({ stages }: { stages: EvidenceFields }) {
  const pairs = [
    ["Original MCP result", stages.mcp_result],
    ["After result presentation", stages.rendered_result],
    ["Exact model input", stages.model_input],
  ] as const
  return (
    <StoryDetail
      bodyClassName={recordStackClass}
      summary="Open each tool result transformation"
    >
      {pairs.map(([label, value]) => (
        <article className={rawRecordClass} key={label}>
          <header className="mb-[8px] flex justify-between gap-[12px]">
            <strong>{label}</strong>
          </header>
          <pre className={detailPreClass}>
            {typeof value === "string" ? value : "Unavailable"}
          </pre>
        </article>
      ))}
    </StoryDetail>
  )
}

function EvidenceDetail({ record }: { record: SessionEvidenceRecord }) {
  return (
    <StoryDetail
      summary={
        <>
          <FileJson2 size={15} /> Evidence and provenance
        </>
      }
    >
      <Provenance record={record} />
      <pre className={detailPreClass}>
        {JSON.stringify(record.fields, null, 2)}
      </pre>
      {record.capture_gaps.length > 0 ? (
        <CaptureGaps gaps={record.capture_gaps} />
      ) : null}
    </StoryDetail>
  )
}

function Provenance({ record }: { record: SessionEvidenceRecord }) {
  return (
    <dl className="mt-[13px] mb-[11px] grid grid-cols-2 gap-px overflow-hidden rounded-[8px] border border-line bg-line">
      <ProvenanceCell label="Source" value={record.source_ref} />
      <ProvenanceCell label="Form" value={record.form} />
      <ProvenanceCell label="Timestamp" value={formatTimestamp(record.at)} />
      <ProvenanceCell
        label="Trace"
        mono
        value={record.trace_id ?? "not correlated"}
      />
      <ProvenanceCell label="Record" mono value={record.id} />
      <ProvenanceCell
        label="Parent"
        mono
        value={record.parent_id ?? "session root"}
      />
    </dl>
  )
}

function ProvenanceCell({
  label,
  mono = false,
  value,
}: {
  label: string
  mono?: boolean
  value: string
}) {
  return (
    <div className="min-w-0 bg-canvas px-[11px] py-[9px]">
      <dt className="text-[9px] tracking-[0.08em] text-content-quiet uppercase">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-[3px] mb-0 overflow-hidden text-[11px] text-ellipsis whitespace-nowrap text-content-muted",
          mono && "font-mono"
        )}
      >
        {value}
      </dd>
    </div>
  )
}

function CaptureGaps({ gaps }: { gaps: string[] }) {
  return (
    <div
      className={cn(
        availabilityClass,
        "mt-[12px] grid gap-[5px] border-[#665530] bg-[#1b1911]"
      )}
    >
      <strong className="text-warning">Unavailable retained evidence</strong>
      {gaps.map((gap) => (
        <span key={gap}>{humanGap(gap)}</span>
      ))}
    </div>
  )
}

function Availability({ gap }: { gap: string }) {
  return <div className={availabilityClass}>{humanGap(gap)}</div>
}

function StoryTerminal({
  captureGaps,
  investigation,
  records,
}: {
  captureGaps: string[]
  investigation: SessionInvestigation
  records: SessionEvidenceRecord[]
}) {
  return (
    <section className="mt-[34px] rounded-[13px] border border-l-[3px] border-line border-l-[#8cdda7] bg-surface p-[25px]">
      <span className={eyebrowClass}>End of session</span>
      <h2 className="mt-[8px] mb-[5px] text-[20px] font-bold capitalize">
        {investigation.run.lifecycle ??
          (investigation.run.success ? "Completed" : "Stopped")}
      </h2>
      <p className="mb-[14px] text-content-muted">
        {investigation.run.ended_at
          ? `${formatTimestamp(investigation.run.ended_at)} · `
          : ""}
        {investigation.run.stop_reason || "No terminal reason retained."}
      </p>
      {records.length > 0 ? (
        <StoryDetail
          bodyClassName={recordStackClass}
          summary="Terminal lifecycle evidence"
        >
          {records.map((record) => (
            <article className={rawRecordClass} key={record.id}>
              <header className="mb-[8px] flex justify-between gap-[12px]">
                <strong>{record.label}</strong>
              </header>
              <pre className={detailPreClass}>
                {JSON.stringify(record.fields, null, 2)}
              </pre>
            </article>
          ))}
        </StoryDetail>
      ) : null}
      {captureGaps.length > 0 ? (
        <CaptureGaps gaps={captureGaps} />
      ) : (
        <div
          className={cn(availabilityClass, "border-[#3c6b4d] text-[#8cdda7]")}
        >
          All required evidence forms report complete capture.
        </div>
      )}
    </section>
  )
}

function toolOriginalText(cycle: StoryToolCycle): string {
  const wireText = cycle.wireTexts
    .filter((record) => recordFields(record).direction !== "out")
    .map(evidenceText)
    .filter(Boolean)
    .join("\n")
  if (wireText) return wireText
  const stages = objectField(cycle.agentResult?.fields?.stages)
  const mcp = stages.mcp_result
  if (typeof mcp === "string" && mcp.trim()) return extractTextField(mcp) || mcp
  const result = cycle.agentResult?.fields?.result
  if (typeof result === "string") return extractTextField(result) || result
  return ""
}

function toolDeliveredText(cycle: StoryToolCycle): string {
  const stages = objectField(cycle.agentResult?.fields?.stages)
  for (const value of [stages.model_input, stages.rendered_result]) {
    if (typeof value === "string" && value.trim()) return value
  }
  const result = cycle.agentResult?.fields?.result
  return typeof result === "string" ? result : ""
}

function extractTextField(value: string): string {
  try {
    const parsed = JSON.parse(value) as unknown
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof (parsed as EvidenceFields).text === "string"
    ) {
      return (parsed as Record<string, string>).text
    }
  } catch {
    return ""
  }
  return ""
}

function observationLabel(record: SessionEvidenceRecord): string {
  const raw = recordFields(record).kind
  const kind = typeof raw === "string" ? raw : record.kind
  return kind.replaceAll("_", " ")
}

function observationValue(record: SessionEvidenceRecord): string {
  const fields = recordFields(record)
  for (const key of ["title", "text", "place_id", "room_id"]) {
    const value = fields[key]
    if (typeof value === "string" && value.trim()) return value
  }
  if (record.room_id) return record.room_id
  return record.preview
}

function promptSummary(record: SessionEvidenceRecord): string {
  const fields = recordFields(record)
  const messages = arrayField(fields.messages)
  const tools = arrayField(fields.tools)
  return `${messages.length || numberValue(fields.message_count)} message${
    messages.length === 1 ? "" : "s"
  } · ${tools.length || numberValue(fields.tool_count)} tools`
}

function responseSubtitle(record: SessionEvidenceRecord): string {
  const fields = recordFields(record)
  const model =
    typeof fields.model === "string" ? fields.model : "model unavailable"
  const stop =
    typeof fields.stop_reason === "string"
      ? fields.stop_reason.replaceAll("_", " ")
      : record.status
  return `${model} · ${stop}`
}

function responseText(record: SessionEvidenceRecord): string {
  const text = evidenceText(record)
  if (text && !text.startsWith("(tool use:")) return text
  const count = text.match(/\d+/)?.[0]
  return count
    ? `Requested ${count} tool call${count === "1" ? "" : "s"}.`
    : text || "The provider response body was not retained."
}

function toolName(record: SessionEvidenceRecord): string {
  const value = recordFields(record).name
  if (typeof value === "string") return value
  return record.label.replace(/^Tool call · /, "")
}

function stepKey(step: StoryStep, index: number): string {
  return step.type === "tool" ? step.cycle.id : `${step.record.id}:${index}`
}

function toolCountAtStart(records: SessionEvidenceRecord[]): number {
  const profile = records.find(
    (record) =>
      typeof recordFields(record).advertised_tools === "number" ||
      typeof recordFields(record).available_capabilities === "number"
  )
  if (profile) {
    return numberValue(
      recordFields(profile).advertised_tools ??
        recordFields(profile).available_capabilities
    )
  }
  return 0
}

function responseCount(investigation: SessionInvestigation): number {
  return (
    investigation.run.responses ??
    investigation.records.filter((record) => record.kind === "response").length
  )
}

function totalTokens(investigation: SessionInvestigation): number {
  return (
    investigation.cost.fresh_input_tokens +
    investigation.cost.cache_read_tokens +
    investigation.cost.cache_write_tokens +
    investigation.cost.output_tokens
  )
}

function humanGap(gap: string): string {
  const labels: Record<string, string> = {
    model_request_body_not_retained:
      "The exact assembled model request body was not retained for this historical run.",
    provider_response_body_not_retained:
      "The exact provider response body was not retained for this historical run.",
    tool_result_transform_stages_not_retained:
      "The before and after tool-result transformation stages were not retained.",
    mud_text_transform_stages_not_retained:
      "The decoded and normalized MUD transformation stages were not retained.",
    zone_not_observed: "The MUD zone was not observed.",
  }
  return labels[gap] ?? gap.replaceAll("_", " ")
}

function messageContent(value: unknown): string {
  if (typeof value === "string") return value
  if (!Array.isArray(value)) return formatJson(value)
  return value
    .map((item) => {
      if (typeof item === "string") return item
      if (typeof item !== "object" || item === null) return String(item)
      const object = item as EvidenceFields
      return typeof object.text === "string" ? object.text : formatJson(object)
    })
    .join("\n")
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? String(value)
}

function objectField(value: unknown): EvidenceFields {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as EvidenceFields)
    : {}
}

function arrayField(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function stringField(value: object, key: string): string | null {
  const field = (value as EvidenceFields)[key]
  return typeof field === "string" ? field : null
}

function numberField(value: unknown): number {
  return typeof value === "number" ? value : 0
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0
}

function capitalize(value: string): string {
  return value ? `${value[0].toUpperCase()}${value.slice(1)}` : value
}

function sentenceCase(value: string): string {
  return value ? `${value[0]?.toUpperCase()}${value.slice(1)}` : value
}

function formatClock(value: string, milliseconds = false): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "time unavailable"
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    hour12: false,
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: milliseconds ? 3 : undefined,
  })
}

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "time unavailable"
  return date.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "medium",
  })
}

function formatDuration(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "duration unavailable"
  if (value < 1_000) return `${Math.round(value)}ms`
  return `${(value / 1_000).toFixed(value < 10_000 ? 2 : 1)}s`
}

function formatInteger(value: number): string {
  return Math.round(value).toLocaleString()
}

function usd(value: number): string {
  return `$${value.toFixed(6)}`
}

export { SessionStory, type SessionStoryProps }
