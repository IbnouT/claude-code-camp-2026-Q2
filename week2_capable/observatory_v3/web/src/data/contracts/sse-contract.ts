import {
  ResourceChangedNotification,
  type ResourceChangedNotificationOutput,
} from "@/data/generated/validators"

import { ContractFault } from "./response-contract"

export function parseResourceChangedNotification(
  serializedData: string
): ResourceChangedNotificationOutput {
  let body: unknown
  try {
    body = JSON.parse(serializedData)
  } catch {
    throw new ContractFault("SSE event data was not valid JSON", 200)
  }

  const parsed = ResourceChangedNotification.safeParse(body)
  if (!parsed.success) {
    throw new ContractFault(
      "SSE event data violated the resource notification contract",
      200
    )
  }
  return parsed.data
}
