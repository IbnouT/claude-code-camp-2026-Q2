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
  | "closed"
  | "connecting"
  | "open"
  | "reconnecting"

type EventSourceLike = {
  addEventListener: (
    type: string,
    listener: EventListenerOrEventListenerObject
  ) => void
  close: () => void
  readyState?: number
}

type EventSourceFactory = (url: string) => EventSourceLike

type NotificationStreamOptions = {
  coordinator: ResourceNotificationCoordinator
  eventSourceFactory?: EventSourceFactory
  onFault?: (error: Error) => void
  onStateChange?: (state: NotificationConnectionState) => void
  scope?: "catalog"
  sessionId?: string
}

type NotificationStream = {
  close: () => void
  getCursor: () => NotificationCursor | null
}

/** The event stream's terminal readyState, after which it never retries. */
const EVENT_SOURCE_CLOSED = 2

const STREAM_RETRY_MIN_MS = 1_000
const STREAM_RETRY_MAX_MS = 15_000

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
  scope,
  sessionId,
}: NotificationStreamOptions): NotificationStream {
  const query = GetResourceNotificationsQueryParams.parse({
    session_id: sessionId,
    scope,
  })
  const url = withQuery("/api/v1/notifications", {
    scope: query.scope,
    session_id: query.session_id,
  })
  let closed = false
  let source: EventSourceLike | null = null
  let retryDelay = STREAM_RETRY_MIN_MS
  let retryTimer: ReturnType<typeof setTimeout> | null = null

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

  const start = () => {
    const current = eventSourceFactory(url)
    source = current
    current.addEventListener("resource_changed", accept)
    current.addEventListener("reconcile", accept)
    current.addEventListener("open", () => {
      if (!closed) {
        retryDelay = STREAM_RETRY_MIN_MS
        onStateChange("open")
      }
    })
    current.addEventListener("error", () => {
      if (closed) {
        return
      }
      onStateChange("reconnecting")
      // The browser retries dropped connections on its own. An HTTP-level
      // failure, a proxy answering while the backend restarts, closes the
      // source permanently, so a fresh one takes over with backoff. The
      // coordinator reconciles any missed changes through the server epoch.
      if (current.readyState === EVENT_SOURCE_CLOSED && retryTimer === null) {
        current.close()
        retryTimer = setTimeout(() => {
          retryTimer = null
          if (!closed) {
            start()
          }
        }, retryDelay)
        retryDelay = Math.min(retryDelay * 2, STREAM_RETRY_MAX_MS)
      }
    })
  }

  onStateChange("connecting")
  start()

  return {
    close: () => {
      if (!closed) {
        closed = true
        if (retryTimer !== null) {
          clearTimeout(retryTimer)
          retryTimer = null
        }
        source?.close()
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
