import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import notificationFixture from "../../../backend/openapi/fixtures/resource-notifications.json?raw"
import { parseResourceNotification } from "@/data/contracts/sse-contract"
import type { ResourceChangeTargetOutput } from "@/data/generated/validators"
import {
  ResourceNotificationCoordinator,
  createQueryInvalidator,
} from "@/data/notification-coordinator"

function loadFixture() {
  const fixture: unknown = JSON.parse(notificationFixture)
  if (!Array.isArray(fixture)) {
    throw new Error("Expected the notification fixture to be an array")
  }
  const changed = parseResourceNotification(JSON.stringify(fixture[0]))
  const reconciliation = parseResourceNotification(JSON.stringify(fixture[1]))
  if (
    changed.event !== "resource_changed" ||
    reconciliation.event !== "reconcile"
  ) {
    throw new Error("Expected both notification fixture variants")
  }
  return { changed, reconciliation }
}

function deferred() {
  let resolve = () => {}
  const promise = new Promise<void>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

describe("resource notification coordinator", () => {
  it("coalesces a burst into one in-flight and one newest trailing refresh", async () => {
    const firstRefresh = deferred()
    const invalidated: ResourceChangeTargetOutput[] = []
    const invalidate = vi.fn<
      (target: ResourceChangeTargetOutput) => Promise<void>
    >(async (target) => {
      invalidated.push(target)
      if (invalidated.length === 1) {
        await firstRefresh.promise
      }
    })
    const coordinator = new ResourceNotificationCoordinator(invalidate)
    const { changed } = loadFixture()
    const second = {
      ...changed,
      change_counter: changed.change_counter + 1,
      resource_version: changed.resource_version + 1,
      source_cursor: "obc1_second",
    }
    const newest = {
      ...second,
      change_counter: second.change_counter + 1,
      resource_version: second.resource_version + 1,
      source_cursor: "obc1_newest",
    }

    const firstResult = coordinator.accept(changed)
    const secondResult = coordinator.accept(second)
    const newestResult = coordinator.accept(newest)
    expect(invalidate).toHaveBeenCalledTimes(1)

    firstRefresh.resolve()
    await Promise.all([firstResult, secondResult, newestResult])

    expect(invalidate).toHaveBeenCalledTimes(2)
    expect(invalidated.at(-1)).toMatchObject({
      resource_version: newest.resource_version,
      source_cursor: "obc1_newest",
    })
    expect(
      coordinator.getNewestTarget(newest.resource_kind, newest.resource_id)
    ).toMatchObject({ source_cursor: "obc1_newest" })
  })

  it("performs one bounded refresh per epoch reconciliation target", async () => {
    const invalidate = vi.fn<
      (_target: ResourceChangeTargetOutput) => Promise<void>
    >(async () => {})
    const coordinator = new ResourceNotificationCoordinator(invalidate)
    const { changed, reconciliation } = loadFixture()

    await coordinator.accept(changed)
    await coordinator.accept(reconciliation, "fedcba:0")

    expect(invalidate).toHaveBeenCalledTimes(2)
    expect(coordinator.getCursor()).toEqual({
      changeCounter: 0,
      lastEventId: "fedcba:0",
      serverEpoch: reconciliation.server_epoch,
    })
  })

  it("invalidates only the matching bounded resource prefix without cancellation", async () => {
    const queryClient = new QueryClient()
    const invalidation = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue()
    const { changed } = loadFixture()
    const invalidate = createQueryInvalidator(queryClient)

    await invalidate(changed)

    expect(invalidation).toHaveBeenCalledWith(
      {
        queryKey: [
          "observatory",
          "resource",
          changed.resource_kind,
          changed.resource_id,
          {
            playerId: changed.player_id,
            sessionId: changed.session_id,
          },
        ],
        refetchType: "active",
      },
      { cancelRefetch: false }
    )
  })
})
