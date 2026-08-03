import { describe, expect, it } from "vitest"

import notificationFixture from "../../../../backend/openapi/fixtures/resource-notifications.json?raw"

import {
  parseResourceChangedNotification,
  parseResourceNotification,
} from "./sse-contract"

describe("resource notification contracts", () => {
  it("accepts changed and bounded epoch-reconciliation notifications", () => {
    const notifications: unknown = JSON.parse(notificationFixture)
    if (!Array.isArray(notifications)) {
      throw new Error("Expected the notification fixture to be an array")
    }

    const event = parseResourceChangedNotification(
      JSON.stringify(notifications[0])
    )
    const reconciliation = parseResourceNotification(
      JSON.stringify(notifications[1])
    )

    expect(event.resource_kind).toBe("session_summary")
    expect(event.resource_version).toBe(3)
    expect(reconciliation).toMatchObject({
      event: "reconcile",
      reason: "epoch_mismatch",
    })
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
          change_counter: 42,
          contract_version: "v1",
          event: "resource_changed",
          resource_id: "session-42",
          resource_kind: "session_summary",
          resource_version: 42,
          server_epoch: "0123456789abcdef0123456789abcdef",
          source_cursor: "opaque-cursor-42",
          uncontracted: true,
        })
      )
    ).toThrow("SSE event data violated the notification contract")
  })
})
