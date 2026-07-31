// @vitest-environment jsdom

import {
  fireEvent,
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
import { LiveMapBoundary } from "./LiveMapBoundary";

describe("live map focus boundary", () => {
  it("shows the unique hidden-room count and activates by pointer", async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();
    renderBoundary({ onToggle });

    const boundary = screen.getByRole("button", {
      name: "Show 3 hidden rooms beyond East Gate",
    });
    expect(boundary).toHaveTextContent("+3");
    await user.click(boundary);
    expect(onToggle).toHaveBeenCalledWith("east-gate");
  });

  it("explains expanded state and supports keyboard retraction", () => {
    const onToggle = vi.fn();
    renderBoundary({
      boundary: {
        roomId: "east-gate",
        count: 3,
        expanded: true,
      },
      onToggle,
    });

    const boundary = screen.getByRole("button", {
      name: "Collapse rooms beyond East Gate",
    });
    expect(boundary).toHaveClass("is-expanded");
    expect(boundary).toHaveTextContent("−");
    fireEvent.keyDown(boundary, { key: " " });
    expect(onToggle).toHaveBeenCalledWith("east-gate");
  });

  it("keeps a lower boundary control beside the room label", () => {
    const view = renderBoundary({
      currentPoint: { x: 148, y: 0 },
      point: { x: 0, y: 122 },
    });

    expect(view.container.querySelector("circle")).toHaveAttribute(
      "cy",
      "154",
    );
  });
});

function renderBoundary(
  overrides: Partial<Parameters<typeof LiveMapBoundary>[0]> = {},
) {
  return render(
    <svg>
      <LiveMapBoundary
        boundary={{
          roomId: "east-gate",
          count: 3,
          expanded: false,
        }}
        currentPoint={{ x: 0, y: 0 }}
        point={{ x: 148, y: 0 }}
        roomTitle="East Gate"
        onToggle={vi.fn()}
        {...overrides}
      />
    </svg>,
  );
}
