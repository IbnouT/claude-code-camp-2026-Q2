import { describe, expect, it } from "vitest"

import { SessionCommandRequest } from "@/data/generated/validators"

describe("SessionCommandRequest", () => {
  it("accepts an optimistic command with an opaque cursor", () => {
    const command = SessionCommandRequest.parse({
      action: "guide",
      expected_cursor: "opaque-session-cursor",
      instruction: "Inspect the north gate",
      request_id: "request-42",
    })

    expect(command.expected_cursor).toBe("opaque-session-cursor")
  })

  it("rejects unknown command fields", () => {
    expect(() =>
      SessionCommandRequest.parse({
        action: "stop",
        expected_cursor: "opaque-session-cursor",
        request_id: "request-43",
        token: "must-not-cross-the-contract",
      })
    ).toThrow(/unrecognized/i)
  })
})
