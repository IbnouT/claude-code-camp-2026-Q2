import {
  Bot,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  FileJson2,
  Flag,
  GitBranch,
  MessageSquareText,
  Wrench,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  SessionEvidenceRecord,
  SessionInvestigation,
  SessionRecordFields,
} from "../contracts";
import {
  evidenceText,
  iterationKey,
  type SessionSelection,
  type SessionStory as Story,
  type StoryObjectiveEpoch,
  type StoryIteration,
  type StoryStep,
  type StoryToolCycle,
  type StoryTurn,
} from "./storyProjection";
import { StoryRecordFields } from "./StoryRecordFields";
import { StoryWireEvidence } from "./StoryWireEvidence";
import styles from "./SessionStory.module.css";

function cx(...names: string[]): string {
  return names.map((name) => styles[name]).filter(Boolean).join(" ");
}

// The record kinds whose heavy members the story withholds and one
// endpoint serves on request.
const withheldKinds = new Set([
  "session_start",
  "prompt",
  "model_request",
  "provider_response",
]);

type Props = {
  investigation: SessionInvestigation;
  story: Story;
  selection: SessionSelection;
  focusedGoalNumber: number | null;
  search: string;
  onGoalSelect: (epoch: StoryObjectiveEpoch) => void;
  onSelect: (selection: SessionSelection) => void;
  onOpenCost: () => void;
};

