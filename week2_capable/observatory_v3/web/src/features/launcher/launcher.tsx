import { useNavigate, useSearch } from "@tanstack/react-router"
import { useState } from "react"

import { useSessionCatalog } from "@/data/session-catalog"
import { useSessionVitals } from "@/data/session-vitals"
import { useStartCommand } from "@/data/start-command"

import { LauncherView, type LauncherStatus } from "./launcher-view"
import { buildRoster, type StartIntent } from "./launcher-model"

function toStatus(status: string): LauncherStatus {
  if (status === "loading") {
    return "pending"
  }
  if (status === "error") {
    return "error"
  }
  return "ready"
}

/**
 * The Launcher route: the roster and start experience over the bounded
 * session catalog. Start submits a durable command, follows its receipt to a
 * terminal state, then opens Live for the resulting session.
 */
function Launcher() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as {
    player?: string
    load?: number | string
  }
  const catalog = useSessionCatalog()
  const startCommand = useStartCommand()
  const result = catalog.result
  const data = "data" in result ? result.data : undefined
  const [selectedId, setSelectedId] = useState<string | undefined>(
    () => search.player
  )
  const roster = buildRoster(data?.players ?? [], data?.sessions ?? [])
  const selected = roster.find((row) => row.id === selectedId) ?? roster[0]
  const vitalsQuery = useSessionVitals(selected?.latest?.id)

  async function handleStart(intent: StartIntent) {
    if (selected === undefined || !selected.startAvailable) {
      return
    }
    const command = await startCommand.mutateAsync({
      idempotency_key: crypto.randomUUID(),
      actor: "operator",
      player_id: intent.playerId,
      instruction: intent.objective === "" ? null : intent.objective,
      reset: intent.reset,
    })
    await catalog.refresh()
    if (command.result_session_id !== null) {
      await navigate({
        to: "/live",
        search: {
          player: command.player_id,
          session: command.result_session_id,
          view: "overview",
        },
      })
    }
  }

  return (
    <LauncherView
      status={toStatus(result.status)}
      players={data?.players ?? []}
      sessions={data?.sessions ?? []}
      onStart={(intent) => {
        void handleStart(intent)
      }}
      onRetry={() => {
        void catalog.refresh()
      }}
      starting={startCommand.isPending}
      startError={startCommand.isError ? startCommand.error.message : undefined}
      selectedId={selected?.id}
      onSelectPlayer={setSelectedId}
      vitals={
        vitalsQuery.data === undefined
          ? undefined
          : {
              playerId: vitalsQuery.data.player_id,
              fields: vitalsQuery.data.fields,
            }
      }
      initialLoadOpen={search.load !== undefined}
    />
  )
}

export { Launcher }
