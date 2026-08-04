import type { ObjectivePresentation } from "./objective-model"

type ObjectiveStripProps = {
  objective: ObjectivePresentation
  evidence?: string
}

/**
 * The one line objective banner under the header: label, current goal,
 * optional clue, and the revision marker when the goal was replaced.
 */
function ObjectiveStrip({ objective, evidence }: ObjectiveStripProps) {
  return (
    <section
      aria-label="Current objective"
      title={evidence}
      className="flex min-h-[34px] min-w-0 items-center gap-2.5 border-b border-line bg-[color-mix(in_srgb,var(--surface)_94%,var(--accent))] px-[22px] py-[7px] whitespace-nowrap max-[700px]:px-3.5"
    >
      <span className="text-[9.5px] font-semibold tracking-[0.16em] text-content-quiet uppercase">
        Objective
      </span>
      <strong className="min-w-0 flex-[0_1_auto] truncate text-[12px] font-semibold text-content-primary">
        {objective.title}
      </strong>
      {objective.clue === null ? null : (
        <small className="min-w-0 flex-[1_1000_auto] truncate text-[10.5px] text-content-quiet max-[700px]:hidden">
          {objective.clue}
        </small>
      )}
      {objective.revisionLabel === null ? null : (
        <em className="ml-auto flex-none text-[10.5px] font-bold tracking-[0.06em] text-accent uppercase not-italic">
          {objective.revisionLabel}
        </em>
      )}
    </section>
  )
}

export { ObjectiveStrip, type ObjectiveStripProps }
