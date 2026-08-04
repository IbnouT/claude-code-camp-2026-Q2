import type { SessionCatalog, SessionCatalogItem } from "@/data/session-catalog"

type ContextIdentity = {
  detailSessionId?: string
  playerId?: string
  sessionId?: string
}

type Lifecycle =
  "checking" | "failed" | "idle" | "running" | "stopped" | "succeeded"

function sessionLifecycle(session: SessionCatalogItem): Lifecycle {
  // The state classifies before the live flag: live stays true through
  // transitions like draining, and those must not read as running.
  const state = session.state.toLowerCase()
  if (state.includes("fail") || state.includes("quarantine")) {
    return "failed"
  }
  if (
    state.includes("check") ||
    state.includes("drain") ||
    state.includes("start")
  ) {
    return "checking"
  }
  if (state.includes("success") || state.includes("complete")) {
    return "succeeded"
  }
  if (session.live) return "running"
  // A capture fault marks an ended session's evidence, never a running
  // session's lifecycle.
  if (session.projection_status === "fault") return "failed"
  if (state.includes("stop") || session.ended_at !== null) return "stopped"
  return "idle"
}

function orderedSessions(
  sessions: readonly SessionCatalogItem[]
): SessionCatalogItem[] {
  return [...sessions].sort((left, right) => {
    if (left.live !== right.live) return left.live ? -1 : 1
    return Date.parse(right.updated_at) - Date.parse(left.updated_at)
  })
}

function selectedSession(
  catalog: SessionCatalog,
  identity: ContextIdentity
): SessionCatalogItem | null {
  const ordered = orderedSessions(catalog.sessions)
  if (identity.detailSessionId !== undefined) {
    const pathSession = ordered.find(
      (session) => session.id === identity.detailSessionId
    )
    if (pathSession !== undefined) return pathSession
    return identity.playerId === undefined
      ? (ordered[0] ?? null)
      : (ordered.find((session) => session.player_id === identity.playerId) ??
          null)
  }

  if (identity.playerId !== undefined) {
    const playerSessions = ordered.filter(
      (session) => session.player_id === identity.playerId
    )
    const exact =
      identity.sessionId === undefined
        ? undefined
        : playerSessions.find((session) => session.id === identity.sessionId)
    return exact ?? playerSessions[0] ?? null
  }

  const exact =
    identity.sessionId === undefined
      ? undefined
      : ordered.find((session) => session.id === identity.sessionId)
  return exact ?? ordered[0] ?? null
}

function latestSessions(
  catalog: SessionCatalog,
  selected: SessionCatalogItem | null
): SessionCatalogItem[] {
  return orderedSessions(catalog.sessions)
    .filter(
      (session) =>
        session.id !== selected?.id &&
        (selected === null || session.player_id === selected.player_id)
    )
    .slice(0, 5)
}

function formatSessionDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "time unavailable"
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date)
}

function sessionMatches(session: SessionCatalogItem, query: string): boolean {
  const normalized = query.trim().toLowerCase()
  if (normalized.length === 0) return true

  return [
    session.id,
    session.player_id,
    session.character,
    session.objective ?? "",
    session.state,
    sessionLifecycle(session),
    formatSessionDate(session.updated_at),
  ].some((value) => value.toLowerCase().includes(normalized))
}

function shortSessionId(sessionId: string): string {
  return sessionId.length > 12 ? sessionId.slice(0, 8) : sessionId
}

export {
  formatSessionDate,
  latestSessions,
  orderedSessions,
  selectedSession,
  sessionLifecycle,
  sessionMatches,
  shortSessionId,
  type ContextIdentity,
  type Lifecycle,
}
