import {
  ResourceNotification,
  type ResourceNotificationOutput,
  ResourceChangedNotification,
  type ResourceChangedNotificationOutput,
} from "@/data/generated/validators"

import { ResponseValidationError } from "./response-contract"

function parseResourceNotification(
  serializedData: string
): ResourceNotificationOutput {
  let body: unknown
  try {
    body = JSON.parse(serializedData)
  } catch {
    throw new ResponseValidationError("SSE event data was not valid JSON", 200)
  }

  const parsed = ResourceNotification.safeParse(body)
  if (!parsed.success) {
    throw new ResponseValidationError(
      "SSE event data violated the notification contract",
      200
    )
  }
  return parsed.data
}

function parseResourceChangedNotification(
  serializedData: string
): ResourceChangedNotificationOutput {
  const notification = parseResourceNotification(serializedData)
  const changed = ResourceChangedNotification.safeParse(notification)
  if (!changed.success) {
    throw new ResponseValidationError(
      "SSE event was not a resource_changed notification",
      200
    )
  }
  return changed.data
}

export { parseResourceChangedNotification, parseResourceNotification }
