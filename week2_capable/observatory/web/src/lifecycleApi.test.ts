import {
  describe,
  expect,
  it,
} from "vitest";
import { lifecycleApiUrl } from "./lifecycleApi";

describe("lifecycle API address", () => {
  it("keeps the served host and targets the supervisor port", () => {
    expect(
      lifecycleApiUrl(
        "/api/sessions/session-123/stop",
        "http://127.0.0.1:8787",
      ),
    ).toBe("http://127.0.0.1:8792/api/sessions/session-123/stop");
  });
});
