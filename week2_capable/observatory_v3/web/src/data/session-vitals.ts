import { keepPreviousData, useQuery } from "@tanstack/react-query"

import {
  GetLiveVitals200Response,
  type LiveVitalsResponseOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"
import { fetchValidated } from "@/data/transport"

type SessionVitals = LiveVitalsResponseOutput
type VitalsFields = SessionVitals["fields"]

/**
 * Observed player state for one session, derived server side from retained
 * gateway observations. The roster reads level, HP, mana, and gold from it.
 */
function useSessionVitals(sessionId: string | undefined) {
  return useQuery({
    enabled: sessionId !== undefined,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) =>
      fetchValidated(
        `/api/v1/live/${sessionId}/vitals`,
        GetLiveVitals200Response,
        { signal }
      ),
    queryKey: [
      ...queryKeys.resource({
        id: `session:${sessionId}:live:vitals`,
        kind: "live-vitals",
        sessionId,
      }),
    ] as const,
  })
}

export { useSessionVitals, type SessionVitals, type VitalsFields }
