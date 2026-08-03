import {
  useInfiniteQuery,
  useQuery,
  type InfiniteData,
} from "@tanstack/react-query"
import { useEffect } from "react"

import { createBoundedPageQueryOptions } from "@/data/bounded-queries"
import {
  GetSessionCatalog200Response,
  type SessionCatalogItemOutput,
  type SessionCatalogResponseOutput,
} from "@/data/generated/validators"
import {
  toServerStateResult,
  type ServerStateResult,
} from "@/data/query-result"
import { queryKeys } from "@/data/query-keys"
import { fetchValidated, withQuery } from "@/data/transport"

const catalogIdentity = {
  id: "session-catalog",
  kind: "session-catalog",
} as const

function sessionCatalogQueryOptions() {
  return createBoundedPageQueryOptions({
    identity: catalogIdentity,
    limit: 50,
    path: "/api/v1/sessions",
    schema: GetSessionCatalog200Response,
  })
}

type SessionCatalogIdentity = {
  detailSessionId?: string
  playerId?: string
  sessionId?: string
}

type SessionCatalogState = {
  isLoadingAllSessions: boolean
  isResolvingIdentity: boolean
  loadAllSessions: () => Promise<void>
  playerComplete: boolean
  refresh: () => Promise<void>
  result: ServerStateResult<SessionCatalogResponseOutput>
}

type SessionCatalog = SessionCatalogResponseOutput
type SessionCatalogItem = SessionCatalogItemOutput
type SessionCatalogResult = ServerStateResult<SessionCatalog>

function dataFromResult(
  result: SessionCatalogResult
): SessionCatalog | undefined {
  return result.status === "loading" || result.status === "error"
    ? undefined
    : result.data
}

function effectivePlayerId(
  rootCatalog: SessionCatalog | undefined,
  identity: SessionCatalogIdentity
): string | undefined {
  const pathSession =
    identity.detailSessionId === undefined
      ? undefined
      : rootCatalog?.sessions.find(
          (session) => session.id === identity.detailSessionId
        )
  if (pathSession !== undefined) return pathSession.player_id
  if (identity.detailSessionId !== undefined) return identity.playerId
  if (identity.playerId !== undefined) return identity.playerId

  return identity.sessionId === undefined
    ? undefined
    : rootCatalog?.sessions.find((session) => session.id === identity.sessionId)
        ?.player_id
}

function mergePlayerPages(
  rootCatalog: SessionCatalog,
  playerId: string | undefined,
  pages: readonly SessionCatalog[]
): SessionCatalog {
  if (playerId === undefined) return rootCatalog

  const sessions = new Map<string, SessionCatalogItem>()
  for (const session of rootCatalog.sessions) {
    if (session.player_id === playerId) sessions.set(session.id, session)
  }
  for (const page of pages) {
    for (const session of page.sessions) {
      if (session.player_id === playerId) sessions.set(session.id, session)
    }
  }
  const lastPage = pages.at(-1)

  return {
    ...rootCatalog,
    completeness:
      pages.some((page) => page.completeness === "degraded") ||
      rootCatalog.completeness === "degraded"
        ? "degraded"
        : pages.some((page) => page.completeness === "partial") ||
            rootCatalog.completeness === "partial"
          ? "partial"
          : "complete",
    continuation_cursor:
      lastPage?.continuation_cursor ?? rootCatalog.continuation_cursor,
    sessions: [...sessions.values()],
    source_cursor: lastPage?.source_cursor ?? rootCatalog.source_cursor,
  }
}

function withCatalogData(
  result: SessionCatalogResult,
  data: SessionCatalog
): SessionCatalogResult {
  if (result.status === "loading" || result.status === "error") return result
  if (result.status === "empty" && data.sessions.length > 0) {
    return { data, status: "ready" }
  }
  return { ...result, data }
}

function useSessionCatalog(
  identity: SessionCatalogIdentity = {}
): SessionCatalogState {
  const query = useQuery(sessionCatalogQueryOptions())
  const rootResult = toServerStateResult(query, {
    getCompleteness: (catalog) => catalog.completeness,
    isEmpty: (catalog) => catalog.sessions.length === 0,
  })
  const rootCatalog = dataFromResult(rootResult)
  const playerId = effectivePlayerId(rootCatalog, identity)
  const playerQuery = useInfiniteQuery<
    SessionCatalog,
    Error,
    InfiniteData<SessionCatalog, string | undefined>,
    readonly unknown[],
    string | undefined
  >({
    enabled: playerId !== undefined,
    getNextPageParam: (lastPage) => lastPage.continuation_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      fetchValidated(
        withQuery("/api/v1/sessions", {
          cursor: pageParam,
          limit: 50,
          player_id: playerId,
        }),
        GetSessionCatalog200Response,
        { signal }
      ),
    queryKey: [
      ...queryKeys.resource({
        id: "session-catalog",
        kind: "session-catalog",
        playerId,
      }),
      "all-pages",
    ] as const,
    refetchInterval: false,
  })
  const {
    data: playerData,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = playerQuery
  const playerPages = playerData?.pages ?? []
  const targetSessionId = identity.detailSessionId ?? identity.sessionId
  const knownTarget =
    targetSessionId === undefined
      ? undefined
      : rootCatalog?.sessions.find((session) => session.id === targetSessionId)
  const targetMismatchesPlayer =
    knownTarget !== undefined &&
    playerId !== undefined &&
    knownTarget.player_id !== playerId
  const targetFound =
    targetSessionId === undefined ||
    playerPages.some((page) =>
      page.sessions.some(
        (session) =>
          session.id === targetSessionId &&
          (playerId === undefined || session.player_id === playerId)
      )
    ) ||
    (knownTarget !== undefined && !targetMismatchesPlayer)
  const isResolvingIdentity =
    playerId !== undefined &&
    targetSessionId !== undefined &&
    !targetMismatchesPlayer &&
    !targetFound &&
    (playerData === undefined || hasNextPage || isFetchingNextPage)

  useEffect(() => {
    if (
      !isResolvingIdentity ||
      playerData === undefined ||
      !hasNextPage ||
      isFetchingNextPage
    ) {
      return
    }
    void fetchNextPage()
  }, [
    fetchNextPage,
    hasNextPage,
    isResolvingIdentity,
    isFetchingNextPage,
    playerData,
  ])

  const result =
    rootCatalog === undefined
      ? rootResult
      : withCatalogData(
          rootResult,
          mergePlayerPages(rootCatalog, playerId, playerPages)
        )

  return {
    isLoadingAllSessions: isFetchingNextPage,
    isResolvingIdentity,
    loadAllSessions: async () => {
      if (playerId === undefined) return
      let snapshot =
        playerData === undefined ? await playerQuery.refetch() : playerQuery
      // oxlint-disable no-await-in-loop
      while (
        snapshot.data?.pages.at(-1)?.continuation_cursor !== null &&
        snapshot.data?.pages.at(-1)?.continuation_cursor !== undefined
      ) {
        snapshot = await fetchNextPage()
      }
      // oxlint-enable no-await-in-loop
    },
    playerComplete:
      playerId !== undefined && playerData !== undefined && !hasNextPage,
    refresh: async () => {
      await Promise.all([
        query.refetch(),
        ...(playerId === undefined ? [] : [playerQuery.refetch()]),
      ])
    },
    result,
  }
}

export {
  sessionCatalogQueryOptions,
  useSessionCatalog,
  type SessionCatalog,
  type SessionCatalogIdentity,
  type SessionCatalogItem,
  type SessionCatalogResult,
  type SessionCatalogState,
}
