import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  AgentControlDialog,
  type ControlDraft,
} from "./AgentControlDialog";

describe("AgentControlDialog", () => {
  it("prefills and confirms an evidence-backed Live suggestion", async () => {
    const submit = vi.fn(async (draft: ControlDraft) => ({
      request_id: draft.request_id,
      action: draft.action,
      state: "running",
      insertion: "next_iteration_boundary",
    }));
    const props = {
      open: false,
      selectedPlayer: "poucet",
      selectedSession: "session-live",
      sequence: 48,
      objective: "Reach the lair",
      model: "recorded-model",
      tools: ["move"],
      onClose: vi.fn(),
      onSubmit: submit,
    };
    const view = render(<AgentControlDialog {...props} />);

    window.dispatchEvent(new CustomEvent("boukensha:control-prefill", {
      detail: {
        instruction: "east",
        reason: "Retained beacon and learned route",
        expected_sequence: 47,
      },
    }));
    view.rerender(<AgentControlDialog {...props} open />);

    const dialog = screen.getByRole("dialog", {
      name: "Direct the selected agent",
    });
    expect(
      within(dialog).getByRole("textbox", { name: "Operator guidance" }),
    ).toHaveValue("east");
    expect(
      within(dialog).getByText("Retained beacon and learned route"),
    ).toBeVisible();
    expect(within(dialog).getByText("#47")).toBeVisible();

    await userEvent.setup().click(
      within(dialog).getByRole("button", { name: "Confirm guide" }),
    );

    expect(submit).toHaveBeenCalledWith(expect.objectContaining({
      action: "guide",
      instruction: "east",
      expected_sequence: 47,
    }));
  });
});
