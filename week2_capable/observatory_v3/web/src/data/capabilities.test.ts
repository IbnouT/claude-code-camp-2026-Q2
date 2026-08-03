import { afterEach, describe, expect, it, vi } from "vitest"

import { capabilitiesQueryOptions } from "@/data/capabilities"
import {
  ResponseValidationError,
  TransportError,
} from "@/data/contracts/response-contract"
import { createObservatoryQueryClient } from "@/data/query-client"
import { queryKeys } from "@/data/query-keys"
import type { FetchImplementation } from "@/data/transport"

const capabilities = {
  features: ["live", "replay"],
  sources: [
    {
      contract_digest: null,
      detail: "Configured source is readable",
      id: "gateway",
      label: "Gateway journals",
      state: "ready",
    },
  ],
  version: 1,
  voice: {
    detail: "Voice is disabled",
    enabled: false,
    endpoint_template: null,
    max_characters: 400,
  },
} as const

const clients = new Set<ReturnType<typeof createObservatoryQueryClient>>()

function createClient() {
  const client = createObservatoryQueryClient()
  clients.add(client)
  return client
}

afterEach(() => {
  for (const client of clients) {
    client.clear()
  }
  clients.clear()
})

describe("capabilities query", () => {
  it("deduplicates identical consumers and reuses the validated cache", async () => {
    let resolveResponse = (_response: Response) => {}
    const fetcher = vi.fn<FetchImplementation>(
      () =>
        new Promise<Response>((resolve) => {
          resolveResponse = resolve
        })
    )
    const client = createClient()
    const options = capabilitiesQueryOptions({ fetcher })

    const first = client.fetchQuery(options)
    const second = client.fetchQuery(options)

    expect(fetcher).toHaveBeenCalledTimes(1)
    resolveResponse(Response.json(capabilities))
    await expect(Promise.all([first, second])).resolves.toEqual([
      capabilities,
      capabilities,
    ])

    await expect(client.fetchQuery(options)).resolves.toEqual(capabilities)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it("does not retry generated-schema validation failures", async () => {
    const fetcher = vi.fn<FetchImplementation>(async () =>
      Response.json({ features: ["live"] })
    )
    const client = createClient()

    await expect(
      client.fetchQuery(capabilitiesQueryOptions({ fetcher }))
    ).rejects.toBeInstanceOf(ResponseValidationError)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it("cancels the native request when the last selected query is cancelled", async () => {
    let aborted = false
    const fetcher = vi.fn<FetchImplementation>(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            aborted = true
            reject(new DOMException("Cancelled", "AbortError"))
          })
        })
    )
    const client = createClient()
    const request = client.fetchQuery(capabilitiesQueryOptions({ fetcher }))

    await vi.waitFor(() => {
      expect(fetcher).toHaveBeenCalledTimes(1)
    })
    await client.cancelQueries({ queryKey: queryKeys.capabilities() })
    await request.catch(() => {})

    expect(aborted).toBe(true)
  })

  it("keeps pre-response failures typed as transport errors", async () => {
    const fetcher = vi.fn<FetchImplementation>(async () => {
      throw new Error("offline")
    })
    const client = createClient()

    await expect(
      client.fetchQuery(capabilitiesQueryOptions({ fetcher }))
    ).rejects.toBeInstanceOf(TransportError)
    expect(fetcher).toHaveBeenCalledTimes(3)
  })
})
