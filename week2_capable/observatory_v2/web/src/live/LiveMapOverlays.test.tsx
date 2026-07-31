// @vitest-environment jsdom

import {
  render,
  screen,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  describe,
  expect,
  it,
  vi,
} from "vitest";
import type { LiveAgentExcerpt } from "../contracts";
import { LiveMapLegend } from "./LiveMapLegend";
import { LiveThoughtDock } from "./LiveThoughtDock";

const thought: LiveAgentExcerpt = {
  text: "Return to the Temple and try another route.",
  phase: "plan",
  observed_at: "2026-07-31T04:01:26Z",
  line: 723,
  evidence: "agent log line 723",
};

describe("live map overlays", () => {
  it("renders exact thought evidence and phase labels", () => {
    render(
      <LiveThoughtDock
        expanded
        thought={thought}
        onToggle={vi.fn()}
      />,
    );

    expect(screen.getByRole("complementary", {
      name: "Agent thought",
    })).toHaveTextContent("Agent · Planning");
    expect(screen.getByText(thought.text)).toBeInTheDocument();
    expect(screen.getByText("agent log line 723 · line 723"))
      .toHaveAttribute("title", "Observed 2026-07-31T04:01:26Z");
  });

  it.each([
    ["reasoning", "Thinking"],
    ["tool_call", "Acting"],
  ] as const)("maps %s to %s", (phase, label) => {
    render(
      <LiveThoughtDock
        expanded
        thought={{ ...thought, phase }}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByText(`Agent · ${label}`)).toBeInTheDocument();
  });

  it("exposes one labeled collapse control per dock", async () => {
    const user = userEvent.setup();
    const toggleThought = vi.fn();
    const toggleLegend = vi.fn();
    render(
      <>
        <LiveThoughtDock
          expanded
          thought={thought}
          onToggle={toggleThought}
        />
        <LiveMapLegend
          entries={[{ kind: "room", label: "Learned room" }]}
          expanded
          onToggle={toggleLegend}
        />
      </>,
    );

    await user.click(screen.getByRole("button", {
      name: "Collapse agent thought",
    }));
    await user.click(screen.getByRole("button", {
      name: "Collapse map legend",
    }));
    expect(toggleThought).toHaveBeenCalledOnce();
    expect(toggleLegend).toHaveBeenCalledOnce();
  });
});
