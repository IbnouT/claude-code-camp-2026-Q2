import type { Meta, StoryObj } from "@storybook/react-vite"

import { LauncherView } from "./launcher-view"
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

const meta: Meta<typeof LauncherView> = {
  title: "Launcher/LauncherView",
  component: LauncherView,
}

export default meta
type Story = StoryObj<typeof LauncherView>

export const Ready: Story = {
  args: {
    status: "ready",
    players: [
      { id: "poucet", label: "Poucet", start_available: true },
      { id: "scout", label: "Scout Ranger", start_available: true },
      { id: "vega", label: "Vega", start_available: false },
    ],
    sessions: [
      seedSession({
        id: "s-vega-live",
        player_id: "vega",
        character: "Vega",
        live: true,
        latest_seq: 42,
      }),
      seedSession({
        id: "s-poucet-1",
        player_id: "poucet",
        character: "Poucet",
      }),
    ],
    onStart: () => undefined,
  },
}

export const Loading: Story = {
  args: {
    status: "pending",
    players: [],
    sessions: [],
    onStart: () => undefined,
  },
}

export const Empty: Story = {
  args: {
    status: "ready",
    players: [],
    sessions: [],
    onStart: () => undefined,
  },
}
