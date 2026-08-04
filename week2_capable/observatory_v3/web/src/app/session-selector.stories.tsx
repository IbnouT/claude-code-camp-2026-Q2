import type { Meta, StoryObj } from "@storybook/react-vite"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRouter,
} from "@tanstack/react-router"

import { SessionSelector } from "./session-selector"
import type { SessionCatalogItem } from "@/data/session-catalog"

function seedSession(
  overrides: Partial<SessionCatalogItem> &
    Pick<SessionCatalogItem, "id" | "player_id" | "character">
): SessionCatalogItem {
  return {
    gateway_session_id: `gw-${overrides.id}`,
    state: overrides.live ? "running" : "ended",
    control_state: null,
    control_available: Boolean(overrides.live),
    capture_status: "complete",
    created_at: "2026-08-03T20:00:00Z",
    updated_at: "2026-08-03T21:00:00Z",
    ended_at: overrides.live ? null : "2026-08-03T21:30:00Z",
    stop_mode: overrides.live ? null : "cooperative",
    event_count: 128,
    turn_count: null,
    iteration_count: null,
    latest_seq: 17,
    legacy: false,
    live: false,
    objective: null,
    goal_count: 1,
    nudge_count: 0,
    projection_status: "available",
    projection_gaps: [],
    ...overrides,
  }
}

const sessions: SessionCatalogItem[] = [
  seedSession({
    id: "8ea29b49-d898-44b9-b01a-1568f53fdf66",
    player_id: "elenor",
    character: "Elenor",
    live: true,
    objective: "Recover the crystal from the temple depths",
    event_count: 438,
  }),
  seedSession({
    id: "b27a872d-4a2b-49f6-9d38-2fb0e6f0a411",
    player_id: "elenor",
    character: "Elenor",
    objective: "Map the eastern corridors",
    event_count: 312,
    updated_at: "2026-08-03T20:40:00Z",
  }),
  seedSession({
    id: "1c9f2ab0-7e31-4f0e-a2d4-5f2b9c8f1e02",
    player_id: "elenor",
    character: "Elenor",
    event_count: 96,
    updated_at: "2026-08-03T19:15:00Z",
  }),
  seedSession({
    id: "5d20cc71-90aa-4b57-8f3e-cb1e6a92d713",
    player_id: "elenor",
    character: "Elenor",
    objective: "Defeat the gate warden without losing mana",
    event_count: 204,
    updated_at: "2026-08-03T18:05:00Z",
  }),
  seedSession({
    id: "00e84a4c-de12-45c0-9a1f-4b7f2f6f0c55",
    player_id: "poucet",
    character: "poucet",
    objective: "Reach level three before nightfall",
    event_count: 513,
    updated_at: "2026-08-03T17:20:00Z",
  }),
]

const catalog = {
  resource_id: "session-catalog" as const,
  resource_version: 1,
  source_cursor: "story",
  completeness: "complete" as const,
  continuation_cursor: null,
  capture_gaps: [],
  source_refs: [],
  players: [
    { id: "elenor", label: "Elenor", start_available: false },
    { id: "poucet", label: "poucet", start_available: true },
  ],
  sessions,
}

function storyRouter(selected: SessionCatalogItem, onLive: boolean) {
  const client = new QueryClient()
  const StorySelector = () => (
    <div className="flex justify-end bg-header-surface p-4">
      <SessionSelector
        catalogResult={{ data: catalog, status: "ready" }}
        isLoadingAllSessions={false}
        loadAllSessions={() => Promise.resolve()}
        onRefresh={() => Promise.resolve()}
        onSelect={() => undefined}
        onSelectPlayer={() => undefined}
        playerComplete
        selected={selected}
        onLeaveLive={onLive ? () => undefined : undefined}
      />
    </div>
  )
  const Wrapped = () => (
    <QueryClientProvider client={client}>
      <StorySelector />
    </QueryClientProvider>
  )
  return createRouter({
    routeTree: createRootRoute({ component: Wrapped }),
    history: createMemoryHistory(),
  })
}

const liveRouter = storyRouter(sessions[0], true)
const sessionsRouter = storyRouter(sessions[1], false)

const meta: Meta = {
  title: "Header/SessionSelector",
}

export default meta

type Story = StoryObj

export const OnLive: Story = {
  render: () => <RouterProvider router={liveRouter} />,
}

export const OnSessions: Story = {
  render: () => <RouterProvider router={sessionsRouter} />,
}
