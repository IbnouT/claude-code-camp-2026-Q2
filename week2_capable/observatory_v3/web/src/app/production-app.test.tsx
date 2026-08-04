import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { App } from "./production-app"

describe("production application boundary", () => {
  it("renders the production router without development review content", async () => {
    render(<App />)

    expect(
      await screen.findByRole("heading", { name: /Boukensha/ })
    ).toBeInTheDocument()
    expect(screen.queryByText("Foundation review")).not.toBeInTheDocument()
    expect(
      screen.queryByRole("link", { name: "Review" })
    ).not.toBeInTheDocument()
  })
})