export function SessionStory({
  investigation,
  story,
  selection,
  focusedGoalNumber,
  search,
  onGoalSelect,
  onSelect,
  onOpenCost,
}: Props) {
  const firstIteration = story.turns[0]?.iterations[0]?.number ?? null;
  const firstTurn = story.turns[0]?.iterations[0]?.turn ?? null;
  const [openIterations, setOpenIterations] = useState<Set<string>>(
    () => new Set(selection.iteration === null || selection.turn === null
      ? firstIteration === null || firstTurn === null
        ? []
        : [iterationKey(firstTurn, firstIteration)]
      : [iterationKey(selection.turn, selection.iteration)]),
  );
  const selectedIteration = (
    selection.turn !== null && selection.iteration !== null
      ? story.byIteration.get(iterationKey(
          selection.turn,
          selection.iteration,
        ))
      : undefined
  );
  const [openGoals, setOpenGoals] = useState<Set<number>>(
    () => new Set(
      selection.recordId !== null && selectedIteration !== undefined
        ? [selectedIteration.objectiveEpoch]
        : [],
    ),
  );
  // A session opens on its turn headings, so only a chosen record opens a turn.
  const [openTurns, setOpenTurns] = useState<Set<number>>(
    () => new Set(
      selection.recordId !== null && selection.turn !== null
        ? [selection.turn]
        : [],
    ),
  );
  const selectedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (selection.turn === null || selection.iteration === null) return;
    const key = iterationKey(selection.turn, selection.iteration);
    setOpenIterations((current) => {
      if (current.has(key)) return current;
      return new Set([...current, key]);
    });
  }, [selection.iteration, selection.turn]);

  // A selected record must stay reachable, so selecting it opens its turn.
  useEffect(() => {
    if (selection.recordId === null || selection.turn === null) return;
    const turn = selection.turn;
    setOpenTurns((current) => (
      current.has(turn) ? current : new Set([...current, turn])
    ));
  }, [selection.recordId, selection.turn]);

  useEffect(() => {
    if (selection.recordId === null) return;
    if (typeof selectedRef.current?.scrollIntoView !== "function") return;
    selectedRef.current.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, [selection.iteration, selection.recordId, selection.turn]);

  const normalizedSearch = search.trim().toLowerCase();
  const turns = useMemo(() => {
    if (!normalizedSearch) return story.turns;
    return story.turns
      .map((turn) => ({
        ...turn,
        iterations: turn.iterations.filter((iteration) => (
          [
            iteration.title,
            iteration.subtitle,
            iteration.roomTitle,
            ...iteration.records.map((record) => (
              `${record.label} ${record.preview}`
            )),
          ].join(" ").toLowerCase().includes(normalizedSearch)
        )),
      }))
      .filter((turn) => turn.iterations.length > 0);
  }, [normalizedSearch, story.turns]);
  const chapters = useMemo(() => story.objectiveEpochs
    .map((epoch) => {
      const chapterMatches = normalizedSearch
        && [
          epoch.title,
          ...epoch.nudges.map((nudge) => nudge.instruction),
        ].join(" ").toLowerCase().includes(normalizedSearch);
      const sourceTurns = chapterMatches ? story.turns : turns;
      return {
        epoch,
        turns: sourceTurns
        .map((turn): StoryTurn => {
          const iterations = turn.iterations.filter(
            (iteration) => iteration.objectiveEpoch === epoch.number,
          );
          return {
            ...turn,
            startedAt: iterations[0]?.startedAt ?? turn.startedAt,
            endedAt: iterations.at(-1)?.endedAt ?? turn.endedAt,
            durationMs: iterations.reduce(
              (total, iteration) => total + iteration.durationMs,
              0,
            ),
            costUsd: iterations.reduce(
              (total, iteration) => total + iteration.costUsd,
              0,
            ),
            iterations,
          };
        })
        .filter((turn) => turn.iterations.length > 0),
      };
    })
    .filter((chapter) => (
      !normalizedSearch || chapter.turns.length > 0
    )), [normalizedSearch, story.objectiveEpochs, story.turns, turns]);
  // A filter has to reach evidence inside a turn, so every turn it keeps opens.
  const matchingTurns = useMemo(() => new Set(
    chapters.flatMap((chapter) => chapter.turns.map((turn) => turn.number)),
  ), [chapters]);
  const matchingIterations = chapters.reduce(
    (total, chapter) => total + chapter.turns.reduce(
      (chapterTotal, turn) => chapterTotal + turn.iterations.length,
      0,
    ),
    0,
  );

  const startAt = investigation.run.created_at
    ?? story.startRecords[0]?.at
    ?? story.turns[0]?.startedAt
    ?? "";
  return (
    <section className={cx("session-story")}  aria-label="Complete session story">
      <div className={cx("story-intro")} >
        <article className={cx("story-start-card")} >
          <span className={cx("story-eyebrow")} >
            Session start · {formatClock(startAt, true)}
          </span>
          <h2>
            {story.objectiveEpochs.length} objective
            {story.objectiveEpochs.length === 1 ? "" : "s"} shaped this session
          </h2>
          <p>
            {sentenceCase(story.objectiveEpochs[0]?.title
              ?? investigation.objective
              ?? "No initial objective was retained.")}
            {" "}The run used {investigation.model ?? "an unlabelled model"} with
            {" "}{toolCountAtStart(story.startRecords)} available tools.
          </p>
          <StandingInstructions
            investigation={investigation}
            records={story.startRecords}
          />
        </article>
        <button className={cx("story-cost-card")}  type="button" onClick={onOpenCost}>
          <span>Model activity</span>
          <strong>{responseCount(investigation)} responses</strong>
          <span>{formatInteger(totalTokens(investigation))} retained tokens</span>
          <small>Explore the {usd(investigation.cost.total_usd)} cost →</small>
        </button>
      </div>

      {normalizedSearch ? (
        <p className={cx("story-search-status")} role="status">
          {matchingIterations} matching iteration
          {matchingIterations === 1 ? "" : "s"} for “{search}”.
          {" "}Matching goals and nudges are expanded.
        </p>
      ) : null}

      {normalizedSearch && matchingIterations === 0 ? (
        <div className={cx("story-empty")} >
          No retained Story evidence contains “{search}”. The complete
          recording remains available when the filter is cleared.
        </div>
      ) : null}

      {chapters.map(({ epoch, turns: chapterTurns }) => {
        const expanded = normalizedSearch
          ? chapterTurns.length > 0
          : openGoals.has(epoch.number);
        const current = epoch.number === story.objectiveEpochs.at(-1)?.number;
        const focused = epoch.number === focusedGoalNumber;
        const totalIterationCount = story.turns.reduce(
          (total, turn) => total + turn.iterations.filter(
            (iteration) => iteration.objectiveEpoch === epoch.number,
          ).length,
          0,
        );
        return (
          <section
            aria-label={`Goal ${epoch.number}: ${sentenceCase(epoch.title)}`}
            className={cx(
              "story-goal-chapter",
              ...(current ? ["is-current"] : []),
              ...(focused ? ["is-focused"] : []),
              ...(expanded ? ["is-expanded"] : ["is-collapsed"]),
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
                onGoalSelect(epoch);
                setOpenGoals((existing) => {
                  const next = new Set(existing);
                  if (next.has(epoch.number)) next.delete(epoch.number);
                  else next.add(epoch.number);
                  return next;
                });
              }}
              onToggle={() => setOpenGoals((existing) => {
                const next = new Set(existing);
                if (next.has(epoch.number)) next.delete(epoch.number);
                else next.add(epoch.number);
                return next;
              })}
            />
            {expanded && chapterTurns.length === 0 ? (
              <p className={cx("story-goal-empty")}>
                No retained iteration followed this applied goal.
              </p>
            ) : null}
            {expanded ? (
              <StoryTurns
                investigation={investigation}
                openIterations={openIterations}
                openTurns={normalizedSearch ? matchingTurns : openTurns}
                selection={selection}
                selectedRef={selectedRef}
                turns={chapterTurns}
                onOpenIterationsChange={setOpenIterations}
                onOpenTurnsChange={setOpenTurns}
                onSelect={onSelect}
              />
            ) : null}
          </section>
        );
      })}

      <StoryTerminal
        captureGaps={investigation.capture_gaps}
        investigation={investigation}
        records={story.terminalRecords}
      />
    </section>
  );
}

