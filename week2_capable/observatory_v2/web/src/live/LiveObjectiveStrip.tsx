import type { LiveObjectiveContext } from "../contracts";

export function LiveObjectiveStrip({
  compatibilityObjective,
  canSetGoal,
  objective,
  objectiveInitial,
}: {
  compatibilityObjective: string | null;
  canSetGoal: boolean;
  objective: LiveObjectiveContext | null;
  objectiveInitial: LiveObjectiveContext | null;
}) {
  const title = objective?.title ?? compatibilityObjective ?? "No goal set";
  const clue = objective?.clue ?? (
    objective === null
    && compatibilityObjective === null
    && canSetGoal
      ? "First message starts the agent"
      : null
  );
  const revisionLabel = (
    objective !== null
    && objectiveInitial !== null
    && objective.revision > 1
  )
    ? `Revision ${objective.revision}`
    : (
      objective !== null
      && objectiveInitial === null
      && objective.source_kind === "operator"
    )
      ? "Goal replaced"
      : null;
  return (
    <section
      aria-label="Current objective"
      className="live-objective-strip"
      title={objective?.evidence}
    >
      <span>Objective</span>
      <strong>{title}</strong>
      {clue === null ? null : (
        <small>
          {objective?.clue === null || objective?.clue === undefined
            ? clue
            : `Objective clue · ${clue}`}
        </small>
      )}
      {revisionLabel === null ? null : <em>{revisionLabel}</em>}
    </section>
  );
}
