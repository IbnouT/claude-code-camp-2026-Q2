import { useQueryClient, type QueryClient } from "@tanstack/react-query"
import { useEffect } from "react"

import type { ResourceChangeTargetOutput } from "@/data/generated/validators"
import { ResourceNotificationCoordinator } from "@/data/notification-coordinator"
import { connectResourceNotifications } from "@/data/notification-stream"
import { queryKeys } from "@/data/query-keys"

/**
 * Refresh exactly the resource a notification names. The session summary
 * target advances once per committed prefix, so it stands in for the
 * runtime derived reads (view and vitals) that have no target of their
 * own. Pinned views are immutable prefixes and never refetch.
 */
async function invalidateLiveTarget(
  client: QueryClient,
  sessionId: string,
  target: ResourceChangeTargetOutput
): Promise<void> {
  const options = { cancelRefetch: false }
  if (target.resource_kind === "session_summary") {
    await client.invalidateQueries(
      {
        queryKey: queryKeys.resource({
          id: `session:${sessionId}:live:view`,
          kind: "live-view",
          sessionId,
        }),
        predicate: (query) => {
          const dimensions = query.queryKey[5]
          return (
            typeof dimensions === "object" &&
            dimensions !== null &&
            (dimensions as { through: number | null }).through === null
          )
        },
      },
      options
    )
    await client.invalidateQueries(
      {
        queryKey: queryKeys.resource({
          id: `session:${sessionId}:live:vitals`,
          kind: "live-vitals",
          sessionId,
        }),
      },
      options
    )
    return
  }
  if (target.resource_kind === "goals") {
    await client.invalidateQueries(
      {
        queryKey: queryKeys.resource({
          id: `session:${sessionId}:goals`,
          kind: "session-goals",
          sessionId,
        }),
      },
      options
    )
    return
  }
  if (target.resource_kind === "live_partition") {
    await client.invalidateQueries(
      {
        queryKey: queryKeys.resource({
          id: target.resource_id,
          kind: "live-partition",
          sessionId,
        }),
      },
      options
    )
  }
}

/**
 * One session scoped notification stream that refreshes the followed
 * session's Live resources when its evidence advances. Bounded queries
 * plus this stream replace the reference's 2 second snapshot poll.
 */
function useLiveSessionLiveness(sessionId: string | undefined): void {
  const queryClient = useQueryClient()
  useEffect(() => {
    if (sessionId === undefined) return
    const coordinator = new ResourceNotificationCoordinator((target) =>
      invalidateLiveTarget(queryClient, sessionId, target)
    )
    const stream = connectResourceNotifications({
      coordinator,
      sessionId,
    })
    return () => {
      stream.close()
    }
  }, [queryClient, sessionId])
}

export { invalidateLiveTarget, useLiveSessionLiveness }
