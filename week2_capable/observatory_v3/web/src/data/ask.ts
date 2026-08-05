import {
  AskEvidence200Response,
  AskRequest,
  type AskResponseOutput,
  type QueryScope,
} from "@/data/generated/validators"
import { postValidated } from "@/data/transport"

/**
 * One evidence question against the retained scope. Answers cite
 * retained records only, model use stays off.
 */
async function askQuestion(
  question: string,
  scope: QueryScope,
  signal?: AbortSignal
): Promise<AskResponseOutput> {
  const body = AskRequest.parse({
    question,
    scope,
    allow_model: false,
    allow_summary: false,
  })
  return postValidated("/api/v1/ask", body, 200, AskEvidence200Response, {
    signal,
  })
}

export { askQuestion, type AskResponseOutput, type QueryScope }
