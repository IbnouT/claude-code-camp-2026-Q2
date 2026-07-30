import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "./App";

describe("observatory product shell", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/?space=live");
  });

  it("renders one coherent header and representative workspace", () => {
    render(<App />);
    expect(
      screen.getByRole("link", { name: "Boukensha Observatory home" }),
    ).toBeVisible();
    expect(
      screen.getByRole("navigation", { name: "Observatory spaces" }),
    ).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Player" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Session" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Living world" })).toBeVisible();
    expect(screen.getByText("Position needs confirmation")).toBeVisible();
  });

  it("keeps global context while moving between spaces", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(screen.getByRole("combobox", { name: "Player" }), "dummy");
    await user.click(screen.getByRole("button", { name: "Knowledge" }));
    expect(screen.getByRole("combobox", { name: "Player" })).toHaveValue("dummy");
    expect(screen.queryByRole("combobox", { name: "Session" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load recorded evidence" }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Direct the agent/ }))
      .not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Search knowledge" })).toBeVisible();
    expect(screen.getByText(/Separate what the player learned/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Sessions" }));
    expect(screen.getByRole("combobox", { name: "Session" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Load recorded evidence" }))
      .toBeDisabled();
  });

  it("opens deterministic Ask from the scoped Live workspace action", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Ask about this run" }));
    const dialog = screen.getByRole("dialog", { name: "Ask or search evidence" });
    expect(dialog).toBeVisible();
    expect(
      within(dialog).getByText("Ask with evidence, even without a model"),
    ).toBeVisible();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Ask about this run" })).toHaveFocus();
  });

  it("shows the full agent-control contract without pretending it can send", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Direct the agent/ }));
    const dialog = screen.getByRole("dialog", { name: "Direct the selected agent" });
    expect(dialog).toBeVisible();
    expect(within(dialog).getByText("Authenticated live session")).toBeVisible();
    expect(within(dialog).getByText("Maximum additional spend")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: /Preview only/ })).toBeDisabled();
  });

  it("makes every evidence form explicit, including a missing truth form", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("tab", { name: /Truth/ }));
    expect(
      screen.getByText("Observer truth is not configured for this installation."),
    ).toBeVisible();
    expect(screen.getByText("missing")).toBeVisible();
  });
});
