import { useState } from "react"

import { useLiveSessionLiveness } from "@/data/live-session-liveness"
import { useSessionGoals } from "@/data/session-goals"
import { cn } from "@/lib/utils"

import { ObjectiveStrip } from "./objective-strip"
import { projectObjective } from "./objective-model"

type LiveShellProps = {
  sessionId: string | undefined
  catalogObjective: string | null
  sessionRunning: boolean
}

/**
 * The Live workspace: the map stage fills the screen, the evidence rail
 * docks right, the causal timeline docks along the bottom. Each region
 * arrives with its own section of the build, the geometry is complete.
 */
function LiveShell({
  sessionId,
  catalogObjective,
  sessionRunning,
}: LiveShellProps) {
  useLiveSessionLiveness(sessionId)
  const goals = useSessionGoals(sessionId)
  const [railOpen, setRailOpen] = useState(
    () => typeof window === "undefined" || window.innerWidth > 700
  )
  const items = goals.data?.items ?? []
  const objective = projectObjective(items, catalogObjective, sessionRunning)
  const evidence = items.at(-1)?.goal.source_ref ?? undefined

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ObjectiveStrip objective={objective} evidence={evidence} />
      <main
        aria-label="Live workspace"
        className="relative min-h-0 flex-1 overflow-hidden bg-[image:radial-gradient(1200px_600px_at_60%_30%,var(--live-workspace-glow),transparent)] bg-canvas [--live-rail-width:320px] [--live-timeline-height:110px] max-[1040px]:[--live-rail-width:260px] max-[700px]:[--live-rail-width:0px] max-[700px]:[--live-timeline-height:64px]"
      >
        <div
          aria-label="Learned world map"
          className="absolute top-0 right-(--live-rail-width) bottom-(--live-timeline-height) left-0 grid min-h-0 min-w-0 overflow-hidden max-[700px]:right-0"
        >
          <p
            role="status"
            className="place-self-center text-[13px] text-content-muted"
          >
            The learned world arrives with the map section.
          </p>
        </div>
        <aside
          aria-label="Live evidence rail"
          className={cn(
            "absolute top-0 right-0 bottom-(--live-timeline-height) z-[8] w-(--live-rail-width) overflow-y-auto border-l border-line bg-surface",
            "max-[700px]:block max-[700px]:w-[min(86vw,320px)] max-[700px]:shadow-[-18px_0_36px_rgb(0_0_0/30%)] max-[700px]:transition-transform max-[700px]:duration-180 max-[700px]:ease-[ease]",
            railOpen
              ? "max-[700px]:translate-x-0"
              : "max-[700px]:translate-x-full"
          )}
        >
          <button
            type="button"
            aria-expanded={railOpen}
            aria-label={railOpen ? "Close evidence rail" : "Open evidence rail"}
            className="hidden max-[700px]:absolute max-[700px]:top-3 max-[700px]:-left-[68px] max-[700px]:grid max-[700px]:h-[34px] max-[700px]:w-[68px] max-[700px]:place-items-center max-[700px]:rounded-l-[9px] max-[700px]:border max-[700px]:border-r-0 max-[700px]:border-line max-[700px]:bg-surface max-[700px]:text-[9px] max-[700px]:font-semibold max-[700px]:tracking-[0.08em] max-[700px]:text-accent max-[700px]:uppercase"
            onClick={() => setRailOpen((open) => !open)}
          >
            Evidence
          </button>
          <p className="mx-4 mt-[42px] text-[11px] text-content-quiet">
            Retained evidence arrives with the rail section.
          </p>
        </aside>
        <section
          aria-label="Causal timeline"
          className="absolute right-0 bottom-0 left-0 z-[8] h-(--live-timeline-height) border-t border-line bg-surface px-[18px] py-3 max-[700px]:px-3"
        >
          <div className="grid h-full place-items-center text-[10px] text-content-quiet">
            The causal timeline arrives with its section.
          </div>
        </section>
      </main>
    </div>
  )
}

export { LiveShell, type LiveShellProps }
