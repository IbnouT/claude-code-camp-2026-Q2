import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { SearchDialog } from "./SearchDialog";

it("constrains Ask to the selected run and replay record", async () => {
  window.history.replaceState(null, "", "/?space=sessions&record=gateway%3A8");
  let request: Record<string, unknown> | null = null;
  vi.stubGlobal("fetch", vi.fn(async (_input, init?: RequestInit) => {
    request = JSON.parse(String(init?.body)) as Record<string, unknown>;
    return new Response(JSON.stringify({
      tier: "deterministic",
      question: "Why did the agent stop?",
      scope_record_id: "gateway:8",
      plan: [],
      answer: "No stop was retained at this moment.",
      claims: [],
      citations: [],
      missing: ["final response at selected moment"],
      model_cost_usd: 0,
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }));

  const user = userEvent.setup();
  render(
    <SearchDialog
      open
      runId="run-1"
      scopeLabel="J2 · a1"
      onClose={() => undefined}
    />,
  );
  await user.type(
    screen.getByRole("textbox", { name: "Question or evidence query" }),
    "Why did the agent stop?",
  );
  await user.click(screen.getByRole("button", { name: "Ask" }));

  expect(await screen.findByText("No stop was retained at this moment."))
    .toBeVisible();
  expect(request).toMatchObject({
    run_id: "run-1",
    selected_record_id: "gateway:8",
    allow_model: false,
  });
});
