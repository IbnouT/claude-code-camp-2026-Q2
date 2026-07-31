import {
  describe,
  expect,
  it,
} from "vitest";
import {
  liveHref,
  liveIdentity,
} from "./routes";

describe("Live route identity", () => {
  it("builds a v2 Live deep link", () => {
    expect(liveHref({
      playerId: "poucet",
      sessionId: "session-123",
    })).toBe("/live?player=poucet&session=session-123");
  });

  it("requires both URL-backed identities", () => {
    expect(liveIdentity(new URL(
      "http://127.0.0.1:8791/live?player=poucet&session=session-123",
    ))).toEqual({
      playerId: "poucet",
      sessionId: "session-123",
    });
    expect(liveIdentity(new URL(
      "http://127.0.0.1:8791/live?player=poucet",
    ))).toBeNull();
  });
});
