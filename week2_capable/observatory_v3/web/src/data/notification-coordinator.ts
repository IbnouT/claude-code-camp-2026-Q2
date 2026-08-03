import type { QueryClient } from "@tanstack/react-query"

import type {
  ResourceChangeTargetOutput,
  ResourceNotificationOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"

type InvalidateResource = (target: ResourceChangeTargetOutput) => Promise<void>

type ResourceRefreshState = {
  latest: ResourceChangeTargetOutput
  refresh: Promise<void> | null
  trailing: boolean
}

type NotificationCursor = {
  changeCounter: number
  lastEventId: string
  serverEpoch: string
}

function resourceStateKey(target: ResourceChangeTargetOutput): string {
  return [
    target.resource_kind,
    target.resource_id,
    target.player_id ?? "",
    target.session_id ?? "",
  ].join("\0")
}

function isNewerTarget(
  incoming: ResourceChangeTargetOutput,
  current: ResourceChangeTargetOutput
): boolean {
  return (
    incoming.resource_version > current.resource_version ||
    (incoming.resource_version === current.resource_version &&
      incoming.source_cursor !== current.source_cursor)
  )
}

class ResourceNotificationCoordinator {
  private readonly invalidate: InvalidateResource
  private readonly resources = new Map<string, ResourceRefreshState>()
  private cursor: NotificationCursor | null = null

  constructor(invalidate: InvalidateResource) {
    this.invalidate = invalidate
  }

  accept(
    notification: ResourceNotificationOutput,
    lastEventId = ""
  ): Promise<void> {
    const epochChanged =
      this.cursor !== null &&
      this.cursor.serverEpoch !== notification.server_epoch
    if (
      !epochChanged &&
      this.cursor !== null &&
      notification.change_counter <= this.cursor.changeCounter
    ) {
      return Promise.resolve()
    }

    this.cursor = {
      changeCounter: notification.change_counter,
      lastEventId:
        lastEventId ||
        `${notification.server_epoch}:${notification.change_counter}`,
      serverEpoch: notification.server_epoch,
    }

    const targets =
      notification.event === "resource_changed"
        ? [
            {
              resource_id: notification.resource_id,
              resource_kind: notification.resource_kind,
              resource_version: notification.resource_version,
              player_id: notification.player_id,
              session_id: notification.session_id,
              source_cursor: notification.source_cursor,
            },
          ]
        : notification.resources
    const force = epochChanged || notification.event === "reconcile"
    return Promise.all(
      targets.map((target) => this.schedule(target, force))
    ).then(() => {})
  }

  getCursor(): NotificationCursor | null {
    return this.cursor === null ? null : { ...this.cursor }
  }

  getNewestTarget(
    resourceKind: string,
    resourceId: string,
    playerId: string | null = null,
    sessionId: string | null = null
  ): ResourceChangeTargetOutput | null {
    const state = this.resources.get(
      [resourceKind, resourceId, playerId ?? "", sessionId ?? ""].join("\0")
    )
    return state === undefined ? null : { ...state.latest }
  }

  private schedule(
    target: ResourceChangeTargetOutput,
    force: boolean
  ): Promise<void> {
    const key = resourceStateKey(target)
    const existing = this.resources.get(key)
    if (existing === undefined) {
      const state: ResourceRefreshState = {
        latest: target,
        refresh: null,
        trailing: false,
      }
      this.resources.set(key, state)
      return this.startRefresh(state)
    }

    const newer = isNewerTarget(target, existing.latest)
    if (!newer && !force) {
      return existing.refresh ?? Promise.resolve()
    }
    if (newer) {
      existing.latest = target
    }
    if (existing.refresh !== null) {
      existing.trailing = true
      return existing.refresh
    }
    return this.startRefresh(existing)
  }

  private startRefresh(state: ResourceRefreshState): Promise<void> {
    const refresh = this.refreshUntilCurrent(state).finally(() => {
      state.refresh = null
    })
    state.refresh = refresh
    return refresh
  }

  private async refreshUntilCurrent(
    state: ResourceRefreshState
  ): Promise<void> {
    do {
      state.trailing = false
      const requestedVersion = state.latest.resource_version
      const requestedCursor = state.latest.source_cursor
      // Refreshes are serialized so overlapping requests cannot occur.
      // eslint-disable-next-line no-await-in-loop
      await this.invalidate(state.latest)
      if (
        state.latest.resource_version !== requestedVersion ||
        state.latest.source_cursor !== requestedCursor
      ) {
        state.trailing = true
      }
    } while (state.trailing)
  }
}

function createQueryInvalidator(queryClient: QueryClient): InvalidateResource {
  return async (target) => {
    await queryClient.invalidateQueries(
      {
        queryKey: queryKeys.resource({
          id: target.resource_id,
          kind: target.resource_kind,
          playerId: target.player_id,
          sessionId: target.session_id,
        }),
        refetchType: "active",
      },
      { cancelRefetch: false }
    )
  }
}

export {
  ResourceNotificationCoordinator,
  createQueryInvalidator,
  isNewerTarget,
  resourceStateKey,
  type InvalidateResource,
  type NotificationCursor,
}
