import { useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"

import { ResourceNotificationCoordinator } from "@/data/notification-coordinator"
import { connectResourceNotifications } from "@/data/notification-stream"
import { queryKeys } from "@/data/query-keys"

/** Every resource kind the Live screen reads for one session. */
const LIVE_RESOURCE_KINDS = [
  "live-vitals",
  "session-goals",
  "live-partition",
  "session-map",
  "session-cost",
  "live-view",
] as const

/**
 * One session scoped notification stream that refreshes every Live
 * resource when the session's evidence advances. Bounded queries plus
 * this stream replace the reference's 2 second snapshot poll.
 */
function useLiveSessionLiveness(sessionId: string | undefined): void {
  const queryClient = useQueryClient()
  useEffect(() => {
    if (sessionId === undefined) return
    const coordinator = new ResourceNotificationCoordinator(async () => {
      for (const kind of LIVE_RESOURCE_KINDS) {
        await queryClient.invalidateQueries(
          { queryKey: queryKeys.resourceKind(kind) },
          { cancelRefetch: false }
        )
      }
    })
    const stream = connectResourceNotifications({
      coordinator,
      sessionId,
    })
    return () => {
      stream.close()
    }
  }, [queryClient, sessionId])
}

export { useLiveSessionLiveness, LIVE_RESOURCE_KINDS }
