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
      query: {
        version: 1,
        operation: "diagnose_stop",
        scope: {
          space: "sessions",
          run_id: "run-1",
          selected_record_id: "gateway:8",
        },
        filters: [],
        order: "causal",
        limit: 25,
      },
      scope_record_id: "gateway:8",
      plan: [],
      answer: "No stop was retained at this moment.",
      claims: [],
      citations: [],
      missing: ["final response at selected moment"],
      hypotheses: ["A hidden limit may have ended the run."],
      model_cost_usd: 0,
      model_input_tokens: 0,
      model_output_tokens: 0,
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }));

  const user = userEvent.setup();
  render(
    <SearchDialog
      open
      scope={{
        space: "sessions",
        run_id: "run-1",
        selected_record_id: "gateway:8",
      }}
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
  expect(screen.getByText("Unsupported hypotheses")).toBeVisible();
  expect(screen.getByText(
    "Capture gaps: final response at selected moment",
  )).toBeVisible();
  expect(request).toMatchObject({
    scope: {
      space: "sessions",
      run_id: "run-1",
      selected_record_id: "gateway:8",
    },
    allow_model: false,
    allow_summary: false,
  });
});

it("emits an allowlisted structured query and saves its URL state", async () => {
  window.history.replaceState(null, "", "/?space=sessions");
  let request: Record<string, unknown> | null = null;
  vi.stubGlobal("fetch", vi.fn(async (_input, init?: RequestInit) => {
    request = JSON.parse(String(init?.body)) as Record<string, unknown>;
    return new Response(JSON.stringify({
      tier: "deterministic",
      question: "Find the selected trace",
      query: {
        version: 1,
        operation: "search_evidence",
        scope: { space: "sessions", run_id: "run-1" },
        filters: [{ field: "trace_id", operator: "eq", value: "trace-7" }],
        order: "chronological",
        limit: 25,
      },
      scope_record_id: null,
      plan: [],
      answer: "One record matched.",
      claims: [],
      citations: [],
      missing: [],
      model_cost_usd: 0,
      model_input_tokens: 0,
      model_output_tokens: 0,
      model_summary: null,
      model_summary_citations: [],
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }));
  const user = userEvent.setup();
  render(
    <SearchDialog
      open
      scope={{ space: "sessions", run_id: "run-1" }}
      onClose={() => undefined}
    />,
  );
  await user.click(screen.getByText("Structured search"));
  await user.click(screen.getByRole("checkbox", {
    name: "Use an exact typed evidence query",
  }));
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Evidence field" }),
    "trace_id",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Filter value" }),
    "trace-7",
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Result order" }),
    "chronological",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Question or evidence query" }),
    "Find the selected trace",
  );
  await user.click(screen.getByRole("button", { name: "Ask" }));

  expect(request).toMatchObject({
    query: {
      version: 1,
      operation: "search_evidence",
      scope: { space: "sessions", run_id: "run-1" },
      filters: [{ field: "trace_id", operator: "eq", value: "trace-7" }],
      order: "chronological",
      limit: 25,
    },
  });
  expect(window.location.search).toContain("queryField=trace_id");
  expect(window.location.search).toContain("queryOrder=chronological");
});

it("offers only operators that match the selected field type", async () => {
  window.history.replaceState(null, "", "/?space=experiments");
  const user = userEvent.setup();
  render(
    <SearchDialog
      open
      scope={{ space: "experiments", comparison_id: "comparison-1" }}
      onClose={() => undefined}
    />,
  );
  await user.click(screen.getByText("Structured search"));
  await user.click(screen.getByRole("checkbox", {
    name: "Use an exact typed evidence query",
  }));

  const field = screen.getByRole("combobox", { name: "Evidence field" });
  expect(field).toHaveValue("arm_id");
  expect(screen.getByRole("option", { name: "contains" })).toBeVisible();
  expect(screen.queryByRole("option", { name: "at least" })).toBeNull();

  await user.selectOptions(field, "cost_usd");

  expect(screen.getByRole("option", { name: "at least" })).toBeVisible();
  expect(screen.getByRole("option", { name: "at most" })).toBeVisible();
  expect(screen.queryByRole("option", { name: "contains" })).toBeNull();
});
