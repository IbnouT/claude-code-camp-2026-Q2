import { keepPreviousData, useQuery } from "@tanstack/react-query"

import {
  GetSessionGoals200Response,
  type GoalPageResponseOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"
import { fetchValidated } from "@/data/transport"

type SessionGoals = GoalPageResponseOutput
type SessionGoalItem = SessionGoals["items"][number]

/**
 * The session's retained goals, newest last: the authored objective and
 * every applied operator revision, each with its turns and nudges.
 */
function useSessionGoals(sessionId: string | undefined) {
  return useQuery({
    enabled: sessionId !== undefined,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) =>
      fetchValidated(
        `/api/v1/sessions/${sessionId}/goals`,
        GetSessionGoals200Response,
        { signal }
      ),
    queryKey: [
      ...queryKeys.resource({
        id: `session:${sessionId}:goals`,
        kind: "session-goals",
        sessionId,
      }),
    ] as const,
  })
}

export { useSessionGoals, type SessionGoalItem, type SessionGoals }
