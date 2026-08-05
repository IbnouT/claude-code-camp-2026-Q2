import { useQuery } from "@tanstack/react-query"

import {
  GetSessionInvestigation200Response,
  type SessionInvestigationResponseOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"
import { sameSessionPlaceholder } from "@/data/session-placeholder"
import { fetchValidated } from "@/data/transport"

type SessionInvestigation = SessionInvestigationResponseOutput["investigation"]

/** The complete recorded story of one retained session. */
function useSessionInvestigation(
  sessionId: string | undefined,
  options: { live?: boolean } = {}
) {
  return useQuery({
    enabled: sessionId !== undefined,
    placeholderData: sameSessionPlaceholder(sessionId),
    // A live session's story grows, so it refreshes on the reference
    // cadence. Ended sessions are immutable and never refetch.
    refetchInterval: options.live === true ? 2000 : false,
    queryFn: ({ signal }) =>
      fetchValidated(
        `/api/v1/sessions/${sessionId}/investigation`,
        GetSessionInvestigation200Response,
        { signal }
      ),
    queryKey: queryKeys.resource({
      id: `session:${sessionId}:investigation`,
      kind: "session-investigation",
      sessionId,
    }),
  })
}

export { useSessionInvestigation, type SessionInvestigation }
