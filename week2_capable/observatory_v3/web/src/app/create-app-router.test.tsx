import { createMemoryHistory, RouterProvider } from "@tanstack/react-router"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it } from "vitest"

import { createAppRouter } from "@/app/create-app-router"
import {
  ServerStateProvider,
  createServerStateClient,
} from "@/data/server-state-provider"

afterEach(cleanup)

function createDeferred() {
  let resolve = () => {}
  const promise = new Promise<void>((resolvePromise) => {
    resolve = resolvePromise
  })

  return { promise, resolve }
}

function renderRoute(
  initialEntry: string,
  prepareRoute?: () => Promise<void> | void
) {
  const router = createAppRouter({
    history: createMemoryHistory({ initialEntries: [initialEntry] }),
    prepareRoute,
  })
  render(
    <ServerStateProvider client={createServerStateClient()}>
      <RouterProvider router={router} />
    </ServerStateProvider>
  )
  return router
}

describe("typed application router", () => {
  it("validates search state and preserves one shell across navigation", async () => {
    const user = userEvent.setup()
    const router = renderRoute("/sessions?state=running&page=3")

    expect(
      await screen.findByRole("heading", { name: "Find a session" })
    ).toBeInTheDocument()
    expect(router.state.location.search).toMatchObject({
      page: 3,
      state: "running",
    })

    const shell = screen.getByTestId("application-shell")
    await user.click(screen.getByRole("link", { name: "Knowledge" }))

    expect(
      await screen.findByRole("heading", { name: "Knowledge" })
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Knowledge" })).toHaveAttribute(
      "aria-current",
      "page"
    )
    expect(screen.getByTestId("application-shell")).toBe(shell)
    expect(screen.getByTestId("route-content")).toHaveFocus()

    router.history.back()
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Find a session" })
      ).toBeInTheDocument()
    })
    expect(screen.getByTestId("application-shell")).toBe(shell)
  })

  it("falls back invalid search values and parses valid session parameters", async () => {
    const router = renderRoute("/sessions?state=unknown&page=-2")

    expect(
      await screen.findByRole("heading", { name: "Find a session" })
    ).toBeInTheDocument()
    expect(router.state.location.search).toMatchObject({
      page: 1,
      state: "all",
    })

    await router.navigate({
      to: "/sessions/$sessionId",
      params: { sessionId: "session-42" },
    })
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sessions/session-42")
    })
    expect(router.state.location.search).toMatchObject({ view: "story" })
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Sessions" })).toHaveAttribute(
        "aria-current",
        "page"
      )
    })
    expect(screen.getByRole("link", { name: "Live" })).not.toHaveAttribute(
      "aria-current"
    )
  })

  it("carries selected context through typed product-space links", async () => {
    const user = userEvent.setup()
    const router = renderRoute(
      "/live?view=activity&player=player-7&session=session-42"
    )

    expect(await screen.findByLabelText("Live workspace")).toBeInTheDocument()
    await user.click(screen.getByRole("link", { name: "Experiments" }))

    expect(router.state.location.pathname).toBe("/experiments")
    expect(router.state.location.search).toMatchObject({
      lens: "compare",
      player: "player-7",
      session: "session-42",
    })

    await user.click(screen.getByRole("link", { name: "Knowledge" }))
    expect(router.state.location.search).toMatchObject({
      player: "player-7",
      query: "",
      session: "session-42",
    })
  })

  it("keeps one shell through routed pending, parameter error, and recovery", async () => {
    let routePreparation: Promise<void> | undefined
    const router = renderRoute("/live", () => routePreparation)

    expect(await screen.findByLabelText("Live workspace")).toBeInTheDocument()
    const shell = screen.getByTestId("application-shell")
    const routeContent = screen.getByTestId("route-content")
    const pending = createDeferred()
    routePreparation = pending.promise

    await userEvent
      .setup()
      .click(screen.getByRole("link", { name: "Sessions" }))
    expect(
      await screen.findByRole("heading", { name: "Loading route" })
    ).toBeInTheDocument()
    expect(screen.getByTestId("application-shell")).toBe(shell)
    expect(screen.getByTestId("route-content")).toBe(routeContent)

    pending.resolve()
    expect(
      await screen.findByRole("heading", { name: "Find a session" })
    ).toBeInTheDocument()
    routePreparation = undefined

    await router.navigate({
      to: "/sessions/$sessionId",
      params: { sessionId: "INVALID!" },
    })

    expect(
      await screen.findByRole("heading", { name: "Route unavailable" })
    ).toBeInTheDocument()
    expect(screen.getByTestId("application-shell")).toBe(shell)
    expect(screen.getByTestId("route-content")).toBe(routeContent)
    expect(routeContent).toHaveFocus()

    await router.navigate({
      to: "/sessions/$sessionId",
      params: { sessionId: "session-42" },
    })
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sessions/session-42")
    })
    expect(screen.getByTestId("application-shell")).toBe(shell)
    expect(screen.getByTestId("route-content")).toBe(routeContent)
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Sessions" })).toHaveAttribute(
        "aria-current",
        "page"
      )
    })
  })

  it("keeps unmatched paths on the not-found boundary", async () => {
    renderRoute("/missing-route")
    expect(
      await screen.findByRole("heading", { name: "Route not found" })
    ).toBeInTheDocument()
  })
})
