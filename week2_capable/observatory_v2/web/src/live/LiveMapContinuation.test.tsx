// @vitest-environment jsdom

import {
  render,
  screen,
} from "@testing-library/react";
import {
  describe,
  expect,
  it,
} from "vitest";
import { LiveMapContinuation } from "./LiveMapContinuation";

describe("LiveMapContinuation", () => {
  it("renders one inert, accessible frame chevron with an inward fade", () => {
    const { container } = render(
      <LiveMapContinuation
        frame={{ width: 400, height: 300 }}
        marker={{
          edge: "right",
          hiddenRoomId: "hidden",
          point: { x: 500, y: 120 },
        }}
        overlayRects={[]}
        safeInsets={{ top: 10, right: 10, bottom: 10, left: 10 }}
        viewport={{ x: 0, y: 0, width: 400, height: 300 }}
        visibleRoomFootprints={[]}
      />,
    );

    const continuation = screen.getByRole("img", {
      name: "Learned map continues east",
    });
    expect(continuation).toHaveAttribute("data-edge", "right");
    expect(continuation).toHaveStyle({
      height: "24px",
      left: "340px",
      top: "108px",
      width: "50px",
    });
    expect(container.querySelector(
      ".live-map-continuation-fade",
    )).toBeInTheDocument();
    expect(container.querySelectorAll(
      ".live-map-continuation-chevron",
    )).toHaveLength(1);
  });
});