function StoryTurns({
  investigation,
  openIterations,
  openTurns,
  selection,
  selectedRef,
  turns,
  onOpenIterationsChange,
  onOpenTurnsChange,
  onSelect,
}: {
  investigation: SessionInvestigation;
  openIterations: Set<string>;
  openTurns: Set<number>;
  selection: SessionSelection;
  selectedRef: React.RefObject<HTMLElement | null>;
  turns: StoryTurn[];
  onOpenIterationsChange: React.Dispatch<React.SetStateAction<Set<string>>>;
  onOpenTurnsChange: React.Dispatch<React.SetStateAction<Set<number>>>;
  onSelect: (selection: SessionSelection) => void;
}) {
  return turns.map((turn) => {
    const open = openTurns.has(turn.number);
    return (
      <section
        aria-label={`Turn ${turn.number}`}
        className={cx(
          "story-turn",
          ...(open ? ["is-open"] : []),
        )}
        key={`${turn.number}:${turn.iterations[0]?.id ?? "empty"}`}
      >
        <h3 className={cx("story-turn-heading")}>
          <button
            aria-expanded={open}
            className={cx("story-turn-toggle")}
            type="button"
            onClick={() => onOpenTurnsChange((current) => {
              const next = new Set(current);
              if (next.has(turn.number)) next.delete(turn.number);
              else next.add(turn.number);
              return next;
            })}
          >
            <span className={cx("story-turn-number")}>Turn {turn.number}</span>
            {turn.instruction === null ? null : (
              <span className={cx("story-turn-instruction")}>
                <span
                  className={cx(
                    "story-eyebrow",
                    "story-turn-tag",
                    `is-${turn.instruction.kind}`,
                  )}
                >
                  {turn.instruction.kind === "nudge" ? "Nudge" : "Goal"}
                </span>
                {sentenceCase(turn.instruction.text)}
              </span>
            )}
            <span className={cx("story-turn-measures")}>
              {formatClock(turn.startedAt, true)} to {formatClock(turn.endedAt, true)}
              {" · "}
              {turn.iterations.length} iteration
              {turn.iterations.length === 1 ? "" : "s"}
            </span>
            <b>{usd(turn.costUsd)}</b>
            <ChevronRight className={cx("story-caret")} size={18} />
          </button>
        </h3>
        {open ? turn.iterations.map((iteration) => (
          <StoryIterationCard
            investigation={investigation}
            iteration={iteration}
            key={iteration.id}
            open={openIterations.has(iterationKey(
              iteration.turn,
              iteration.number,
            ))}
            selected={selection.turn === iteration.turn
              && selection.iteration === iteration.number}
            selectedRecordId={selection.recordId}
            selectedRef={selection.turn === iteration.turn
              && selection.iteration === iteration.number
              ? selectedRef
              : undefined}
            onSelect={onSelect}
            onToggle={() => {
              const key = iterationKey(iteration.turn, iteration.number);
              onOpenIterationsChange((current) => {
                const next = new Set(current);
                if (next.has(key)) next.delete(key);
                else next.add(key);
                return next;
              });
              onSelect({
                turn: iteration.turn,
                iteration: iteration.number,
                recordId: null,
              });
            }}
          />
        )) : null}
      </section>
    );
  });
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
  current: boolean;
  epoch: StoryObjectiveEpoch;
  expanded: boolean;
  focused: boolean;
  iterationCount: number;
  onFocus: () => void;
  onToggle: () => void;
}) {
  return (
    <header className={cx("story-goal-heading")}>
      <button
        aria-expanded={expanded}
        aria-label={`Select Goal ${epoch.number}: ${sentenceCase(epoch.title)}`}
        className={cx("story-goal-select")}
        type="button"
        onClick={onFocus}
      >
        <span className={cx("story-goal-icon")} aria-hidden="true">
          <Flag size={18} />
        </span>
        <span>
          <span className={cx("story-eyebrow")}>
            Goal {epoch.number}
            {focused ? " · selected" : current ? " · latest" : ""}
          </span>
          <strong>{sentenceCase(epoch.title)}</strong>
          <small>
            Applied {formatClock(epoch.startedAt, true)}
            {" · "}
            {epoch.nudges.length} nudge{epoch.nudges.length === 1 ? "" : "s"}
            {" · "}
            {iterationCount} iteration{iterationCount === 1 ? "" : "s"}
          </small>
        </span>
      </button>
      <div className={cx("story-goal-actions")}>
        <button
          aria-label={`${expanded ? "Collapse" : "Expand"} Goal ${epoch.number}`}
          aria-expanded={expanded}
          type="button"
          onClick={onToggle}
        >
          <ChevronRight aria-hidden="true" size={16} />
          {expanded ? "Collapse" : "Expand"}
        </button>
      </div>
    </header>
  );
}

