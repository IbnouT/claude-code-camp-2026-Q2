import { describe, expect, it } from "vitest"

import { queryKeys } from "@/data/query-keys"
import { sameSessionPlaceholder } from "@/data/session-placeholder"

function queryFor(sessionId: string) {
  return {
    queryKey: [
      ...queryKeys.resource({
        id: `session:${sessionId}:live:view`,
        kind: "live-view",
        sessionId,
      }),
      { through: null },
    ] as const,
  }
}

describe("sameSessionPlaceholder", () => {
  it("keeps previous data while the session is unchanged", () => {
    const placeholder = sameSessionPlaceholder("session-a")
    expect(placeholder({ value: 1 }, queryFor("session-a"))).toEqual({
      value: 1,
    })
  })

  it("drops previous data across a session switch", () => {
    const placeholder = sameSessionPlaceholder("session-b")
    expect(placeholder({ value: 1 }, queryFor("session-a"))).toBeUndefined()
  })

  it("drops previous data when nothing is selected", () => {
    const placeholder = sameSessionPlaceholder(undefined)
    expect(placeholder({ value: 1 }, queryFor("session-a"))).toBeUndefined()
  })

  it("handles a missing previous query", () => {
    const placeholder = sameSessionPlaceholder("session-a")
    expect(placeholder({ value: 1 }, undefined)).toBeUndefined()
  })
})
