import {
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  SkipBack,
  SkipForward,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { SessionInvestigation } from "../contracts";
import { SessionReplayMap } from "./SessionReplayMap";
import {
  recordIndexForIteration,
  type SessionSelection,
  type SessionStory,
  type StoryIteration,
  type StoryObjectiveEpoch,
} from "./storyProjection";
import styles from "./SessionMap.module.css";

function cx(...names: string[]): string {
  return names.map((name) => styles[name]).filter(Boolean).join(" ");
}

type Props = {
  investigation: SessionInvestigation;
  story: SessionStory;
  selection: SessionSelection;
  focusedGoalNumber: number | null;
  onGoalSelect: (epoch: StoryObjectiveEpoch) => void;
  onSelect: (selection: SessionSelection) => void;
  onOpenStory: () => void;
};

export function SessionMap({
  investigation,
  story,
  selection,
  focusedGoalNumber,
  onGoalSelect,
  onSelect,
  onOpenStory,
}: Props) {
  const iterations = useMemo(
    () => story.turns.flatMap((turn) => turn.iterations),
    [story.turns],
  );
  const currentIndex = iterations.findIndex((iteration) => (
    iteration.turn === selection.turn
    && iteration.number === selection.iteration
  ));
  const current = currentIndex < 0 ? null : iterations[currentIndex] ?? null;
  const [playing, setPlaying] = useState(false);
  const selectedRowRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (typeof selectedRowRef.current?.scrollIntoView !== "function") return;
    selectedRowRef.current.scrollIntoView({ block: "nearest" });
  }, [current?.id]);

  useEffect(() => {
    if (!playing || currentIndex >= iterations.length - 1) {
      if (currentIndex >= iterations.length - 1) setPlaying(false);
      return undefined;
    }
    const timer = window.setTimeout(() => {
      const next = iterations[currentIndex + 1];
      if (next) onSelect({
        turn: next.turn,
        iteration: next.number,
        recordId: null,
      });
    }, 900);
    return () => window.clearTimeout(timer);
  }, [currentIndex, iterations, onSelect, playing]);

  const choose = (index: number): void => {
    const next = iterations[Math.max(0, Math.min(iterations.length - 1, index))];
    if (next) onSelect({
      turn: next.turn,
      iteration: next.number,
      recordId: null,
    });
  };
  const selectedRecordIndex = recordIndexForIteration(
    investigation.records,
    current?.turn ?? null,
    current?.number ?? null,
  );
  const canGoBack = currentIndex > 0;
  const canGoForward = currentIndex < iterations.length - 1;
  const currentEpoch = story.objectiveEpochs.find(
    (epoch) => epoch.number === current?.objectiveEpoch,
  ) ?? null;
  const goalGroups = useMemo(() => story.objectiveEpochs.map((epoch) => ({
    epoch,
    iterations: iterations
      .map((iteration, index) => ({ index, iteration }))
      .filter(({ iteration }) => iteration.objectiveEpoch === epoch.number),
  })), [iterations, story.objectiveEpochs]);
  const [openGoals, setOpenGoals] = useState<Set<number>>(
    () => new Set(),
  );
  const previousEpochRef = useRef(currentEpoch?.number ?? null);
  useEffect(() => {
    const previous = previousEpochRef.current;
    previousEpochRef.current = currentEpoch?.number ?? null;
    if (
      currentEpoch === null
      || previous === null
      || previous === currentEpoch.number
    ) {
      return;
    }
    setOpenGoals((existing) => {
      if (existing.has(currentEpoch.number)) return existing;
      return new Set([...existing, currentEpoch.number]);
    });
  }, [currentEpoch]);
  const activeNudges = currentEpoch?.nudges.filter(
    (nudge) => Date.parse(nudge.record.at) <= Date.parse(current?.startedAt ?? ""),
  ) ?? [];

  if (current === null) {
    return (
      <div className={cx("session-map-empty")}>
        This session has no retained iteration to replay.
      </div>
    );
  }

  return (
    <section className={cx("session-map-view")} aria-label="Session map replay">
      <div className={cx("session-map-stage")}>
        <SessionReplayMap
          investigation={investigation}
          selectedIndex={selectedRecordIndex}
        />
        <ReplayControls
          canGoBack={canGoBack}
          canGoForward={canGoForward}
          current={current}
          index={currentIndex}
          playing={playing}
          total={iterations.length}
          onFirst={() => choose(0)}
          onLast={() => choose(iterations.length - 1)}
          onNext={() => choose(currentIndex + 1)}
          onPlayingChange={setPlaying}
          onPrevious={() => choose(currentIndex - 1)}
          onScrub={choose}
        />
      </div>
      <aside className={cx("session-iteration-rail")}>
        <header>
          <span className={cx("story-eyebrow")}>Map replay</span>
          <h2>Follow the run in space</h2>
          <p>
            The selected iteration, current room, traveled path, and room
            detail move together.
          </p>
        </header>
        <div className={cx("session-iteration-list")}>
          {goalGroups.map(({ epoch, iterations: goalIterations }) => {
            const expanded = openGoals.has(epoch.number);
            return (
              <section
                aria-label={`Map goal ${epoch.number}: ${epoch.title}`}
                className={cx(
                  "session-map-goal",
                  ...(focusedGoalNumber === epoch.number ? ["is-focused"] : []),
                )}
                key={epoch.id}
              >
                <div className={cx("session-goal-row")}>
                  <button
                    aria-expanded={expanded}
                    aria-label={`Jump to Goal ${epoch.number}: ${epoch.title}`}
                    className={cx("session-goal-select")}
                    type="button"
                    onClick={() => {
                      onGoalSelect(epoch);
                      setOpenGoals((existing) => {
                        const next = new Set(existing);
                        if (next.has(epoch.number)) next.delete(epoch.number);
                        else next.add(epoch.number);
                        return next;
                      });
                    }}
                  >
                    <small>Goal {epoch.number}</small>
                    <span>
                      <strong>{epoch.title}</strong>
                      <small>
                        {goalIterations.length} iteration
                        {goalIterations.length === 1 ? "" : "s"}
                        {" · "}
                        {epoch.nudges.length} nudge
                        {epoch.nudges.length === 1 ? "" : "s"}
                      </small>
                    </span>
                  </button>
                  <button
                    aria-label={`${expanded ? "Collapse" : "Expand"} map Goal ${epoch.number}`}
                    aria-expanded={expanded}
                    className={cx("session-goal-toggle")}
                    type="button"
                    onClick={() => setOpenGoals((existing) => {
                      const next = new Set(existing);
                      if (next.has(epoch.number)) next.delete(epoch.number);
                      else next.add(epoch.number);
                      return next;
                    })}
                  >
                    <ChevronRight aria-hidden="true" size={16} />
                  </button>
                </div>
                {expanded ? goalIterations.map(({ index, iteration }) => (
                  <button
                    aria-current={index === currentIndex ? "step" : undefined}
                    className={cx(
                      "session-iteration-row",
                      ...(index === currentIndex ? ["active"] : []),
                    )}
                    key={iteration.id}
                    ref={index === currentIndex ? selectedRowRef : undefined}
                    type="button"
                    onClick={() => choose(index)}
                  >
                    <span>{iteration.number}</span>
                    <span>
                      <strong>{iteration.title}</strong>
                      <small>{iteration.roomTitle ?? iteration.subtitle}</small>
                    </span>
                    <b>{usd(iteration.costUsd)}</b>
                  </button>
                )) : null}
              </section>
            );
          })}
        </div>
        <div className={cx("session-map-selection")}>
          {currentEpoch ? (
            <span className={cx("session-current-goal")}>
              Goal {currentEpoch.number} · {currentEpoch.title}
              {activeNudges.length > 0
                ? ` · ${activeNudges.length} nudge${activeNudges.length === 1 ? "" : "s"} active`
                : ""}
            </span>
          ) : null}
          <h3>
            Turn {current.turn} · Iteration {current.number}
            {current.roomTitle ? ` · ${current.roomTitle}` : ""}
          </h3>
          <p>
            {formatClock(current.startedAt)} · {current.title}
          </p>
          <button
            type="button"
            onClick={() => {
              onSelect({
                turn: current.turn,
                iteration: current.number,
                recordId: current.responseIds[0]
                  ?? current.records[0]?.id
                  ?? null,
              });
              onOpenStory();
            }}
          >
            Open the complete iteration story →
          </button>
        </div>
      </aside>
    </section>
  );
}

