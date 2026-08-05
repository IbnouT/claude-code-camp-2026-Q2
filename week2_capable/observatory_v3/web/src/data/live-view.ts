import { useQuery } from "@tanstack/react-query"

import {
  GetLiveView200Response,
  type LiveViewResponseOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"
import { sameSessionPlaceholder } from "@/data/session-placeholder"
import { fetchValidated, withQuery } from "@/data/transport"

type LiveView = LiveViewResponseOutput
type LiveJourney = LiveView["view"]

/**
 * The derived Live view of one session, whole or bounded to a pinned
 * prefix. The pinned fetch and the latest fetch run as separate queries
 * so the transport can pin without losing the live extent.
 */
function useLiveView(
  sessionId: string | undefined,
  through: number | null = null
) {
  return useQuery({
    enabled: sessionId !== undefined,
    placeholderData: sameSessionPlaceholder(sessionId),
    queryFn: ({ signal }) =>
      fetchValidated(
        withQuery(`/api/v1/live/${sessionId}/view`, {
          through: through ?? undefined,
        }),
        GetLiveView200Response,
        { signal }
      ),
    queryKey: [
      ...queryKeys.resource({
        id: `session:${sessionId}:live:view`,
        kind: "live-view",
        sessionId,
      }),
      { through },
    ] as const,
  })
}

export { useLiveView, type LiveJourney, type LiveView }
