import { QueryClient } from "@tanstack/react-query"

import {
  HttpResponseError,
  ResponseValidationError,
  TransportError,
} from "@/data/contracts/response-contract"

const maximumRetryCount = 2
const maximumRetryDelayMilliseconds = 4_000

function retryDelay(attemptIndex: number): number {
  return Math.min(250 * 2 ** attemptIndex, maximumRetryDelayMilliseconds)
}

function shouldRetry(failureCount: number, error: Error): boolean {
  if (failureCount >= maximumRetryCount) {
    return false
  }
  if (error.name === "AbortError" || error instanceof ResponseValidationError) {
    return false
  }
  if (error instanceof HttpResponseError) {
    return error.status === 408 || error.status === 429 || error.status >= 500
  }
  return error instanceof TransportError
}

function createObservatoryQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: 5 * 60_000,
        refetchInterval: false,
        refetchOnReconnect: true,
        refetchOnWindowFocus: false,
        retry: shouldRetry,
        retryDelay,
        staleTime: 15_000,
      },
    },
  })
}

export {
  createObservatoryQueryClient,
  maximumRetryCount,
  retryDelay,
  shouldRetry,
}
