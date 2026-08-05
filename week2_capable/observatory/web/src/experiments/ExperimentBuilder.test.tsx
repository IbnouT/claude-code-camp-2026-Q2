import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ExperimentCatalog } from "../contracts";
import { ExperimentBuilder } from "./ExperimentBuilder";

const catalog: ExperimentCatalog = {
  registry: [
    {
      id: "render.mode",
      label: "Model-facing result",
      group: "rendering",
      kind: "enum",
      description: "Select the retained gateway result projection.",
      default: "full",
      options: ["raw", "minimal", "full"],
      minimum: null,
      maximum: null,
      source: "gateway result-mode contract",
      execution_supported: true,
    },
  ],
  scenarios: [
    {
      id: "J1",
      label: "Find the bakery and read the menu",
      objective: "Find the bakery and read the menu.",
      success_predicate: "Gateway evidence retains a numbered bakery menu row.",
      starting_state: "level1-temple@1",
      reset_strategy: "verified snapshot before every sample",
      reset_identity: "level1-temple@1",
      execution_supported: true,
    },
  ],
  execution: {
    available: false,
    state_store_available: true,
    max_spend_usd: 10,
    paid_confirmation_required: true,
  },
};

describe("ExperimentBuilder", () => {
  it("builds two complete arms and validates without starting paid work", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        validation: {
          valid: true,
          comparable: true,
          execution_available: false,
          paid_confirmation_required: true,
          issues: [],
          checks: ["Every effective field belongs to the typed registry."],
        },
        queue: Array.from({ length: 20 }, (_, index) => `sample-${index + 1}`),
      }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ExperimentBuilder
        catalog={catalog}
        onClose={vi.fn()}
        onJobCreated={vi.fn()}
      />,
    );

    expect(screen.getByRole("spinbutton", {
      name: "Per-run spend ceiling",
    })).toHaveValue(0.5);
    await user.selectOptions(
      screen.getByRole("combobox", {
        name: "Variant Model-facing result",
      }),
      "raw",
    );
    await user.click(screen.getByRole("button", {
      name: "Validate definition",
    }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    const payload = JSON.parse(String(request.body)) as {
      definition: {
        arms: Array<{ values: Record<string, string> }>;
        effective_max_spend_usd: number;
      };
    };
    expect(payload.definition.arms[0].values["render.mode"]).toBe("full");
    expect(payload.definition.arms[1].values["render.mode"]).toBe("raw");
    expect(payload.definition.effective_max_spend_usd).toBe(10);
    expect(await screen.findByText("Definition is valid")).toBeInTheDocument();
    expect(screen.getByText(
      "Definition is valid, local execution is disabled",
    )).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare run" }))
      .not.toBeInTheDocument();
  });
});
