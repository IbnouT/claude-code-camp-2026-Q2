import { useMutation, useQueryClient } from "@tanstack/react-query"

import {
  CommandResponse,
  GetCommand200Response,
  StartCommandRequest,
  type CommandResponseOutput,
  type StartCommandRequestOutput,
} from "@/data/generated/validators"
import { sessionCatalogQueryOptions } from "@/data/session-catalog"
import { fetchValidated, postValidated } from "@/data/transport"

/** The backend readiness budget for one start, plus reconnect headroom. */
const START_FOLLOW_BUDGET_MS = 70_000
const START_FOLLOW_STEP_MS = 500

class StartFailedError extends Error {
  constructor(detail: string) {
    super(detail)
    this.name = "StartFailedError"
  }
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds)
  })
}

/**
 * Submit one durable start command and follow its receipt to a terminal
 * state. This is a bounded post-command follow of a single receipt, not
 * resource polling: it ends at succeeded, failed, or the readiness budget.
 * The returned command carries the resulting session identity.
 */
async function startSession(
  input: StartCommandRequestOutput
): Promise<CommandResponseOutput> {
  const body = StartCommandRequest.parse(input)
  let command = await postValidated(
    "/api/v1/commands/start",
    body,
    202,
    CommandResponse
  )
  const deadline = Date.now() + START_FOLLOW_BUDGET_MS
  while (command.state !== "succeeded" && command.state !== "failed") {
    if (Date.now() > deadline) {
      throw new StartFailedError(
        "The start did not reach a result in time. Check the roster."
      )
    }
    // eslint-disable-next-line no-await-in-loop
    await sleep(START_FOLLOW_STEP_MS)
    // eslint-disable-next-line no-await-in-loop
    command = await fetchValidated(
      `/api/v1/commands/${command.command_id}`,
      GetCommand200Response
    )
  }
  if (command.state === "failed") {
    throw new StartFailedError(
      command.result_detail ?? "The session could not be started."
    )
  }
  return command
}

function useStartCommand() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: startSession,
    onSettled: () => {
      void client.invalidateQueries({
        queryKey: sessionCatalogQueryOptions().queryKey,
      })
    },
  })
}

export { StartFailedError, startSession, useStartCommand }
