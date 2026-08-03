import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SessionSelector } from "@/app/session-selector"
import type { SessionCatalog, SessionCatalogItem } from "@/data/session-catalog"

afterEach(cleanup)

const selectorControls = {
  isLoadingAllSessions: false,
  loadAllSessions: async () => {},
  onSelectPlayer: () => {},
  playerComplete: true,
} as const

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
  const players = new Map(
    sessions.map((session) => [
      session.player_id,
      { id: session.player_id, label: session.character },
    ])
  )
  return {
    capture_gaps: [],
    completeness: "complete",
    continuation_cursor: null,
    players: [...players.values()],
    resource_id: "session-catalog",
    resource_version: 1,
    sessions,
    source_cursor: "cursor-1",
    source_refs: ["gateway"],
  }
}

describe("shared session selector", () => {
  it("renders direct loading, reconnecting, and error states", async () => {
    const user = userEvent.setup()
    const refresh = vi.fn<() => Promise<void>>().mockResolvedValue(undefined)
    const view = render(
      <SessionSelector
        {...selectorControls}
        catalogResult={{ status: "loading" }}
        selected={null}
        onRefresh={refresh}
        onSelect={vi.fn<(session: SessionCatalogItem) => void>()}
      />
    )

    await user.click(screen.getByRole("button", { name: /select player/i }))
    expect(screen.getByText("Loading sessions…")).toBeInTheDocument()

    view.rerender(
      <SessionSelector
        {...selectorControls}
        catalogResult={{ data: undefined, status: "reconnecting" }}
        selected={null}
        onRefresh={refresh}
        onSelect={vi.fn<(session: SessionCatalogItem) => void>()}
      />
    )
    expect(
      screen.getByText("Reconnecting to the session catalog…")
    ).toBeInTheDocument()

    view.rerender(
      <SessionSelector
        {...selectorControls}
        catalogResult={{
          error: new Error("offline") as never,
          status: "error",
        }}
        selected={null}
        onRefresh={refresh}
        onSelect={vi.fn<(session: SessionCatalogItem) => void>()}
      />
    )
    expect(screen.getByText("Session catalog unavailable.")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Try again" }))
    expect(refresh).toHaveBeenCalledOnce()

    const emptyCatalog = catalog([])
    view.rerender(
      <SessionSelector
        {...selectorControls}
        catalogResult={{ data: emptyCatalog, status: "empty" }}
        selected={null}
        onRefresh={refresh}
        onSelect={vi.fn<(session: SessionCatalogItem) => void>()}
      />
    )
    expect(screen.getByText("No session is available.")).toBeInTheDocument()

    const staleSession = item("stale")
    view.rerender(
      <SessionSelector
        {...selectorControls}
        catalogResult={{
          data: catalog([staleSession]),
          error: null,
          status: "stale",
        }}
        selected={staleSession}
        onRefresh={refresh}
        onSelect={vi.fn<(session: SessionCatalogItem) => void>()}
      />
    )
    expect(
      screen.getByRole("dialog", { name: "Player and session context" })
    ).toHaveTextContent("stale")
    expect(screen.getByText("Read-only session")).toBeInTheDocument()
  })

  it("shows latest five, searchable all sessions, selection, and capability state", async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn<(session: SessionCatalogItem) => void>()
    const onSelectPlayer = vi.fn<(playerId: string) => void>()
    const loadAllSessions = vi
      .fn<() => Promise<void>>()
      .mockResolvedValue(undefined)
    const sessions = Array.from({ length: 7 }, (_, index) =>
      item(`session-${index}`, {
        character: `Player ${index}`,
        control_available: index === 6,
        control_state: index === 6 ? "ready" : null,
        ended_at: index === 6 ? null : "2026-08-03T10:30:00Z",
        live: index === 6,
        objective:
          index === 2 ? "Recover the crystal" : `Objective session-${index}`,
        player_id: "player-alpha",
        state: index === 6 ? "running" : "stopped",
        updated_at: `2026-08-03T10:${String(index).padStart(2, "0")}:00Z`,
      })
    )
    const beta = item("beta-session", {
      character: "Player Beta",
      player_id: "player-beta",
    })
    const data = catalog([...sessions, beta])

    render(
      <SessionSelector
        {...selectorControls}
        catalogResult={{ data, status: "ready" }}
        loadAllSessions={loadAllSessions}
        selected={sessions[6]}
        onRefresh={vi.fn<() => Promise<void>>().mockResolvedValue(undefined)}
        onSelect={onSelect}
        onSelectPlayer={onSelectPlayer}
      />
    )

    await user.click(
      screen.getByRole("button", { name: /selected context, player 6/i })
    )
    expect(screen.getByText("Control available: ready")).toBeInTheDocument()
    expect(
      screen.getAllByRole("button", { name: /player [0-5]/i })
    ).toHaveLength(5)
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Selected player" }),
      "player-beta"
    )
    expect(onSelectPlayer).toHaveBeenCalledWith("player-beta")

    await user.click(screen.getByRole("button", { name: "Show all sessions" }))
    expect(loadAllSessions).toHaveBeenCalledOnce()
    const search = screen.getByRole("searchbox", {
      name: "Search all sessions",
    })
    await user.type(search, "crystal")
    expect(
      screen.getByRole("button", { name: /recover the crystal/i })
    ).toBeInTheDocument()
    await user.click(
      screen.getByRole("button", { name: /recover the crystal/i })
    )
    expect(onSelect).toHaveBeenCalledWith(sessions[2])
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
