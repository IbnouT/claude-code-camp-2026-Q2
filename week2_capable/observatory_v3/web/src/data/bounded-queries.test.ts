import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import sessionCatalogFixture from "../../../backend/openapi/fixtures/session-catalog.json?raw"
import {
  createBoundedDetailQueryOptions,
  createBoundedPageQueryOptions,
} from "@/data/bounded-queries"
import {
  GetSessionCatalog200Response,
  GetSessionSummary200Response,
} from "@/data/generated/validators"
import type { FetchImplementation } from "@/data/transport"

const clients = new Set<QueryClient>()

function createClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  clients.add(client)
  return client
}

afterEach(() => {
  for (const client of clients) {
    client.clear()
  }
  clients.clear()
})

describe("bounded query factories", () => {
  it("keys and validates a bounded page across every request dimension", async () => {
    const fetcher = vi.fn<FetchImplementation>(
      async () =>
        new Response(sessionCatalogFixture, {
          headers: { "content-type": "application/json" },
          status: 200,
        })
    )
    const options = createBoundedPageQueryOptions({
      cursor: "page-cursor-2",
      fetcher,
      identity: {
        id: "session-catalog",
        kind: "session_catalog",
        playerId: "poucet",
      },
      limit: 20,
      parameters: { player_id: "poucet" },
      path: "/api/v1/sessions",
      schema: GetSessionCatalog200Response,
      serverEpoch: "0123456789abcdef0123456789abcdef",
    })

    const result = await createClient().fetchQuery(options)

    expect(result.sessions).toHaveLength(1)
    expect(options.queryKey).toEqual([
      "observatory",
      "resource",
      "session_catalog",
      "session-catalog",
      { playerId: "poucet", sessionId: null },
      "page",
      {
        cursor: "page-cursor-2",
        limit: 20,
        parameters: { player_id: "poucet" },
        serverEpoch: "0123456789abcdef0123456789abcdef",
      },
    ])
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/sessions?player_id=poucet&cursor=page-cursor-2&limit=20",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(options.refetchInterval).toBe(false)
  })

  it("validates materialization as a typed detail state without polling", async () => {
    const fetcher = vi.fn<FetchImplementation>(async () =>
      Response.json(
        {
          capture_gaps: [],
          completeness: "partial",
          resource_id: "session:session-42:summary",
          resource_version: 2,
          retry_after_ms: 250,
          session_id: "session-42",
          source_cursor: "opaque-cursor-2",
          source_refs: ["projection"],
          state: "materialization_pending",
        },
        { status: 202 }
      )
    )
    const options = createBoundedDetailQueryOptions({
      fetcher,
      identity: {
        id: "session:session-42:summary",
        kind: "session_summary",
        sessionId: "session-42",
      },
      immutable: true,
      path: "/api/v1/sessions/session-42",
      schema: GetSessionSummary200Response,
      sourceCursor: "opaque-cursor-1",
    })

    await expect(createClient().fetchQuery(options)).resolves.toMatchObject({
      data: {
        retry_after_ms: 250,
        state: "materialization_pending",
      },
      status: "materializing",
    })
    expect(options.meta).toEqual({ immutable: true })
    expect(options.refetchInterval).toBe(false)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
