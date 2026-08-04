import { describe, expect, it } from "vitest"

import {
  formatSessionDate,
  latestSessions,
  orderedSessions,
  selectedSession,
  sessionLifecycle,
  sessionMatches,
} from "@/app/session-context-model"
import type { SessionCatalog, SessionCatalogItem } from "@/data/session-catalog"

function item(
  id: string,
  overrides: Partial<SessionCatalogItem> = {}
): SessionCatalogItem {
  return {
    capture_status: "complete",
    character: `Character ${id}`,
    control_available: false,
    control_state: null,
    created_at: "2026-08-03T10:00:00Z",
    ended_at: "2026-08-03T10:30:00Z",
    event_count: 20,
    turn_count: null,
    iteration_count: null,
    gateway_session_id: `gateway-${id}`,
    goal_count: 2,
    id,
    latest_seq: 20,
    legacy: false,
    live: false,
    nudge_count: 1,
    objective: `Objective ${id}`,
    player_id: `player-${id}`,
    projection_gaps: [],
    projection_status: "available",
    state: "stopped",
    stop_mode: "graceful",
    updated_at: "2026-08-03T10:30:00Z",
    ...overrides,
  }
}

function catalog(sessions: SessionCatalogItem[]): SessionCatalog {
  return {
    capture_gaps: [],
    completeness: "complete",
    continuation_cursor: null,
    players: sessions.map((session) => ({
      id: session.player_id,
      label: session.character,
      start_available: false,
    })),
    resource_id: "session-catalog",
    resource_version: 1,
    sessions,
    source_cursor: "cursor-1",
    source_refs: ["gateway"],
  }
}

describe("selected session context model", () => {
  it("orders running sessions first and resolves an exact deep link", () => {
    const stopped = item("stopped")
    const live = item("live", {
      control_available: true,
      control_state: "ready",
      ended_at: null,
      live: true,
      state: "running",
      updated_at: "2026-08-03T09:00:00Z",
    })
    const data = catalog([stopped, live])

    expect(orderedSessions(data.sessions)).toEqual([live, stopped])
    expect(
      selectedSession(data, {
        playerId: stopped.player_id,
        sessionId: stopped.id,
      })
    ).toBe(stopped)
    expect(selectedSession(data, {})).toBe(live)
  })

  it("maps direct lifecycle and capability-relevant source states", () => {
    expect(sessionLifecycle(item("running", { live: true }))).toBe("running")
    expect(sessionLifecycle(item("checking", { state: "draining" }))).toBe(
      "checking"
    )
    // The live flag stays true through transitions and must not win.
    expect(
      sessionLifecycle(item("draining", { live: true, state: "draining" }))
    ).toBe("checking")
    expect(
      sessionLifecycle(item("starting", { live: true, state: "starting" }))
    ).toBe("checking")
    expect(
      sessionLifecycle(item("live-failed", { live: true, state: "failed" }))
    ).toBe("failed")
    // Quarantine blocks agent commands, never a healthy running state.
    expect(
      sessionLifecycle(
        item("quarantined", { live: true, state: "quarantined" })
      )
    ).toBe("failed")
    expect(sessionLifecycle(item("failed", { state: "failed" }))).toBe("failed")
    expect(sessionLifecycle(item("complete", { state: "complete" }))).toBe(
      "succeeded"
    )
    expect(sessionLifecycle(item("stopped"))).toBe("stopped")
    expect(
      sessionLifecycle(
        item("idle", { ended_at: null, state: "waiting", stop_mode: null })
      )
    ).toBe("idle")
  })

  it("recovers player-only, missing, mismatch, and detail-path identities", () => {
    const alphaLatest = item("alpha-latest", {
      player_id: "alpha",
      updated_at: "2026-08-03T12:00:00Z",
    })
    const alphaOlder = item("alpha-older", {
      player_id: "alpha",
      updated_at: "2026-08-03T11:00:00Z",
    })
    const beta = item("beta-session", {
      live: true,
      player_id: "beta",
      state: "running",
    })
    const data = catalog([alphaOlder, beta, alphaLatest])

    expect(selectedSession(data, { playerId: "alpha" })).toBe(alphaLatest)
    expect(
      selectedSession(data, {
        playerId: "alpha",
        sessionId: "missing-session",
      })
    ).toBe(alphaLatest)
    expect(selectedSession(data, { sessionId: "missing-session" })).toBe(beta)
    expect(
      selectedSession(data, {
        playerId: "alpha",
        sessionId: beta.id,
      })
    ).toBe(alphaLatest)
    expect(
      selectedSession(data, {
        detailSessionId: beta.id,
        playerId: "alpha",
        sessionId: alphaOlder.id,
      })
    ).toBe(beta)
    expect(
      selectedSession(data, {
        detailSessionId: "missing-detail",
        playerId: "alpha",
      })
    ).toBe(alphaLatest)
  })

  it("bounds selected-player latest sessions and searches displayed fields", () => {
    const sessions = Array.from({ length: 7 }, (_, index) =>
      item(`session-${index}`, {
        player_id: "selected-player",
        objective: index === 4 ? "Recover the crystal" : `Objective ${index}`,
        updated_at: `2026-08-03T10:${String(index).padStart(2, "0")}:00Z`,
      })
    )
    const otherPlayer = item("other-running", {
      live: true,
      player_id: "other-player",
      state: "running",
    })
    const data = catalog([...sessions, otherPlayer])
    const selected = sessions[6]

    expect(latestSessions(data, selected)).toHaveLength(5)
    expect(latestSessions(data, selected)).not.toContain(otherPlayer)
    expect(sessionMatches(sessions[4], "crystal")).toBe(true)
    expect(sessionMatches(sessions[4], "session-4")).toBe(true)
    expect(sessionMatches(sessions[4], "stopped")).toBe(true)
    expect(
      sessionMatches(
        sessions[4],
        formatSessionDate(sessions[4].updated_at).slice(0, 6)
      )
    ).toBe(true)
    expect(sessionMatches(sessions[4], "missing")).toBe(false)
  })
})
