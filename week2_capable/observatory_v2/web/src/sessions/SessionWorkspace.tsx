import { MessageSquareText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { SessionInvestigation } from "../contracts";
import { SessionCost } from "./SessionCost";
import { SessionMap } from "./SessionMap";
import { SessionStory } from "./SessionStory";
import {
  iterationKey,
  projectSessionStory,
  type SessionSelection,
  type StoryObjectiveEpoch,
  type SessionView,
} from "./storyProjection";
import styles from "./SessionShell.module.css";

type IncidentContext = {
  annotations: unknown[];
  sourceVersions: Record<string, unknown>;
  redactionPolicy: unknown;
  history: unknown;
};

type Props = {
  investigation: SessionInvestigation | null;
  loading: boolean;
  error: string | null;
  sourceState: "offline" | "recorded";
  incident: IncidentContext;
  onOpenSearch: () => void;
  onOpenRun: (runId: string) => void;
  onSelectionChange?: (recordId: string | null) => void;
};

const views: {
  id: SessionView;
  label: string;
  description: string;
}[] = [
  {
    id: "story",
    label: "Story",
    description: "is the complete chronological record. Expand only as deep as needed.",
  },
  {
    id: "map",
    label: "Map",
    description: "replays the Live spatial view with the iteration that produced each state.",
  },
  {
    id: "cost",
    label: "Cost",
    description: "attributes every amount and returns to the exact response that produced it.",
  },
];

export function SessionsWorkspace({
  investigation,
  loading,
  error,
  sourceState,
  onSelectionChange,
}: Props) {
  const [view, setView] = useState<SessionView>(initialView);
  const [search, setSearch] = useState("");
  const [selection, setSelection] = useState<SessionSelection>(
    initialSelection,
  );
  const [focusedGoalNumber, setFocusedGoalNumber] = useState<number | null>(
    initialGoal,
  );
  const story = useMemo(
    () => investigation === null ? null : projectSessionStory(investigation),
    [investigation],
  );

  useEffect(() => {
    if (story === null || story.turns.length === 0) return;
    const iterationExists = selection.turn !== null
      && selection.iteration !== null
      && story.byIteration.has(iterationKey(
        selection.turn,
        selection.iteration,
      ));
    if (iterationExists) {
      const selectedIteration = story.byIteration.get(iterationKey(
        selection.turn as number,
        selection.iteration as number,
      ));
      if (
        selectedIteration !== undefined
        && focusedGoalNumber === null
      ) {
        setFocusedGoalNumber(selectedIteration.objectiveEpoch);
      }
      return;
    }
    const focusedGoal = story.objectiveEpochs.find(
      (epoch) => epoch.number === focusedGoalNumber,
    ) ?? story.objectiveEpochs.at(-1) ?? null;
    const first = focusedGoal?.firstIteration
      ?? story.turns[0]?.iterations[0]
      ?? null;
    setFocusedGoalNumber(focusedGoal?.number ?? null);
    setSelection({
      turn: first?.turn ?? null,
      iteration: first?.number ?? null,
      recordId: null,
    });
  }, [
    focusedGoalNumber,
    selection.iteration,
    selection.turn,
    story,
  ]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("view", view);
    url.searchParams.delete("lens");
    url.searchParams.delete("record");
    if (selection.turn === null) url.searchParams.delete("turn");
    else url.searchParams.set("turn", String(selection.turn));
    if (selection.iteration === null) url.searchParams.delete("iteration");
    else url.searchParams.set("iteration", String(selection.iteration));
    if (selection.recordId === null) url.searchParams.delete("event");
    else url.searchParams.set("event", selection.recordId);
    if (focusedGoalNumber === null) url.searchParams.delete("goal");
    else url.searchParams.set("goal", String(focusedGoalNumber));
    window.history.replaceState(null, "", url);
  }, [focusedGoalNumber, selection, view]);

  useEffect(() => {
    onSelectionChange?.(selection.recordId);
  }, [onSelectionChange, selection.recordId]);

  if (loading) {
    return <WorkspaceState text="Building the complete session story…" />;
  }
  if (error !== null) {
    return <WorkspaceState error text={error} />;
  }
  if (investigation === null || story === null) {
    return (
      <WorkspaceState text="Select a recorded session to read its complete run." />
    );
  }

  const activeView = views.find((candidate) => candidate.id === view)
    ?? views[0];
  const duration = investigation.run.duration_ms
    ?? sessionDuration(investigation);
  const iterationCount = story.turns.reduce(
    (total, turn) => total + turn.iterations.length,
    0,
  );
  const focusedGoal = story.objectiveEpochs.find(
    (epoch) => epoch.number === focusedGoalNumber,
  ) ?? story.objectiveEpochs.at(-1) ?? null;
  const handleSelect = (next: SessionSelection): void => {
    if (next.turn !== null && next.iteration !== null) {
      const iteration = story.byIteration.get(iterationKey(
        next.turn,
        next.iteration,
      ));
      if (iteration !== undefined) {
        setFocusedGoalNumber(iteration.objectiveEpoch);
      }
    }
    setSelection(next);
  };
  const handleGoalSelect = (epoch: StoryObjectiveEpoch): void => {
    setFocusedGoalNumber(epoch.number);
    setSelection({
      turn: epoch.firstIteration?.turn ?? epoch.record?.turn ?? null,
      iteration: epoch.firstIteration?.number
        ?? epoch.record?.iteration
        ?? null,
      recordId: null,
    });
  };

  return (
    <main className={styles.observatory}>
      <section className={styles.runHeader}>
        <div className={styles.runHeaderInner}>
          <div className={styles.runCopy}>
            <span className={styles.eyebrow}>
              {focusedGoal === null
                ? "Recorded session"
                : `Goal ${focusedGoal.number} of ${story.objectiveEpochs.length}`}
            </span>
            <h1>{sentenceCase(
              focusedGoal?.title
                ?? investigation.objective
                ?? investigation.run.label,
            )}</h1>
            <p>
              {formatRunSubtitle(investigation)}
              {" · "}
              {sourceState === "offline"
                ? "verified offline capsule"
                : captureLabel(investigation)}
            </p>
          </div>
          <dl className={styles.runMetrics}>
            <div className={styles.runMetric}>
              <dt>Duration</dt>
              <dd>{formatDuration(duration)}</dd>
            </div>
            <div className={styles.runMetric}>
              <dt>Iterations</dt>
              <dd>{formatInteger(iterationCount)}</dd>
            </div>
            <div className={`${styles.runMetric} ${styles.costMetric}`}>
              <dt>Total cost</dt>
              <dd>{usd(investigation.cost.total_usd)}</dd>
            </div>
          </dl>
        </div>
      </section>

      <div className={styles.viewBar}>
        <nav className={styles.viewSwitch} aria-label="Session views">
          {views.map((item) => {
            return (
              <button
                aria-current={view === item.id ? "page" : undefined}
                className={view === item.id ? styles.active : undefined}
                key={item.id}
                type="button"
                onClick={() => {
                  if (item.id === "story") {
                    setSelection((current) => ({
                      ...current,
                      recordId: null,
                    }));
                  }
                  setView(item.id);
                }}
              >
                {item.label}
              </button>
            );
          })}
        </nav>
        <p className={styles.viewDescription}>
          <strong>{activeView.label}</strong> {activeView.description}
        </p>
        <span className={styles.viewSpacer} />
        {view === "story" ? (
          <input
            aria-label="Filter Story evidence"
            className={styles.search}
            placeholder="Filter Story evidence"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        ) : null}
      </div>

      <div className={styles.viewContent}>
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
  );
}

