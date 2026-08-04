import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { LauncherView } from "./launcher-view"

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => (
    <a href="/live">{children}</a>
  ),
}))

describe("launcher view", () => {
  it("escape closes the start and load panels", () => {
    render(
      <LauncherView
        status="ready"
        players={[{ id: "poucet", label: "poucet", start_available: true }]}
        sessions={[]}
        onStart={() => {}}
        initialLoadOpen
      />
    )
    expect(screen.getByText("All players")).toBeInTheDocument()
    expect(screen.getByLabelText(/Opening instruction/)).toBeInTheDocument()

    fireEvent.keyDown(window, { key: "Escape" })

    expect(screen.queryByText("All players")).not.toBeInTheDocument()
    expect(
      screen.queryByLabelText(/Opening instruction/)
    ).not.toBeInTheDocument()
  })
})
