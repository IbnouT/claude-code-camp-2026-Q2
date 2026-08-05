import {
  describe,
  expect,
  it,
} from "vitest";
import type { Snapshot } from "../contracts";
import {
  cacheHit,
  formatAge,
  latestContextFill,
  projectSpend,
} from "./liveEvidence";

describe("live evidence projection", () => {
  it("uses the scoped spend numerator", () => {
    const base = {
      cost_usd: 0.8,
      current_turn_cost_usd: 0.12,
      spend_cap_usd: 0.2,
      spend_cap_scope: "turn",
    } as Snapshot;
    expect(projectSpend(base)).toEqual({ amount: 0.12, cap: 0.2, scope: "turn" });
    expect(projectSpend({ ...base, spend_cap_scope: "session" })).toEqual({
      amount: 0.8,
      cap: 0.2,
      scope: "session",
    });
  });

  it("keeps cache and latest-response context semantics explicit", () => {
    expect(cacheHit({ fresh_input: 600, cache_read: 300, cache_write: 100 })).toBe(0.3);
    expect(cacheHit({ fresh_input: 0, cache_read: 0, cache_write: 0 })).toBeNull();
    expect(latestContextFill({
      context_limit: 200_000,
      economics: [{ response: 1, at: "now", cost_usd: 0.1, cumulative_cost_usd: 0.1, context_tokens: 50_000 }],
    } as Snapshot)).toBe(0.25);
  });

  it("formats observable staleness without future ages", () => {
    expect(formatAge("2026-07-31T22:00:00Z", Date.parse("2026-07-31T22:00:04Z"))).toBe("4s ago");
    expect(formatAge("2026-07-31T22:00:04Z", Date.parse("2026-07-31T22:00:00Z"))).toBe("now");
  });
});
