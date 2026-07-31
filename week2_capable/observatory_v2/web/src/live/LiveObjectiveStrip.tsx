import type { LiveObjectiveContext } from "../contracts";

export function LiveObjectiveStrip({
  objective,
}: {
  objective: LiveObjectiveContext | null;
}) {
  if (objective === null) return null;
  return (
    <section
      aria-label="Current objective"
      className="live-objective-strip"
      title={objective.evidence}
    >
      <span>Objective</span>
      <strong>{objective.title}</strong>
      {objective.clue === null ? null : <small>{objective.clue}</small>}
      {objective.revision > 1 ? (
        <em>revision {objective.revision}</em>
      ) : null}
    </section>
  );
}
