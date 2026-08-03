import { queryOptions } from "@tanstack/react-query"

import type { ContractSchema } from "@/data/contracts/response-contract"
import { parseContractResponse } from "@/data/contracts/response-contract"
import {
  MaterializationPendingResponse,
  type MaterializationPendingResponseOutput,
} from "@/data/generated/validators"
import { queryKeys, type ResourceIdentity } from "@/data/query-keys"
import {
  fetchResponse,
  fetchValidated,
  type FetchImplementation,
} from "@/data/transport"
import { withQuery } from "@/data/transport"

type BoundedPageOptions<Output> = {
  cursor?: string
  fetcher?: FetchImplementation
  identity: ResourceIdentity
  limit: number
  parameters?: Readonly<Record<string, number | string | undefined>>
  path: string
  schema: ContractSchema<Output>
  serverEpoch?: string
}

type BoundedDetailOptions<Output> = {
  fetcher?: FetchImplementation
  identity: ResourceIdentity
  immutable: boolean
  path: string
  schema: ContractSchema<Output>
  serverEpoch?: string
  sourceCursor?: string
}

type BoundedDetailResult<Output> =
  | { data: Output; status: "ready" }
  | {
      data: MaterializationPendingResponseOutput
      status: "materializing"
    }

function compactParameters(
  parameters: Readonly<Record<string, number | string | undefined>>
): Readonly<Record<string, number | string>> {
  return Object.fromEntries(
    Object.entries(parameters).filter(
      (entry): entry is [string, number | string] => entry[1] !== undefined
    )
  )
}

function createBoundedPageQueryOptions<Output>(
  options: BoundedPageOptions<Output>
) {
  const parameters = compactParameters(options.parameters ?? {})
  const dimensions = {
    cursor: options.cursor ?? null,
    limit: options.limit,
    parameters,
    serverEpoch: options.serverEpoch ?? null,
  }

  return queryOptions({
    queryFn: ({ signal }) =>
      fetchValidated(
        withQuery(options.path, {
          ...parameters,
          cursor: options.cursor,
          limit: options.limit,
        }),
        options.schema,
        { fetcher: options.fetcher, signal }
      ),
    queryKey: queryKeys.resourcePage(options.identity, dimensions),
    refetchInterval: false,
  })
}

function createBoundedDetailQueryOptions<Output>(
  options: BoundedDetailOptions<Output>
) {
  return queryOptions({
    meta: { immutable: options.immutable },
    queryFn: async ({ signal }): Promise<BoundedDetailResult<Output>> => {
      const response = await fetchResponse(options.path, {
        fetcher: options.fetcher,
        signal,
      })
      if (response.status === 202) {
        return {
          data: await parseContractResponse(
            response,
            new Map([[202, MaterializationPendingResponse]])
          ),
          status: "materializing",
        }
      }
      return {
        data: await parseContractResponse(
          response,
          new Map([[200, options.schema]])
        ),
        status: "ready",
      }
    },
    queryKey: queryKeys.resourceDetail(options.identity, {
      serverEpoch: options.serverEpoch ?? null,
      sourceCursor: options.sourceCursor ?? null,
    }),
    refetchInterval: false,
  })
}

export {
  createBoundedDetailQueryOptions,
  createBoundedPageQueryOptions,
  type BoundedDetailOptions,
  type BoundedDetailResult,
  type BoundedPageOptions,
}
