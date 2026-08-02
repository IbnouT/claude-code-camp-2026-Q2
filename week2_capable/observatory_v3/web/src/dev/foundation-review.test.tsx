import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { App } from "./foundation-review"

describe("development foundation review", () => {
  it("shows the foundation gates and preserves controlled input state", async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(
      screen.getByRole("heading", { name: "Observatory architecture" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Backend contract baseline" })
    ).toBeInTheDocument()
    expect(screen.getByText("65 unrelated sessions")).toBeInTheDocument()
    expect(screen.getAllByText("14.79 MiB")).toHaveLength(2)
    expect(screen.getByText("3,273 records")).toBeInTheDocument()

    const probe = screen.getByRole("textbox", { name: "HMR state probe" })
    await user.type(probe, "state survives")

    expect(probe).toHaveValue("state survives")
    expect(screen.getByText("Playwright and axe")).toBeInTheDocument()
  })
})
