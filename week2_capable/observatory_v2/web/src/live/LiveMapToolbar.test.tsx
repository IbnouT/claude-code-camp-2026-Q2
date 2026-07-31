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
import { LiveMapToolbar } from "./LiveMapToolbar";

describe("live map toolbar", () => {
  it("exposes explicit camera and presentation state", () => {
    renderToolbar();

    expect(screen.getByRole("group", {
      name: "Map camera",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Follow",
    })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", {
      name: "Manual",
    })).toBeEnabled();
    expect(screen.getByRole("button", {
      name: "Manual",
    })).toHaveAttribute(
      "title",
      "Freeze the camera at its current center and scale",
    );
    expect(screen.getByRole("button", {
      name: "Focus",
    })).toHaveAttribute("aria-pressed", "true");
  });

  it("makes Fit context-aware and activates every operator choice", async () => {
    const user = userEvent.setup();
    const onCameraChange = vi.fn();
    const onModeChange = vi.fn();
    const onZoom = vi.fn();
    renderToolbar({
      selectedRoomId: "vnum:6077",
      onCameraChange,
      onModeChange,
      onZoom,
    });

    await user.click(screen.getByRole("button", {
      name: "Fit selection",
    }));
    await user.click(screen.getByRole("button", {
      name: "Lantern",
    }));
    await user.click(screen.getByRole("button", {
      name: "Zoom in",
    }));

    expect(onCameraChange).toHaveBeenCalledWith("fit");
    expect(onModeChange).toHaveBeenCalledWith("lantern");
    expect(onZoom).toHaveBeenCalledWith("in");
  });

  it("explains bounded zoom controls", () => {
    renderToolbar({ zoom: 2 });
    expect(screen.getByRole("button", {
      name: "Zoom in",
    })).toBeDisabled();
    expect(screen.getByRole("button", {
      name: "Zoom in",
    })).toHaveAttribute("title", "Maximum zoom reached");

    renderToolbar({ zoom: 0.1, minimumZoom: 0.1 });
    const zoomOut = screen.getAllByRole("button", {
      name: "Zoom out",
    }).at(-1);
    expect(zoomOut).toBeDisabled();
    expect(zoomOut).toHaveAttribute("title", "Minimum zoom reached");
  });
});

function renderToolbar(
  overrides: Partial<Parameters<typeof LiveMapToolbar>[0]> = {},
) {
  return render(
    <LiveMapToolbar
      camera="follow"
      mode="focus"
      selectedRoomId={null}
      zoom={1}
      minimumZoom={0.75}
      maximumZoom={2}
      onCameraChange={vi.fn()}
      onModeChange={vi.fn()}
      onZoom={vi.fn()}
      {...overrides}
    />,
  );
}