function StoryIterationCard({
  investigation,
  iteration,
  open,
  selected,
  selectedRecordId,
  selectedRef,
  onSelect,
  onToggle,
}: {
  investigation: SessionInvestigation;
  iteration: StoryIteration;
  open: boolean;
  selected: boolean;
  selectedRecordId: string | null;
  selectedRef?: React.RefObject<HTMLElement | null>;
  onSelect: (selection: SessionSelection) => void;
  onToggle: () => void;
}) {
  return (
    <article
      className={cx(
        "story-iteration",
        ...(selected ? ["is-selected"] : []),
        ...(open ? ["is-open"] : []),
      )}
      ref={selectedRef as React.RefObject<HTMLElement> | undefined}
    >
      <button
        aria-expanded={open}
        className={cx("story-iteration-toggle")}
        type="button"
        onClick={onToggle}
      >
        <span className={cx("story-iteration-number")}>{iteration.number}</span>
        <span className={cx("story-iteration-title")}>
          <strong>{iteration.title}</strong>
          <span>{iteration.subtitle}</span>
        </span>
        <span className={cx("story-iteration-measures")} >
          <time dateTime={iteration.startedAt}>{formatClock(iteration.startedAt, true)}</time>
          <span>{formatDuration(iteration.durationMs)}</span>
          <span>
            {iteration.toolCalls} tool call{iteration.toolCalls === 1 ? "" : "s"}
          </span>
          <b>{usd(iteration.costUsd)}</b>
          <ChevronRight className={cx("story-caret")}  size={18} />
        </span>
      </button>
      {open ? (
        <div className={cx("story-iteration-body")} >
          {iteration.steps.map((step, index) => (
            <StoryStepView
              investigation={investigation}
              iteration={iteration.number}
              turn={iteration.turn}
              key={stepKey(step, index)}
              selectedRecordId={selectedRecordId}
              step={step}
              onSelect={onSelect}
            />
          ))}
          {iteration.captureGaps.length > 0 ? (
            <CaptureGaps gaps={iteration.captureGaps} />
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function StoryStepView({
  investigation,
  iteration,
  turn,
  selectedRecordId,
  step,
  onSelect,
}: {
  investigation: SessionInvestigation;
  iteration: number;
  turn: number;
  selectedRecordId: string | null;
  step: StoryStep;
  onSelect: (selection: SessionSelection) => void;
}) {
  if (step.type === "tool") {
    return (
      <ToolCycle
        cycle={step.cycle}
        investigation={investigation}
        iteration={iteration}
        turn={turn}
        selectedRecordId={selectedRecordId}
        onSelect={onSelect}
      />
    );
  }
  const record = step.record;
  const sessionId = runtimeSessionId(investigation);
  if (record.kind === "prompt") {
    return (
      <CausalStep
        dot="input"
        record={record}
        selected={selectedRecordId === record.id}
        title="Input available to the model"
        subtitle={promptSummary(record)}
        onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
      >
        <MessagePreview record={record} />
        <details className={cx("story-detail")} >
          <summary>
            Exact model request, system prompt, messages, and tool schemas
          </summary>
          <div className={cx("story-detail-body")} >
            {sessionId === null ? (
              <div className={cx("story-availability")} >
                Exact request loading is available for registered runtime
                sessions. This experiment sample retains its prompt summary.
              </div>
            ) : (
              <StoryRecordFields record={record} sessionId={sessionId}>
                {(detail: SessionRecordFields) => (
                  <>
                    <MessageBody fields={detail.fields} preview={record.preview} />
                    <ToolSurface fields={detail.fields} />
                  </>
                )}
              </StoryRecordFields>
            )}
            <Provenance record={record} />
          </div>
        </details>
      </CausalStep>
    );
  }
  if (record.kind === "plan" || record.kind === "reasoning") {
    return (
      <CausalStep
        dot="plan"
        record={record}
        selected={selectedRecordId === record.id}
        title={record.kind === "reasoning" ? "Retained reasoning" : "Agent plan"}
        subtitle="retained text"
        onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
      >
        <div className={cx("story-content-card")} >{evidenceText(record)}</div>
        <EvidenceDetail record={record} sessionId={sessionId} />
      </CausalStep>
    );
  }
  if (record.kind === "response") {
    return (
      <CausalStep
        dot="model"
        record={record}
        selected={selectedRecordId === record.id}
        title="Model response"
        subtitle={responseSubtitle(record)}
        onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
      >
        <div className={cx("story-content-card")} >
          {responseText(record)}
        </div>
        <ResponseEconomics record={record} />
        <EvidenceDetail record={record} sessionId={sessionId} />
      </CausalStep>
    );
  }
  if (record.kind === "retry" || record.kind === "limit_reached") {
    return (
      <CausalStep
        dot="signal"
        record={record}
        selected={selectedRecordId === record.id}
        title={record.label}
        subtitle="Execution signal"
        onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
      >
        <div className={cx("story-availability", "is-warning")} >{evidenceText(record)}</div>
        <EvidenceDetail record={record} sessionId={sessionId} />
      </CausalStep>
    );
  }
  return (
    <CausalStep
      dot="input"
      record={record}
      selected={selectedRecordId === record.id}
      title={record.label}
      subtitle={`${record.source} · ${record.form}`}
      onSelect={() => onSelect({ turn, iteration, recordId: record.id })}
    >
      <div className={cx("story-content-card")} >{evidenceText(record)}</div>
      <EvidenceDetail record={record} sessionId={sessionId} />
    </CausalStep>
  );
}

function ToolCycle({
  cycle,
  investigation,
  iteration,
  turn,
  selectedRecordId,
  onSelect,
}: {
  cycle: StoryToolCycle;
  investigation: SessionInvestigation;
  iteration: number;
  turn: number;
  selectedRecordId: string | null;
  onSelect: (selection: SessionSelection) => void;
}) {
  const originalMudText = toolOriginalText(cycle);
  const parserText = cycle.parserInputs.map(evidenceText).filter(Boolean).join("\n\n");
  const deliveredText = toolDeliveredText(cycle);
  const stages = cycle.agentResult?.fields.stages;
  const hasTransformStages = typeof stages === "object" && stages !== null;
  const sessionId = runtimeSessionId(investigation);
  return (
    <>
      <CausalStep
        dot="tool"
        record={cycle.call}
        selected={selectedRecordId === cycle.call.id}
        title={`Tool call · ${toolName(cycle.call)}`}
        subtitle="agent → gateway → Telnet → MUD"
        onSelect={() => onSelect({
          turn,
          iteration,
          recordId: cycle.call.id,
        })}
      >
        <div className={cx("story-content-card", "mono")} >
          {toolName(cycle.call)}({formatJson(cycle.call.fields.args ?? {})})
        </div>
        <details className={cx("story-detail")} >
          <summary>Transport path and timing</summary>
          <div className={cx("story-detail-body")} >
            <TransportPath cycle={cycle} />
            {cycle.wires.map((wire) => (
              <details className={cx("story-nested-detail")}  key={wire.id}>
                <summary>
                  {wire.label} · {numberField(wire.fields.bytes)} bytes · {formatClock(wire.at, true)}
                </summary>
                <div className={cx("story-detail-body")} >
                  {sessionId === null ? (
                    <div className={cx("story-availability")} >
                      Exact wire loading is available for registered runtime
                      sessions. This experiment sample retains its wire metadata.
                    </div>
                  ) : (
                    <StoryWireEvidence record={wire} sessionId={sessionId} />
                  )}
                  <Provenance record={wire} />
                </div>
              </details>
            ))}
            <EvidenceDetail record={cycle.call} sessionId={sessionId} />
          </div>
        </details>
      </CausalStep>

      <CausalStep
        dot="world"
        record={cycle.wireTexts[0] ?? cycle.agentResult ?? cycle.call}
        selected={cycle.wireTexts.some((record) => record.id === selectedRecordId)}
        title="MUD response"
        subtitle={cycle.wireTexts.length > 0
          ? "original decoded text before parsing"
          : "best retained original text"}
        onSelect={() => onSelect({
          turn,
          iteration,
          recordId: cycle.wireTexts[0]?.id ?? cycle.agentResult?.id ?? cycle.call.id,
        })}
      >
        {originalMudText ? (
          <pre className={cx("story-terminal")} >{originalMudText}</pre>
        ) : (
          <div className={cx("story-availability")} >
            Original MUD text was not retained for this tool cycle.
          </div>
        )}
        {cycle.wireTexts.map((record) => <EvidenceDetail key={record.id} record={record} sessionId={sessionId} />)}
      </CausalStep>

      <CausalStep
        dot="world"
        record={cycle.parserInputs[0] ?? cycle.observations[0] ?? cycle.call}
        selected={[
          ...cycle.parserInputs,
          ...cycle.observations,
          ...cycle.stateChanges,
        ].some((record) => record.id === selectedRecordId)}
        title="Transformation and structured observation"
        subtitle="before and after remain connected"
        onSelect={() => onSelect({
          turn,
          iteration,
          recordId: cycle.parserInputs[0]?.id
            ?? cycle.observations[0]?.id
            ?? cycle.call.id,
        })}
      >
        <div className={cx("story-transform")} >
          <div className={cx("story-transform-panel")} >
            <h4>Parser input</h4>
            {parserText ? (
              <pre>{parserText}</pre>
            ) : (
              <Availability gap="mud_text_transform_stages_not_retained" />
            )}
          </div>
          <span className={cx("story-transform-arrow")} >→</span>
          <div className={cx("story-transform-panel")} >
            <h4>Typed observations and state</h4>
            {cycle.observations.length + cycle.stateChanges.length > 0 ? (
              <ObservationList records={[
                ...cycle.observations,
                ...cycle.stateChanges,
              ]} />
            ) : (
              <Availability gap="parsed_observations_not_retained" />
            )}
          </div>
        </div>
        <details className={cx("story-detail")} >
          <summary>Open each parsed record and state change</summary>
          <div className={cx("story-detail-body", "story-record-stack")} >
            {[...cycle.parserInputs, ...cycle.observations, ...cycle.stateChanges]
              .map((record) => (
                <article className={cx("story-raw-record")}  key={record.id}>
                  <header>
                    <strong>{record.label}</strong>
                    <time dateTime={record.at}>{formatClock(record.at, true)}</time>
                  </header>
                  <pre>{JSON.stringify(record.fields, null, 2)}</pre>
                  <Provenance record={record} />
                </article>
              ))}
          </div>
        </details>
      </CausalStep>

      <CausalStep
        dot="tool"
        record={cycle.agentResult ?? cycle.gatewayResults[0] ?? cycle.call}
        selected={[
          ...cycle.gatewayResults,
          ...(cycle.agentResult ? [cycle.agentResult] : []),
        ].some((record) => record.id === selectedRecordId)}
        title="Result delivered upstream"
        subtitle="exact content retained in the agent log"
        onSelect={() => onSelect({
          turn,
          iteration,
          recordId: cycle.agentResult?.id
            ?? cycle.gatewayResults[0]?.id
            ?? cycle.call.id,
        })}
      >
        {deliveredText ? (
          <pre className={cx("story-terminal")} >{deliveredText}</pre>
        ) : (
          <Availability gap="tool_result_transform_stages_not_retained" />
        )}
        {hasTransformStages ? (
          <TransformationStages stages={stages as Record<string, unknown>} />
        ) : null}
        {cycle.agentResult ? (
          <EvidenceDetail record={cycle.agentResult} sessionId={sessionId} />
        ) : null}
      </CausalStep>
    </>
  );
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
  children: React.ReactNode;
  dot: "input" | "plan" | "model" | "tool" | "world" | "signal";
  record: SessionEvidenceRecord;
  selected: boolean;
  subtitle: string;
  title: string;
  onSelect: () => void;
}) {
  return (
    <section
      className={cx(
        "story-causal-step",
        ...(selected ? ["is-selected"] : []),
      )}
      data-record-id={record.id}
    >
      <button
        aria-label={`Select ${title}`}
        className={cx("story-step-dot", `is-${dot}`)}
        type="button"
        onClick={onSelect}
      />
      <header className={cx("story-step-head")} >
        <strong>{title}</strong>
        <span>{subtitle}</span>
        <time dateTime={record.at}>{formatClock(record.at, true)}</time>
      </header>
      {children}
    </section>
  );
}

function MessagePreview({ record }: { record: SessionEvidenceRecord }) {
  const last = record.fields.last_message;
  if (typeof last !== "object" || last === null) {
    return <div className={cx("story-content-card")} >{record.preview}</div>;
  }
  const role = stringField(last, "role") ?? "message";
  const content = messageContent((last as Record<string, unknown>).content);
  return (
    <div className={cx("story-content-card")} >
      <strong>{capitalize(role)}</strong>
      <p>{content || record.preview}</p>
    </div>
  );
}

function MessageBody({
  fields,
  preview,
}: {
  fields: Record<string, unknown>;
  preview: string;
}) {
  const messages = arrayField(fields.messages);
  if (messages.length === 0) return <pre>{preview}</pre>;
  return (
    <div className={cx("story-message-list")} >
      {messages.map((message, index) => {
        const object = typeof message === "object" && message !== null
          ? message as Record<string, unknown>
          : {};
        return (
          <article key={`${String(object.role)}:${index}`}>
            <strong>{capitalize(String(object.role ?? "message"))}</strong>
            <pre>{messageContent(object.content)}</pre>
          </article>
        );
      })}
    </div>
  );
}

function ToolSurface({ fields }: { fields: Record<string, unknown> }) {
  const tools = arrayField(fields.tools);
  return (
    <details className={cx("story-nested-detail")} >
      <summary>{tools.length} available tool{tools.length === 1 ? "" : "s"}</summary>
      <div className={cx("story-tool-surface")} >
        {tools.map((tool) => <code key={String(tool)}>{String(tool)}</code>)}
      </div>
    </details>
  );
}

function ResponseEconomics({ record }: { record: SessionEvidenceRecord }) {
  const usage = objectField(record.fields.usage);
  const input = numberValue(usage.input_tokens)
    + numberValue(usage.cache_creation_input_tokens)
    + numberValue(usage.cache_read_input_tokens);
  const output = numberValue(usage.output_tokens);
  return (
    <div className={cx("story-economics")} >
      <div><span>Duration</span><strong>{formatDuration(record.duration_ms)}</strong></div>
      <div><span>Input</span><strong>{formatInteger(input)} tok</strong></div>
      <div><span>Output</span><strong>{formatInteger(output)} tok</strong></div>
      <div><span>Context</span><strong>{formatInteger(input)} tok</strong></div>
      <div className={cx("is-cost")} ><span>Cost</span><strong>{usd(record.cost_usd)}</strong></div>
    </div>
  );
}

function TransportPath({ cycle }: { cycle: StoryToolCycle }) {
  const gateway = cycle.gatewayCall;
  return (
    <div className={cx("story-transport")} >
      <div>
        <GitBranch size={17} />
        <span>Agent call</span>
        <strong>{cycle.call.source_ref}</strong>
      </div>
      <ChevronRight size={18} />
      <div>
        <Wrench size={17} />
        <span>Gateway</span>
        <strong>{gateway?.trace_id ?? "trace unavailable"}</strong>
      </div>
      <ChevronRight size={18} />
      <div>
        <MessageSquareText size={17} />
        <span>Command</span>
        <strong>{cycle.commands.map((record) => evidenceText(record)).join(", ") || "command body unavailable"}</strong>
      </div>
    </div>
  );
}

function ObservationList({ records }: { records: SessionEvidenceRecord[] }) {
  return (
    <dl className={cx("story-observations")} >
      {records.map((record) => (
        <div key={record.id}>
          <dt>{observationLabel(record)}</dt>
          <dd>{observationValue(record)}</dd>
        </div>
      ))}
    </dl>
  );
}

function TransformationStages({ stages }: { stages: Record<string, unknown> }) {
  const pairs = [
    ["Original MCP result", stages.mcp_result],
    ["After result presentation", stages.rendered_result],
    ["Exact model input", stages.model_input],
  ] as const;
  const mode = typeof stages.result_mode === "string"
    ? stages.result_mode
    : null;
  const cut = typeof stages.truncated_chars === "number"
    ? stages.truncated_chars
    : 0;
  return (
    <details className={cx("story-detail")} >
      <summary>
        Open each tool result transformation
        {mode === null ? "" : ` · presented ${mode}`}
        {cut > 0 ? ` · ${formatInteger(cut)} characters cut` : ""}
      </summary>
      <div className={cx("story-detail-body", "story-record-stack")} >
        {pairs.map(([label, value]) => (
          <article className={cx("story-raw-record")}  key={label}>
            <header>
              <strong>{label}</strong>
              {cut > 0 && label === "Exact model input" ? (
                <time>{formatInteger(cut)} characters cut before the model</time>
              ) : null}
            </header>
            <pre>{typeof value === "string" ? value : "Unavailable"}</pre>
          </article>
        ))}
      </div>
    </details>
  );
}

function EvidenceDetail({
  record,
  sessionId,
}: {
  record: SessionEvidenceRecord;
  sessionId: string | null;
}) {
  const withheld = sessionId !== null
    && record.source === "agent"
    && withheldKinds.has(record.kind);
  return (
    <details className={cx("story-detail")} >
      <summary><FileJson2 size={15} /> Evidence and provenance</summary>
      <div className={cx("story-detail-body")} >
        <Provenance record={record} />
        <pre>{JSON.stringify(record.fields, null, 2)}</pre>
        {withheld ? (
          <StoryRecordFields record={record} sessionId={sessionId}>
            {(detail: SessionRecordFields) => (
              <pre>{JSON.stringify(detail.fields, null, 2)}</pre>
            )}
          </StoryRecordFields>
        ) : null}
        {record.capture_gaps.length > 0 ? (
          <CaptureGaps gaps={record.capture_gaps} />
        ) : null}
      </div>
    </details>
  );
}

function runtimeSessionId(investigation: SessionInvestigation): string | null {
  return investigation.source_kind === "runtime_session"
    ? investigation.run.id
    : null;
}

function StandingInstructions({
  investigation,
  records,
}: {
  investigation: SessionInvestigation;
  records: SessionEvidenceRecord[];
}) {
  const start = records.find((record) => record.kind === "session_start");
  const system = start?.fields.system;
  if (typeof system !== "string" || system.trim() === "") return null;
  return (
    <details className={cx("story-detail", "story-standing")}>
      <summary>
        System prompt · the standing instructions given to the model
      </summary>
      <div className={cx("story-detail-body")}>
        <pre>{system}</pre>
      </div>
    </details>
  );
}

function Provenance({ record }: { record: SessionEvidenceRecord }) {
  return (
    <dl className={cx("story-provenance")} >
      <div><dt>Source</dt><dd>{record.source_ref}</dd></div>
      <div><dt>Form</dt><dd>{record.form}</dd></div>
      <div><dt>Timestamp</dt><dd>{formatTimestamp(record.at)}</dd></div>
      <div><dt>Trace</dt><dd className={cx("mono")} >{record.trace_id ?? "not correlated"}</dd></div>
      <div><dt>Record</dt><dd className={cx("mono")} >{record.id}</dd></div>
      <div><dt>Parent</dt><dd className={cx("mono")} >{record.parent_id ?? "session root"}</dd></div>
    </dl>
  );
}

function CaptureGaps({ gaps }: { gaps: string[] }) {
  return (
    <div className={cx("story-capture-gaps")} >
      <strong>Unavailable retained evidence</strong>
      {gaps.map((gap) => <span key={gap}>{humanGap(gap)}</span>)}
    </div>
  );
}

function Availability({ gap }: { gap: string }) {
  return <div className={cx("story-availability")} >{humanGap(gap)}</div>;
}

function StoryTerminal({
  captureGaps,
  investigation,
  records,
}: {
  captureGaps: string[];
  investigation: SessionInvestigation;
  records: SessionEvidenceRecord[];
}) {
  return (
    <section className={cx("story-terminal-state")} >
      <span className={cx("story-eyebrow")} >End of session</span>
      <h2>
        {investigation.run.lifecycle ?? (
          investigation.run.success ? "Completed" : "Stopped"
        )}
      </h2>
      <p>
        {investigation.run.ended_at
          ? `${formatTimestamp(investigation.run.ended_at)} · `
          : ""}
        {investigation.run.stop_reason || "No terminal reason retained."}
      </p>
      {records.length > 0 ? (
        <details className={cx("story-detail")} >
          <summary>Terminal lifecycle evidence</summary>
          <div className={cx("story-detail-body", "story-record-stack")} >
            {records.map((record) => (
              <article className={cx("story-raw-record")}  key={record.id}>
                <header><strong>{record.label}</strong></header>
                <pre>{JSON.stringify(record.fields, null, 2)}</pre>
              </article>
            ))}
          </div>
        </details>
      ) : null}
      {captureGaps.length > 0 ? <CaptureGaps gaps={captureGaps} /> : (
        <div className={cx("story-availability", "is-complete")} >All required evidence forms report complete capture.</div>
      )}
    </section>
  );
}

function toolOriginalText(cycle: StoryToolCycle): string {
  const wireText = cycle.wireTexts
    .filter((record) => record.fields.direction !== "out")
    .map(evidenceText)
    .filter(Boolean)
    .join("\n");
  if (wireText) return wireText;
  const stages = objectField(cycle.agentResult?.fields.stages);
  const mcp = stages.mcp_result;
  if (typeof mcp === "string" && mcp.trim()) return extractTextField(mcp) || mcp;
  const result = cycle.agentResult?.fields.result;
  if (typeof result === "string") return extractTextField(result) || result;
  return "";
}

function toolDeliveredText(cycle: StoryToolCycle): string {
  const stages = objectField(cycle.agentResult?.fields.stages);
  for (const value of [stages.model_input, stages.rendered_result]) {
    if (typeof value === "string" && value.trim()) return value;
  }
  const result = cycle.agentResult?.fields.result;
  return typeof result === "string" ? result : "";
}

function extractTextField(value: string): string {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (
      typeof parsed === "object"
      && parsed !== null
      && typeof (parsed as Record<string, unknown>).text === "string"
    ) {
      return (parsed as Record<string, string>).text;
    }
  } catch {
    return "";
  }
  return "";
}

function observationLabel(record: SessionEvidenceRecord): string {
  const kind = typeof record.fields.kind === "string"
    ? record.fields.kind
    : record.kind;
  return kind.replaceAll("_", " ");
}

function observationValue(record: SessionEvidenceRecord): string {
  for (const key of ["title", "text", "place_id", "room_id"]) {
    const value = record.fields[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  if (record.room_id) return record.room_id;
  return record.preview;
}

function promptSummary(record: SessionEvidenceRecord): string {
  const messages = arrayField(record.fields.messages);
  const tools = arrayField(record.fields.tools);
  return `${messages.length || numberValue(record.fields.message_count)} message${
    messages.length === 1 ? "" : "s"
  } · ${tools.length || numberValue(record.fields.tool_count)} tools`;
}

function responseSubtitle(record: SessionEvidenceRecord): string {
  const model = typeof record.fields.model === "string"
    ? record.fields.model
    : "model unavailable";
  const stop = typeof record.fields.stop_reason === "string"
    ? record.fields.stop_reason.replaceAll("_", " ")
    : record.status;
  return `${model} · ${stop}`;
}

function responseText(record: SessionEvidenceRecord): string {
  const text = evidenceText(record);
  if (text && !text.startsWith("(tool use:")) return text;
  const count = text.match(/\d+/)?.[0];
  return count
    ? `Requested ${count} tool call${count === "1" ? "" : "s"}.`
    : text || "The provider response body was not retained.";
}

function toolName(record: SessionEvidenceRecord): string {
  const value = record.fields.name;
  if (typeof value === "string") return value;
  return record.label.replace(/^Tool call · /, "");
}

function stepKey(step: StoryStep, index: number): string {
  return step.type === "tool" ? step.cycle.id : `${step.record.id}:${index}`;
}

function toolCountAtStart(records: SessionEvidenceRecord[]): number {
  const profile = records.find((record) => (
    typeof record.fields.advertised_tools === "number"
    || typeof record.fields.available_capabilities === "number"
  ));
  if (profile) {
    return numberValue(
      profile.fields.advertised_tools
      ?? profile.fields.available_capabilities,
    );
  }
  return 0;
}

function responseCount(investigation: SessionInvestigation): number {
  return investigation.run.responses
    ?? investigation.records.filter((record) => record.kind === "response").length;
}

function totalTokens(investigation: SessionInvestigation): number {
  return investigation.cost.fresh_input_tokens
    + investigation.cost.cache_read_tokens
    + investigation.cost.cache_write_tokens
    + investigation.cost.output_tokens;
}

function humanGap(gap: string): string {
  const labels: Record<string, string> = {
    model_request_body_not_retained: "The exact assembled model request body was not retained for this historical run.",
    provider_response_body_not_retained: "The exact provider response body was not retained for this historical run.",
    tool_result_transform_stages_not_retained: "The before and after tool-result transformation stages were not retained.",
    mud_text_transform_stages_not_retained: "The decoded and normalized MUD transformation stages were not retained.",
    zone_not_observed: "The MUD zone was not observed.",
  };
  return labels[gap] ?? gap.replaceAll("_", " ");
}

function messageContent(value: unknown): string {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return formatJson(value);
  return value.map((item) => {
    if (typeof item === "string") return item;
    if (typeof item !== "object" || item === null) return String(item);
    const object = item as Record<string, unknown>;
    return typeof object.text === "string"
      ? object.text
      : formatJson(object);
  }).join("\n");
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? String(value);
}

function objectField(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function arrayField(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringField(value: object, key: string): string | null {
  const field = (value as Record<string, unknown>)[key];
  return typeof field === "string" ? field : null;
}

function numberField(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function capitalize(value: string): string {
  return value ? `${value[0].toUpperCase()}${value.slice(1)}` : value;
}

function sentenceCase(value: string): string {
  return value ? `${value[0]?.toUpperCase()}${value.slice(1)}` : value;
}

function formatClock(value: string, milliseconds = false): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    hour12: false,
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: milliseconds ? 3 : undefined,
  });
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return date.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "medium",
  });
}

function formatDuration(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "duration unavailable";
  if (value < 1_000) return `${Math.round(value)}ms`;
  return `${(value / 1_000).toFixed(value < 10_000 ? 2 : 1)}s`;
}

function formatInteger(value: number): string {
  return Math.round(value).toLocaleString();
}

function usd(value: number): string {
  return `$${value.toFixed(6)}`;
}
