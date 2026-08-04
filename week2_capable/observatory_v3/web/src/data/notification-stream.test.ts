import { describe, expect, it, vi } from "vitest"

import notificationFixture from "../../../backend/openapi/fixtures/resource-notifications.json?raw"
import type { ResourceChangeTargetOutput } from "@/data/generated/validators"
import { ResourceNotificationCoordinator } from "@/data/notification-coordinator"
import {
  connectResourceNotifications,
  type EventSourceLike,
} from "@/data/notification-stream"

class FakeEventSource implements EventSourceLike {
  readonly listeners = new Map<
    string,
    Set<EventListenerOrEventListenerObject>
  >()
  closed = false
  readyState = 1

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const listeners = this.listeners.get(type) ?? new Set()
    listeners.add(listener)
    this.listeners.set(type, listeners)
  }

  close() {
    this.closed = true
  }

  emit(type: string, event: Event) {
    for (const listener of this.listeners.get(type) ?? []) {
      if (typeof listener === "function") {
        listener(event)
      } else {
        listener.handleEvent(event)
      }
    }
  }
}

function changedFixture(): Record<string, unknown> {
  const fixture: unknown = JSON.parse(notificationFixture)
  if (!Array.isArray(fixture) || typeof fixture[0] !== "object") {
    throw new Error("Expected a changed notification fixture")
  }
  return fixture[0] as Record<string, unknown>
}

describe("resource notification stream", () => {
  it("retains event identity, reports reconnecting, and closes cleanly", async () => {
    const source = new FakeEventSource()
    const states: string[] = []
    const faults: Error[] = []
    const invalidate = vi.fn<
      (_target: ResourceChangeTargetOutput) => Promise<void>
    >(async () => {})
    const coordinator = new ResourceNotificationCoordinator(invalidate)
    let requestedUrl = ""
    const stream = connectResourceNotifications({
      coordinator,
      eventSourceFactory: (url) => {
        requestedUrl = url
        return source
      },
      onFault: (error) => faults.push(error),
      onStateChange: (state) => states.push(state),
      sessionId: "session-42",
    })
    const changed = changedFixture()

    source.emit("open", new Event("open"))
    source.emit(
      "resource_changed",
      new MessageEvent("resource_changed", {
        data: JSON.stringify(changed),
        lastEventId: `${changed.server_epoch}:${changed.change_counter}`,
      })
    )
    await vi.waitFor(() => {
      expect(invalidate).toHaveBeenCalledTimes(1)
    })
    source.emit("error", new Event("error"))

    expect(requestedUrl).toBe("/api/v1/notifications?session_id=session-42")
    expect(states).toEqual(["connecting", "open", "reconnecting"])
    expect(stream.getCursor()).toMatchObject({
      changeCounter: changed.change_counter,
      serverEpoch: changed.server_epoch,
    })
    expect(faults).toEqual([])

    stream.close()
    expect(source.closed).toBe(true)
    expect(states.at(-1)).toBe("closed")
  })

  it("replaces a permanently closed source with backoff", () => {
    vi.useFakeTimers()
    try {
      const sources: FakeEventSource[] = []
      const stream = connectResourceNotifications({
        coordinator: new ResourceNotificationCoordinator(async () => {}),
        eventSourceFactory: () => {
          const source = new FakeEventSource()
          sources.push(source)
          return source
        },
      })
      // The proxy answered with an HTTP failure: the source is terminal.
      sources[0].readyState = 2
      sources[0].emit("error", new Event("error"))
      expect(sources[0].closed).toBe(true)
      expect(sources).toHaveLength(1)
      vi.advanceTimersByTime(1_000)
      expect(sources).toHaveLength(2)
      // The replacement dies too: the next retry waits twice as long.
      sources[1].readyState = 2
      sources[1].emit("error", new Event("error"))
      vi.advanceTimersByTime(1_000)
      expect(sources).toHaveLength(2)
      vi.advanceTimersByTime(1_000)
      expect(sources).toHaveLength(3)
      // A recovered stream resets the backoff and keeps flowing.
      sources[2].emit("open", new Event("open"))
      stream.close()
      vi.advanceTimersByTime(60_000)
      expect(sources).toHaveLength(3)
      expect(sources[2].closed).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it("reports invalid notification payloads without closing the stream", () => {
    const source = new FakeEventSource()
    const faults: Error[] = []
    const stream = connectResourceNotifications({
      coordinator: new ResourceNotificationCoordinator(async () => {}),
      eventSourceFactory: () => source,
      onFault: (error) => faults.push(error),
      sessionId: "session-42",
    })

    source.emit(
      "resource_changed",
      new MessageEvent("resource_changed", { data: "{" })
    )

    expect(faults).toHaveLength(1)
    expect(faults[0]).toMatchObject({ kind: "validation" })
    expect(source.closed).toBe(false)
    stream.close()
  })
})
