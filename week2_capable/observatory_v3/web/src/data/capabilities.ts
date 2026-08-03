import { queryOptions, useQuery } from "@tanstack/react-query"

import {
  GetCapabilities200Response,
  type ObservatoryCapabilitiesOutput,
} from "@/data/generated/validators"
import { queryKeys } from "@/data/query-keys"
import {
  toServerStateResult,
  type ServerStateResult,
} from "@/data/query-result"
import { fetchValidated, type FetchImplementation } from "@/data/transport"

type CapabilitiesQueryOptions = {
  fetcher?: FetchImplementation
}

function capabilitiesQueryOptions(options: CapabilitiesQueryOptions = {}) {
  return queryOptions({
    queryFn: ({ signal }) =>
      fetchValidated("/api/v1/capabilities", GetCapabilities200Response, {
        fetcher: options.fetcher,
        signal,
      }),
    queryKey: queryKeys.capabilities(),
    retryOnMount: false,
  })
}

function useCapabilities(): ServerStateResult<ObservatoryCapabilitiesOutput> {
  const query = useQuery(capabilitiesQueryOptions())
  return toServerStateResult(query, {
    isEmpty: (capabilities) =>
      capabilities.features.length === 0 && capabilities.sources.length === 0,
  })
}

export {
  capabilitiesQueryOptions,
  useCapabilities,
  type CapabilitiesQueryOptions,
}
