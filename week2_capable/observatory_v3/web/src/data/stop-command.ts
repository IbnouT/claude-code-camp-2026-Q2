import { useMutation, useQueryClient } from "@tanstack/react-query"

import { HttpResponseError } from "@/data/contracts/response-contract"
import {
  CommandResponse,
  GetCommand200Response,
  SessionCommandRequest,
  type CommandResponseOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"
import { fetchValidated, postValidated } from "@/data/transport"

/** A cooperative stop waits out one in-flight turn's bounded grace. */
const STOP_FOLLOW_BUDGET_MS = 45_000
const STOP_FOLLOW_STEP_MS = 500

class StopFailedError extends Error {
  constructor(detail: string) {
    super(detail)
    this.name = "StopFailedError"
  }
}

type StopSessionInput = {
  session_id: string
  player_id: string
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds)
  })
}

/**
 * Submit one durable cooperative stop against the session's exact cursor
 * and follow its receipt to a terminal state. Bounded receipt follow, not
 * resource polling: it ends at succeeded, failed, or the grace budget.
 */
async function stopSession(
  input: StopSessionInput
): Promise<CommandResponseOutput> {
  // A stop targets the session identity, no evidence cursor required.
  const body = SessionCommandRequest.parse({
    idempotency_key: crypto.randomUUID(),
    actor: "observatory",
    player_id: input.player_id,
    action: "stop",
  })
  let command: CommandResponseOutput
  try {
    command = await postValidated(
      `/api/v1/sessions/${encodeURIComponent(input.session_id)}/commands`,
      body,
      202,
      CommandResponse
    )
  } catch (error) {
    throw error instanceof HttpResponseError
      ? new StopFailedError(error.message)
      : error
  }
  const deadline = Date.now() + STOP_FOLLOW_BUDGET_MS
  while (command.state !== "succeeded" && command.state !== "failed") {
    if (Date.now() > deadline) {
      throw new StopFailedError(
        "The stop did not reach a result in time. Check the session state."
      )
    }
    // eslint-disable-next-line no-await-in-loop
    await sleep(STOP_FOLLOW_STEP_MS)
    // eslint-disable-next-line no-await-in-loop
    command = await fetchValidated(
      `/api/v1/commands/${command.command_id}`,
      GetCommand200Response
    )
  }
  if (command.state === "failed") {
    throw new StopFailedError(
      command.result_detail ?? "The session could not be stopped."
    )
  }
  return command
}

function useStopCommand() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: stopSession,
    onSettled: () => {
      void client.invalidateQueries({
        queryKey: queryKeys.resourceKind("session-catalog"),
      })
      void client.invalidateQueries({
        queryKey: queryKeys.resourceKind("live-vitals"),
      })
    },
  })
}

export { StopFailedError, stopSession, useStopCommand, type StopSessionInput }
