import type { SessionGoalItem } from "@/data/session-goals"

type ObjectivePresentation = {
  title: string
  clue: string | null
  revisionLabel: string | null
}

/**
 * The objective strip's reading of the retained goals: the latest goal
 * leads, the catalog objective fills in for legacy sessions, and the
 * revision count shows when an operator replaced the goal.
 */
function projectObjective(
  goals: readonly SessionGoalItem[],
  catalogObjective: string | null,
  canSetGoal: boolean,
  catalogGoalCount: number | null = null
): ObjectivePresentation {
  const ordered = [...goals].sort(
    (left, right) => (left.goal.ordinal ?? 0) - (right.goal.ordinal ?? 0)
  )
  const latest = ordered.at(-1) ?? null
  const title =
    latest?.goal.title?.trim() || catalogObjective?.trim() || "No goal set"
  const clue =
    latest === null && (catalogObjective === null || catalogObjective === "")
      ? canSetGoal
        ? "First message starts the agent"
        : null
      : null
  const revisions = Math.max(ordered.length, catalogGoalCount ?? 0)
  const revisionLabel = revisions > 1 ? `Revision ${revisions}` : null
  return { title, clue, revisionLabel }
}

export { projectObjective, type ObjectivePresentation }
