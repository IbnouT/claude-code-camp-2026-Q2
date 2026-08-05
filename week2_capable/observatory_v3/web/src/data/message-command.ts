import { useMutation, useQueryClient } from "@tanstack/react-query"

import { HttpResponseError } from "@/data/contracts/response-contract"
import {
  CommandResponse,
  GetSessionSummary200Response,
  SessionCommandRequest,
  type CommandResponseOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"
import { fetchValidated, postValidated } from "@/data/transport"

type OperatorMessageInput = {
  session_id: string
  player_id: string
  action: "guide" | "revise"
  instruction: string
}

/**
 * Guide and revise instruct against observed state, so they keep the
 * exact cursor guard. A busy agent can advance the cursor between read
 * and submit, so the freshest cursor is retried a bounded number of
 * times before the conflict surfaces.
 */
const MESSAGE_CURSOR_ATTEMPTS = 3

class MessageFailedError extends Error {
  constructor(detail: string) {
    super(detail)
    this.name = "MessageFailedError"
  }
}

async function sendOperatorMessage(
  input: OperatorMessageInput
): Promise<CommandResponseOutput> {
  for (let attempt = 1; attempt <= MESSAGE_CURSOR_ATTEMPTS; attempt += 1) {
    // The command guard compares the composite index cursor, which only
    // index backed resources carry. The session summary is the cheapest.
    const summary = await fetchValidated(
      `/api/v1/sessions/${encodeURIComponent(input.session_id)}`,
      GetSessionSummary200Response
    )
    const body = SessionCommandRequest.parse({
      idempotency_key: crypto.randomUUID(),
      actor: "observatory",
      player_id: input.player_id,
      action: input.action,
      instruction: input.instruction,
      expected_cursor: summary.source_cursor,
    })
    try {
      return await postValidated(
        `/api/v1/sessions/${encodeURIComponent(input.session_id)}/commands`,
        body,
        202,
        CommandResponse
      )
    } catch (error) {
      const conflicted =
        error instanceof HttpResponseError && error.status === 409
      if (!conflicted || attempt === MESSAGE_CURSOR_ATTEMPTS) {
        throw error instanceof HttpResponseError
          ? new MessageFailedError(error.message)
          : error
      }
    }
  }
  throw new MessageFailedError("The message could not be submitted.")
}

function useOperatorMessage() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: sendOperatorMessage,
    onSettled: () => {
      void client.invalidateQueries({
        queryKey: queryKeys.resourceKind("live-partition"),
      })
      void client.invalidateQueries({
        queryKey: queryKeys.resourceKind("session-goals"),
      })
    },
  })
}

export {
  MessageFailedError,
  sendOperatorMessage,
  useOperatorMessage,
  type OperatorMessageInput,
}