function WorkspaceState({
  error = false,
  text,
}: {
  error?: boolean;
  text: string;
}) {
  return (
    <main className={`${styles.workspaceState}${error ? ` ${styles.error}` : ""}`}>
      <MessageSquareText aria-hidden="true" size={28} />
      <strong>{error ? "Session unavailable" : "Sessions"}</strong>
      <p>{text}</p>
    </main>
  );
}

function initialView(): SessionView {
  const query = new URL(window.location.href).searchParams;
  const value = query.get("view");
  if (value === "story" || value === "map" || value === "cost") return value;
  const legacy = query.get("lens");
  if (legacy === "map" || legacy === "cost") return legacy;
  return "story";
}

function initialSelection(): SessionSelection {
  const query = new URL(window.location.href).searchParams;
  const rawIteration = query.get("iteration");
  const iteration = rawIteration === null ? null : Number(rawIteration);
  return {
    turn: numericQuery(query.get("turn")),
    iteration: Number.isFinite(iteration) ? iteration : null,
    recordId: query.get("event") ?? query.get("record"),
  };
}

function initialGoal(): number | null {
  return numericQuery(new URL(window.location.href).searchParams.get("goal"));
}

function numericQuery(value: string | null): number | null {
  if (value === null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatRunSubtitle(investigation: SessionInvestigation): string {
  const start = investigation.run.created_at
    ?? investigation.records[0]?.at
    ?? "";
  const end = investigation.run.ended_at
    ?? investigation.records.at(-1)?.at
    ?? "";
  const lifecycle = (investigation.run.lifecycle
    ?? (investigation.run.success ? "completed" : "stopped")).toLowerCase();
  const reason = investigation.run.stop_reason?.trim().toLowerCase() ?? "";
  const outcome = lifecycle === "stopped" && reason === "cooperative"
    ? "stopped cooperatively"
    : reason
      ? `${lifecycle}: ${reason}`
      : lifecycle;
  return `${formatTimestamp(start)} · ${outcome} at ${formatTime(end)}`;
}

function captureLabel(investigation: SessionInvestigation): string {
  if (investigation.capture_gaps.length > 0) {
    return [
      "Retained evidence with",
      investigation.capture_gaps.length,
      `explicit gap${investigation.capture_gaps.length === 1 ? "" : "s"}`,
    ].join(" ");
  }
  const status = investigation.run.capture_status?.trim();
  if (status) return `${capitalize(status)} evidence capture`;
  return investigation.capture_gaps.length === 0
    ? "Complete retained evidence"
    : "Retained evidence with explicit gaps";
}

function sessionDuration(investigation: SessionInvestigation): number | null {
  const stamps = investigation.records
    .map((record) => Date.parse(record.at))
    .filter(Number.isFinite);
  if (stamps.length < 2) return null;
  return Math.max(...stamps) - Math.min(...stamps);
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "Time unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date).replace(/, (?=\d{1,2}:)/, " at ");
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "time unavailable";
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function formatDuration(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "Unavailable";
  if (value < 1_000) return `${Math.round(value)} ms`;
  const seconds = value / 1_000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${minutes}m ${String(remainder).padStart(2, "0")}s`;
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function usd(value: number): string {
  return `$${value.toFixed(6)}`;
}

function capitalize(value: string): string {
  return value ? `${value[0]?.toUpperCase()}${value.slice(1)}` : value;
}

function sentenceCase(value: string): string {
  return value ? `${value[0]?.toUpperCase()}${value.slice(1)}` : value;
}
