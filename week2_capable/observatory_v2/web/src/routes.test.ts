import {
  describe,
  expect,
  it,
} from "vitest";
import {
  liveHref,
  liveIdentity,
  recordedSessionHref,
} from "./routes";

describe("Live route identity", () => {
  it("builds a v2 Live deep link", () => {
    expect(liveHref({
      playerId: "poucet",
      sessionId: "session-123",
    })).toBe("/live?player=poucet&session=session-123");
  });

  it("opens a recorded session on the same v2 Live surface", () => {
    expect(recordedSessionHref({
      id: "recorded-123",
      player_id: "poucet",
    })).toBe("/live?player=poucet&session=recorded-123");
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
