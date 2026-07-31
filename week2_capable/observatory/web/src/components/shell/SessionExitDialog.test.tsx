import {
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  SessionExitDialog,
  type StopReceipt,
} from "./SessionExitDialog";

describe("SessionExitDialog", () => {
  it("focuses Cancel and treats Escape only as cancellation", async () => {
    const cancel = vi.fn();
    const confirm = vi.fn(async (): Promise<StopReceipt> => ({
      session_id: "session-live",
      player_id: "poucet",
      state: "stopped",
      mode: "cooperative",
    }));
    render(
      <SessionExitDialog
        open
        player="poucet"
        session="session-live"
        onCancel={cancel}
        onConfirm={confirm}
      />,
    );

    const dialog = screen.getByRole("dialog", {
      name: "Stop this session?",
    });
    await waitFor(() => {
      expect(
        within(dialog).getByRole("button", { name: "Cancel" }),
      ).toHaveFocus();
    });
    await userEvent.setup().keyboard("{Escape}");

    expect(cancel).toHaveBeenCalledOnce();
    expect(confirm).not.toHaveBeenCalled();
  });
});
