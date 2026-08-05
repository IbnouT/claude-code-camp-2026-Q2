import {
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";
import {
  selectedRoomFromLocation,
  syncSelectedRoomToLocation,
} from "./selectionUrl";

describe("selected room URL state", () => {
  beforeEach(() => {
    window.history.replaceState(
      null,
      "",
      "/?space=live&session=session-1",
    );
  });

  it("writes and restores the selected room", () => {
    syncSelectedRoomToLocation("room:3001");

    expect(selectedRoomFromLocation()).toBe("room:3001");
    expect(new URL(window.location.href).searchParams.get("session"))
      .toBe("session-1");
  });

  it("removes only the selected room when selection clears", () => {
    syncSelectedRoomToLocation("room:3001");
    syncSelectedRoomToLocation(null);

    expect(selectedRoomFromLocation()).toBeNull();
    expect(new URL(window.location.href).searchParams.get("session"))
      .toBe("session-1");
  });
});
