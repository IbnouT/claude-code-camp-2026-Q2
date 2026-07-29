import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("observatory shell", () => {
  it("centers the world, belief divergence, and diagnostics", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Living world" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Belief vs reality" })).toBeVisible();
    expect(screen.getByText("Objective ended without evidence")).toBeVisible();
  });

  it("moves from live into an evidence investigation", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByText("Objective ended without evidence"));
    expect(screen.getByRole("button", { name: /Investigate/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText("Paused at evidence")).toBeVisible();
  });

  it("opens the shared ask and search palette", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Ask or search/ }));
    expect(screen.getByRole("dialog", { name: "Ask or search evidence" })).toBeVisible();
  });
});
