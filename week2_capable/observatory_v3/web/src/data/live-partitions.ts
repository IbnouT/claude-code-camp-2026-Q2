import { useQuery } from "@tanstack/react-query"

import {
  GetLivePartition200Response,
  type LivePartitionResponseOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"
import { sameSessionPlaceholder } from "@/data/session-placeholder"
import { fetchValidated } from "@/data/transport"

type LivePartition =
  | "identity-lifecycle"
  | "world-map"
  | "position-path"
  | "thought-activity"
  | "vitals-combat"
  | "economics"
  | "controls"
  | "diagnostics"

type LivePartitionData = LivePartitionResponseOutput

/**
 * One content versioned Live partition for a session. Each panel reads
 * its own partition and refreshes from the session notification stream.
 */
function useLivePartition(
  sessionId: string | undefined,
  partition: LivePartition
) {
  return useQuery({
    enabled: sessionId !== undefined,
    placeholderData: sameSessionPlaceholder(sessionId),
    queryFn: ({ signal }) =>
      fetchValidated(
        `/api/v1/live/${sessionId}/${partition}`,
        GetLivePartition200Response,
        { signal }
      ),
    queryKey: [
      ...queryKeys.resource({
        id: `session:${sessionId}:live:${partition}`,
        kind: "live-partition",
        sessionId,
      }),
    ] as const,
  })
}

export { useLivePartition, type LivePartition, type LivePartitionData }
