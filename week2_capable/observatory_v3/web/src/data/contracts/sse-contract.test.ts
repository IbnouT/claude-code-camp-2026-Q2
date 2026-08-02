import { describe, expect, it } from "vitest"

import { parseResourceChangedNotification } from "./sse-contract"

describe("parseResourceChangedNotification", () => {
  it("accepts a versioned resource notification", () => {
    const event = parseResourceChangedNotification(
      JSON.stringify({
        at: 1722631200.25,
        contract_version: "v1",
        event: "resource_changed",
        resource_id: "session-42",
        resource_kind: "session-summary",
        resource_version: 42,
        source_cursor: "opaque-cursor-42",
      })
    )

    expect(event.resource_kind).toBe("session-summary")
    expect(event.resource_version).toBe(42)
  })

  it("rejects invalid JSON", () => {
    expect(() => parseResourceChangedNotification("{")).toThrow(
      "SSE event data was not valid JSON"
    )
  })

  it("rejects uncontracted fields", () => {
    expect(() =>
      parseResourceChangedNotification(
        JSON.stringify({
          at: 1722631200.25,
          contract_version: "v1",
          event: "resource_changed",
          resource_id: "session-42",
          resource_kind: "session-summary",
          resource_version: 42,
          source_cursor: "opaque-cursor-42",
          uncontracted: true,
        })
      )
    ).toThrow("SSE event data violated the resource notification contract")
  })
})
