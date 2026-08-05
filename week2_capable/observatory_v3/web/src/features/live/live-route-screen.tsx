import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect } from "react"

import { useLiveActions } from "@/app/live-actions-context"
import { selectedSession, sessionLifecycle } from "@/app/session-context-model"
import { useLiveView } from "@/data/live-view"
import { useSessionCatalog } from "@/data/session-catalog"

import { AskDialog } from "./ask-dialog"
import { LiveShell } from "./live-shell"
import { MessageAgentDialog } from "./message-agent-dialog"

type LiveRouteScreenProps = {
  playerId: string | undefined
  sessionId: string | undefined
  through: number | null
  room: string | null
}

/**
 * The Live route: resolves the observed session from the catalog and
 * mounts the workspace shell for it.
 */
function LiveRouteScreen({
  playerId,
  sessionId,
  through,
  room,
}: LiveRouteScreenProps) {
  const catalog = useSessionCatalog({ playerId, sessionId })
  const dialogs = useLiveActions()
  const navigate = useNavigate()
  const onSelectRoom = useCallback(
    (roomId: string | null) => {
      void navigate({
        to: ".",
        replace: true,
        search: (previous: Record<string, unknown>) => ({
          ...previous,
          room: roomId ?? undefined,
        }),
      })
    },
    [navigate]
  )
  const onSelectThrough = useCallback(
    (sequence: number | null) => {
      void navigate({
        to: ".",
        replace: true,
        search: (previous: Record<string, unknown>) => ({
          ...previous,
          through: sequence ?? undefined,
        }),
      })
    },
    [navigate]
  )
  const data =
    catalog.result.status === "loading" || catalog.result.status === "error"
      ? undefined
      : catalog.result.data
  const selected =
    data === undefined ? null : selectedSession(data, { playerId, sessionId })
  const running = selected !== null && sessionLifecycle(selected) === "running"
  // The same query the shell renders from, so the drawer adds no fetch.
  const liveView = useLiveView(selected?.id, through)
  const view = liveView.data?.view ?? null

  const { openAsk, closeAsk } = dialogs
  useEffect(() => {
    if (selected === null) return
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        openAsk()
      }
      if (event.key === "Escape") {
        closeAsk()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [selected, openAsk, closeAsk])

  return (
    <>
      <LiveShell
        sessionId={selected?.id}
        catalogObjective={selected?.objective ?? null}
        sessionRunning={running}
        captureStatus={selected?.capture_status ?? null}
        through={through}
        onSelectThrough={onSelectThrough}
        selectedRoomId={room}
        onSelectRoom={onSelectRoom}
      />
      {selected === null ? null : (
        <>
          <AskDialog
            open={dialogs.askOpen}
            onClose={dialogs.closeAsk}
            playerId={selected.player_id}
            sessionId={selected.id}
          />
          {view === null ? null : (
            <MessageAgentDialog
              open={dialogs.messageOpen}
              onClose={dialogs.closeMessage}
              playerId={selected.player_id}
              sessionId={selected.id}
              sessionRunning={running}
              controlAvailable={selected.control_available === true}
              objectiveAvailable={
                view.objective_context !== null || view.objective !== null
              }
              followingLive={view.following_live}
              selectedSequence={view.through_sequence}
              messages={view.operator_messages}
            />
          )}
        </>
      )}
    </>
  )
}

export { LiveRouteScreen, type LiveRouteScreenProps }
