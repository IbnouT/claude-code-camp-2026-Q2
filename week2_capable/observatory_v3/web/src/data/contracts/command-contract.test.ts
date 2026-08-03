import { describe, expect, it } from "vitest"

import {
  SessionCommandRequest,
  StartCommandRequest,
} from "@/data/generated/validators"

describe("SessionCommandRequest", () => {
  it("accepts an optimistic command with an opaque cursor", () => {
    const command = SessionCommandRequest.parse({
      action: "guide",
      actor: "operator",
      expected_cursor: "opaque-session-cursor",
      idempotency_key: "request-42",
      instruction: "Inspect the north gate",
      player_id: "poucet",
    })

    expect(command.expected_cursor).toBe("opaque-session-cursor")
  })

  it("keeps start commands credential-free", () => {
    const command = StartCommandRequest.parse({
      actor: "operator",
      idempotency_key: "request-43",
      player_id: "poucet",
    })

    expect(command).toMatchObject({
      actor: "operator",
      player_id: "poucet",
    })
    expect(command).not.toHaveProperty("api_key")
  })

  it("rejects unknown command fields", () => {
    expect(() =>
      SessionCommandRequest.parse({
        action: "stop",
        actor: "operator",
        expected_cursor: "opaque-session-cursor",
        idempotency_key: "request-44",
        player_id: "poucet",
        token: "must-not-cross-the-contract",
      })
    ).toThrow(/unrecognized/i)
  })
})
