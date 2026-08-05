import { useNavigate } from "@tanstack/react-router"
import { useCallback, useState } from "react"

import { useLiveActions } from "@/app/live-actions-context"
import { useSessionCatalog } from "@/data/session-catalog"
import { useSessionInvestigation } from "@/data/session-investigation"
import { AskDialog } from "@/features/live/ask-dialog"

import { SessionWorkspace, type WorkspaceParams } from "./session-workspace"

type SessionRouteScreenProps = {
  sessionId: string
  initialParams: WorkspaceParams
}

/**
 * The recorded session route: resolves the session, loads its
 * investigation, and mounts the workspace with the Ask dialog.
 */
function SessionRouteScreen({
  sessionId,
  initialParams,
}: SessionRouteScreenProps) {
  const catalog = useSessionCatalog({ sessionId })
  const dialogs = useLiveActions()
  const navigate = useNavigate()
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(
    initialParams.event
  )

  const data =
    catalog.result.status === "loading" || catalog.result.status === "error"
      ? undefined
      : catalog.result.data
  const selected =
    data?.sessions.find((session) => session.id === sessionId) ?? null
  const investigation = useSessionInvestigation(sessionId, {
    live: selected?.live === true,
  })

  const onParamsChange = useCallback(
    (params: WorkspaceParams) => {
      void navigate({
        to: ".",
        replace: true,
        // The reading position writes back silently, never as a jump.
        resetScroll: false,
        search: (previous: Record<string, unknown>) => ({
          ...previous,
          view: params.view,
          turn: params.turn ?? undefined,
          iteration: params.iteration ?? undefined,
          event: params.event ?? undefined,
          goal: params.goal ?? undefined,
        }),
      })
    },
    [navigate]
  )

  const investigationError =
    catalog.result.status === "error"
      ? "Sessions unavailable"
      : investigation.isError
        ? investigation.error instanceof Error
          ? investigation.error.message
          : "Session unavailable"
        : null

  return (
    <>
      <SessionWorkspace
        investigation={investigation.data?.investigation ?? null}
        loading={investigation.isPending && investigationError === null}
        error={investigationError}
        initialParams={initialParams}
        onParamsChange={onParamsChange}
        onSelectionChange={setSelectedRecordId}
      />
      {selected === null ? null : (
        <AskDialog
          open={dialogs.askOpen}
          onClose={dialogs.closeAsk}
          playerId={selected.player_id}
          sessionId={selected.id}
          selectedRecordId={selectedRecordId}
        />
      )}
    </>
  )
}

export { SessionRouteScreen, type SessionRouteScreenProps }
