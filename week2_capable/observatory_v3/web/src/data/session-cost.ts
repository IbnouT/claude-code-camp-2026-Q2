import { keepPreviousData, useQuery } from "@tanstack/react-query"

import {
  CostRangeResponse,
  type CostRangeResponseOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"
import { fetchValidated } from "@/data/transport"

type SessionCost = CostRangeResponseOutput

/**
 * Retained spend for one session: the total and the per response
 * contributors, newest last, for the economics block and sparkline.
 */
function useSessionCost(sessionId: string | undefined) {
  return useQuery({
    enabled: sessionId !== undefined,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) =>
      fetchValidated(`/api/v1/sessions/${sessionId}/cost`, CostRangeResponse, {
        signal,
      }),
    queryKey: [
      ...queryKeys.resource({
        id: `session:${sessionId}:cost`,
        kind: "session-cost",
        sessionId,
      }),
    ] as const,
  })
}

export { useSessionCost, type SessionCost }
