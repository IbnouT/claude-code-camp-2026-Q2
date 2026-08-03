import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it } from "vitest"

import { App } from "./foundation-review"
import { tokenEvidence } from "./token-evidence"

afterEach(cleanup)

describe("development foundation review", () => {
  it("maps every authored semantic token to frozen selector evidence", () => {
    const mappedTokens = tokenEvidence.map(({ token }) => token)

    expect(mappedTokens).toHaveLength(106)
    expect(mappedTokens).toHaveLength(new Set(mappedTokens).size)
    for (const evidence of tokenEvidence) {
      expect(evidence.dark.file).not.toBe("")
      expect(evidence.dark.selector).not.toBe("")
      expect(evidence.dark.property).not.toBe("")
    }
  })

  it("shows the foundation gates and preserves controlled input state", async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(
      screen.getByRole("heading", { name: "Observatory architecture" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Backend contract baseline" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Observatory semantic tokens" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Map states" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Interaction and layers" })
    ).toBeInTheDocument()
    expect(screen.getByTestId("map-navigation-colors")).toBeInTheDocument()
    expect(screen.getByTestId("map-fill-colors")).toBeInTheDocument()
    expect(screen.getByTestId("map-line-colors")).toBeInTheDocument()
    expect(screen.getByText("65 unrelated sessions")).toBeInTheDocument()
    expect(screen.getAllByText("14.79 MiB")).toHaveLength(2)
    expect(screen.getByText("3,273 records")).toBeInTheDocument()

    const probe = screen.getByRole("textbox", { name: "HMR state probe" })
    await user.type(probe, "state survives")

    expect(probe).toHaveValue("state survives")
    expect(screen.getByText("Playwright and axe")).toBeInTheDocument()
  })

  it("switches the cumulative token review between exact themes", async () => {
    const user = userEvent.setup()
    render(<App />)

    const gallery = screen.getByTestId("token-gallery")
    const lightTheme = screen.getByRole("button", { name: "Light" })
    const darkTheme = screen.getByRole("button", { name: "Dark" })

    expect(gallery).toHaveAttribute("data-theme-review", "dark")
    expect(darkTheme).toHaveAttribute("aria-pressed", "true")

    await user.click(lightTheme)

    expect(gallery).toHaveAttribute("data-theme-review", "light")
    expect(document.documentElement).toHaveAttribute("data-theme", "light")
    expect(lightTheme).toHaveAttribute("aria-pressed", "true")

    await user.click(darkTheme)

    expect(gallery).toHaveAttribute("data-theme-review", "dark")
    expect(document.documentElement).not.toHaveAttribute("data-theme")
  })
})