function ReplayControls({
  canGoBack,
  canGoForward,
  current,
  index,
  playing,
  total,
  onFirst,
  onLast,
  onNext,
  onPlayingChange,
  onPrevious,
  onScrub,
}: {
  canGoBack: boolean;
  canGoForward: boolean;
  current: StoryIteration;
  index: number;
  playing: boolean;
  total: number;
  onFirst: () => void;
  onLast: () => void;
  onNext: () => void;
  onPlayingChange: (playing: boolean) => void;
  onPrevious: () => void;
  onScrub: (index: number) => void;
}) {
  return (
    <div className={cx("session-map-replay")}>
      <div className={cx("session-map-transport")}>
        <button
          aria-label="First iteration"
          disabled={!canGoBack}
          type="button"
          onClick={onFirst}
        >
          <SkipBack size={17} />
        </button>
        <button
          aria-label="Previous iteration"
          disabled={!canGoBack}
          type="button"
          onClick={onPrevious}
        >
          <ChevronLeft size={18} />
        </button>
        <button
          aria-label={playing ? "Pause replay" : "Play replay"}
          className={cx("is-play")}
          disabled={!playing && !canGoForward}
          type="button"
          onClick={() => onPlayingChange(!playing)}
        >
          {playing ? <Pause size={17} /> : <Play size={17} />}
        </button>
        <button
          aria-label="Next iteration"
          disabled={!canGoForward}
          type="button"
          onClick={onNext}
        >
          <ChevronRight size={18} />
        </button>
        <button
          aria-label="Last iteration"
          disabled={!canGoForward}
          type="button"
          onClick={onLast}
        >
          <SkipForward size={17} />
        </button>
      </div>
      <input
        aria-label="Replay iteration"
        disabled={total < 2}
        max={Math.max(total - 1, 0)}
        min="0"
        type="range"
        value={index}
        onChange={(event) => onScrub(Number(event.target.value))}
      />
      <div className={cx("session-map-replay-meta")}>
        <strong>
          Turn {current.turn} · Iteration {current.number}
          {" "}({index + 1} of {total})
        </strong>
        <span>
          {formatClock(current.startedAt)}
          {current.roomTitle ? ` · ${current.roomTitle}` : ""}
        </span>
      </div>
    </div>
  );
}

function formatClock(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    hour12: false,
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  });
}

function usd(value: number): string {
  return `$${value.toFixed(6)}`;
}
