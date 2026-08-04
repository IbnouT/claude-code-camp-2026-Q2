import { selectedSession, sessionLifecycle } from "@/app/session-context-model"
import { useSessionCatalog } from "@/data/session-catalog"

import { LiveShell } from "./live-shell"

type LiveRouteScreenProps = {
  playerId: string | undefined
  sessionId: string | undefined
}

/**
 * The Live route: resolves the observed session from the catalog and
 * mounts the workspace shell for it.
 */
function LiveRouteScreen({ playerId, sessionId }: LiveRouteScreenProps) {
  const catalog = useSessionCatalog({ playerId, sessionId })
  const data =
    catalog.result.status === "loading" || catalog.result.status === "error"
      ? undefined
      : catalog.result.data
  const selected =
    data === undefined ? null : selectedSession(data, { playerId, sessionId })

  return (
    <LiveShell
      sessionId={selected?.id}
      catalogObjective={selected?.objective ?? null}
      sessionRunning={
        selected !== null && sessionLifecycle(selected) === "running"
      }
    />
  )
}

export { LiveRouteScreen, type LiveRouteScreenProps }
