import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import type { ResourceChangeTargetOutput } from "@/data/generated/validators"
import { invalidateLiveTarget } from "@/data/live-session-liveness"
import { queryKeys } from "@/data/query-keys"

function target(
  kind: string,
  resourceId: string
): ResourceChangeTargetOutput {
  return {
    resource_kind: kind,
    resource_id: resourceId,
    resource_version: 1,
    source_cursor: "obc1_x",
  } as ResourceChangeTargetOutput
}

function viewKey(sessionId: string, through: number | null) {
  return [
    ...queryKeys.resource({
      id: `session:${sessionId}:live:view`,
      kind: "live-view",
      sessionId,
    }),
    { through },
  ] as const
}

describe("invalidateLiveTarget", () => {
  it("refreshes the latest view but never a pinned prefix", async () => {
    const client = new QueryClient()
    client.setQueryData(viewKey("s1", null), { latest: true })
    client.setQueryData(viewKey("s1", 40), { pinned: true })

    await invalidateLiveTarget(
      client,
      "s1",
      target("session_summary", "session:s1:summary")
    )

    expect(client.getQueryState(viewKey("s1", null))?.isInvalidated).toBe(true)
    expect(client.getQueryState(viewKey("s1", 40))?.isInvalidated).toBe(false)
  })

  it("routes a partition target to that partition only", async () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, "invalidateQueries")

    await invalidateLiveTarget(
      client,
      "s1",
      target("live_partition", "session:s1:live:economics")
    )

    expect(invalidate).toHaveBeenCalledTimes(1)
    expect(invalidate).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: queryKeys.resource({
          id: "session:s1:live:economics",
          kind: "live-partition",
          sessionId: "s1",
        }),
      }),
      { cancelRefetch: false }
    )
  })

  it("ignores targets with no live consumer", async () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, "invalidateQueries")

    await invalidateLiveTarget(client, "s1", target("cost", "session:s1:cost"))

    expect(invalidate).not.toHaveBeenCalled()
  })
})
