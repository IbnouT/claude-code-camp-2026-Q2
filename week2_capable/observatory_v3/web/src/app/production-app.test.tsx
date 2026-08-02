import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { App } from "./production-app"

describe("production application boundary", () => {
  it("renders only the production foundation state", () => {
    render(<App />)

    expect(
      screen.getByRole("heading", { name: "Frontend foundation ready" })
    ).toBeInTheDocument()
    expect(screen.queryByText("Foundation review")).not.toBeInTheDocument()
  })
})
