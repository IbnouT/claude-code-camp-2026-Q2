import type { PlayerOption, SessionCatalogItem } from "@/data/session-catalog"
import type { VitalsFields } from "@/data/session-vitals"

type ResetMode = "none" | "temple" | "baseline"

type RosterRow = {
  id: string
  label: string
  startAvailable: boolean
  latest: SessionCatalogItem | undefined
}

type StartIntent = {
  playerId: string
  objective: string
  reset: ResetMode
}

/** Live sessions first, then most recently updated. */
function sortSessions(
  sessions: readonly SessionCatalogItem[]
): SessionCatalogItem[] {
  return [...sessions].sort((first, second) => {
    if (first.live !== second.live) return first.live ? -1 : 1
    return Date.parse(second.updated_at) - Date.parse(first.updated_at)
  })
}

/**
 * Group sessions by player into roster rows, each player's
 * `latest` is their live session if one exists, else their newest session.
 * `start_available` is authoritative from the backend.
 */
function buildRoster(
  players: readonly PlayerOption[],
  sessions: readonly SessionCatalogItem[]
): RosterRow[] {
  const byPlayer = new Map<string, SessionCatalogItem[]>()
  for (const session of sessions) {
    const owned = byPlayer.get(session.player_id) ?? []
    owned.push(session)
    byPlayer.set(session.player_id, owned)
  }
  const rows = players.map((player) => {
    const owned = sortSessions(byPlayer.get(player.id) ?? [])
    return {
      id: player.id,
      label: player.label,
      startAvailable: player.start_available,
      latest: owned[0],
    }
  })
  return rows.sort((first, second) => {
    const firstLive = first.latest?.live === true
    const secondLive = second.latest?.live === true
    if (firstLive !== secondLive) return firstLive ? -1 : 1
    return (
      Date.parse(second.latest?.updated_at ?? "1970-01-01") -
      Date.parse(first.latest?.updated_at ?? "1970-01-01")
    )
  })
}

/** Relative time: today HH:MM, yesterday, N days ago. */
function when(iso: string): string {
  const date = new Date(iso)
  const age = Date.now() - date.getTime()
  if (age < 86_400_000 && date.toDateString() === new Date().toDateString()) {
    const time = date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    })
    return `today ${time}`
  }
  const days = Math.max(1, Math.round(age / 86_400_000))
  return days === 1 ? "yesterday" : `${days} days ago`
}

/** Duration label from created/ended timestamps. */
function duration(session: SessionCatalogItem): string {
  const end = new Date(session.ended_at ?? session.updated_at).getTime()
  const start = new Date(session.created_at).getTime()
  const seconds = Math.max(0, Math.round((end - start) / 1000))
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

/** Stop-mode annotation for the recorded-session list. */
function stopAnnotation(session: SessionCatalogItem): string {
  if (session.stop_mode === "forced_after_grace") {
    return "stopped · forced after grace · "
  }
  if (session.stop_mode === "cooperative") {
    return "stopped · "
  }
  return ""
}

function endedSessions(
  sessions: readonly SessionCatalogItem[],
  playerId: string | undefined,
  allPlayers: boolean
): SessionCatalogItem[] {
  return sortSessions(
    sessions.filter(
      (session) =>
        !session.live && (allPlayers || session.player_id === playerId)
    )
  )
}

/** First numeric observation among the given field names, if any. */
function observedNumber(
  fields: VitalsFields | undefined,
  ...names: string[]
): number | null {
  if (fields === undefined) return null
  for (const name of names) {
    const value = fields[name]?.value
    if (typeof value === "number") return value
  }
  return null
}

export {
  buildRoster,
  observedNumber,
  duration,
  endedSessions,
  sortSessions,
  stopAnnotation,
  when,
}
export type { ResetMode, RosterRow, StartIntent }
