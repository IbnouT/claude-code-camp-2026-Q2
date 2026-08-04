import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render as renderBare, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactElement } from "react"

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}))

import { SessionSelector } from "@/app/session-selector"
import type { SessionCatalog, SessionCatalogItem } from "@/data/session-catalog"

afterEach(cleanup)

function render(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = renderBare(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>
  )
  return {
    ...view,
    rerender: (next: ReactElement) =>
      view.rerender(
        <QueryClientProvider client={client}>{next}</QueryClientProvider>
      ),
  }
}

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
  const players = new Map(
    sessions.map((session) => [
      session.player_id,
      {
        id: session.player_id,
        label: session.character,
        start_available: false,
      },
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
      screen.getByRole("dialog", { name: "View context" })
    ).toHaveTextContent("stopped")
  })

  it("shows latest three, selection, and capability state", async () => {
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
          index === 4 ? "Recover the crystal" : `Objective session-${index}`,
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
      screen.getByRole("button", { name: /view context, player 6/i })
    )
    // Current section with the full session id and its actions.
    expect(screen.getByText("Current")).toBeInTheDocument()
    expect(screen.getAllByText("session-6").length).toBeGreaterThan(0)
    expect(screen.getByRole("button", { name: /stop session/i })).toBeEnabled()
    // Recent sessions of the same player, capped at three.
    expect(screen.getByText(/recent player 6 sessions/i)).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /view all player 6 sessions \(7\)/i })
    ).toBeInTheDocument()
    // Player switching lives outside the panel: no other-players block.
    expect(screen.queryByText("Other players")).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /all sessions & players/i })
    ).not.toBeInTheDocument()
    // Rows lead with the session goal when one is retained.
    const recentRows = screen.getAllByRole("button", {
      name: /stopped, (objective session-|recover the crystal)/i,
    })
    expect(recentRows).toHaveLength(3)
    expect(
      screen.getByRole("button", { name: /stopped, recover the crystal/i })
    ).toBeInTheDocument()
    // A recent row opens its session and closes the panel.
    await user.click(recentRows[0])
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("confirms before stopping and cancel leaves the session alone", async () => {
    const user = userEvent.setup()
    const running = item("session-live", {
      control_available: true,
      control_state: "ready",
      ended_at: null,
      live: true,
      state: "running",
    })
    render(
      <SessionSelector
        {...selectorControls}
        catalogResult={{ data: catalog([running]), status: "ready" }}
        selected={running}
        onRefresh={vi.fn<() => Promise<void>>().mockResolvedValue(undefined)}
        onSelect={vi.fn<(session: SessionCatalogItem) => void>()}
      />
    )
    await user.click(screen.getByRole("button", { name: /view context/i }))
    await user.click(screen.getByRole("button", { name: /stop session/i }))
    // The confirmation carries the scope and the grace warning.
    expect(screen.getByText("Stop this session?")).toBeInTheDocument()
    expect(screen.getAllByText(running.id).length).toBeGreaterThan(0)
    expect(screen.getByText(/bounded grace period/i)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(screen.queryByText("Stop this session?")).not.toBeInTheDocument()
  })

  it("offers the map recording for an ended selection", async () => {
    const user = userEvent.setup()
    const ended = item("session-ended")
    const data = catalog([ended])

    render(
      <SessionSelector
        {...selectorControls}
        catalogResult={{ data, status: "ready" }}
        selected={ended}
        onRefresh={vi.fn<() => Promise<void>>().mockResolvedValue(undefined)}
        onSelect={vi.fn<(session: SessionCatalogItem) => void>()}
      />
    )
    await user.click(screen.getByRole("button", { name: /view context/i }))
    expect(
      screen.getByRole("button", { name: "View map recording" })
    ).toBeInTheDocument()
  })
})
