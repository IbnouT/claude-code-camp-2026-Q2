import {
  GetResourceNotificationsQueryParams,
  type ResourceNotificationOutput,
} from "@/data/generated/validators"
import {
  ResourceNotificationCoordinator,
  type NotificationCursor,
} from "@/data/notification-coordinator"
import { parseResourceNotification } from "@/data/contracts/sse-contract"
import { ResponseValidationError } from "@/data/contracts/response-contract"
import { withQuery } from "@/data/transport"

type NotificationConnectionState =
  "closed" | "connecting" | "open" | "reconnecting"

type EventSourceLike = {
  addEventListener: (
    type: string,
    listener: EventListenerOrEventListenerObject
  ) => void
  close: () => void
}

type EventSourceFactory = (url: string) => EventSourceLike

type NotificationStreamOptions = {
  coordinator: ResourceNotificationCoordinator
  eventSourceFactory?: EventSourceFactory
  onFault?: (error: Error) => void
  onStateChange?: (state: NotificationConnectionState) => void
  sessionId: string
}

type NotificationStream = {
  close: () => void
  getCursor: () => NotificationCursor | null
}

function defaultEventSourceFactory(url: string): EventSourceLike {
  return new EventSource(url)
}

function messageEvent(event: Event): MessageEvent<string> {
  if (!(event instanceof MessageEvent) || typeof event.data !== "string") {
    throw new ResponseValidationError("SSE notification was not a text message")
  }
  return event
}

function connectResourceNotifications({
  coordinator,
  eventSourceFactory = defaultEventSourceFactory,
  onFault = () => {},
  onStateChange = () => {},
  sessionId,
}: NotificationStreamOptions): NotificationStream {
  const query = GetResourceNotificationsQueryParams.parse({
    session_id: sessionId,
  })
  const url = withQuery("/api/v1/notifications", {
    session_id: query.session_id,
  })
  onStateChange("connecting")
  const source = eventSourceFactory(url)
  let closed = false

  const accept = (event: Event) => {
    try {
      const message = messageEvent(event)
      const notification: ResourceNotificationOutput =
        parseResourceNotification(message.data)
      void coordinator.accept(notification, message.lastEventId).catch(onFault)
    } catch (error) {
      onFault(
        error instanceof Error
          ? error
          : new ResponseValidationError("SSE notification failed")
      )
    }
  }

  source.addEventListener("resource_changed", accept)
  source.addEventListener("reconcile", accept)
  source.addEventListener("open", () => {
    if (!closed) {
      onStateChange("open")
    }
  })
  source.addEventListener("error", () => {
    if (!closed) {
      onStateChange("reconnecting")
    }
  })

  return {
    close: () => {
      if (!closed) {
        closed = true
        source.close()
        onStateChange("closed")
      }
    },
    getCursor: () => coordinator.getCursor(),
  }
}

export {
  connectResourceNotifications,
  type EventSourceFactory,
  type EventSourceLike,
  type NotificationConnectionState,
  type NotificationStream,
  type NotificationStreamOptions,
}
