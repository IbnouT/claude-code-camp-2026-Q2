import { describe, expect, it } from "vitest"

import {
  HttpResponseError,
  ResponseValidationError,
  TransportError,
} from "@/data/contracts/response-contract"
import { ApiError } from "@/data/generated/validators"
import { maximumRetryCount, retryDelay, shouldRetry } from "@/data/query-client"

const apiError = ApiError.parse({
  contract_version: "v1",
  detail: null,
  error: "unavailable",
})

describe("query retry policy", () => {
  it("retries transport and transient HTTP failures only within the bound", () => {
    expect(shouldRetry(0, new TransportError("offline"))).toBe(true)
    expect(shouldRetry(1, new HttpResponseError(503, apiError))).toBe(true)
    expect(shouldRetry(maximumRetryCount, new TransportError("offline"))).toBe(
      false
    )
  })

  it("does not retry validation, cancellation, or stable HTTP failures", () => {
    expect(shouldRetry(0, new ResponseValidationError("invalid", 200))).toBe(
      false
    )
    expect(shouldRetry(0, new HttpResponseError(404, apiError))).toBe(false)
    expect(shouldRetry(0, new DOMException("cancelled", "AbortError"))).toBe(
      false
    )
  })

  it("uses capped exponential backoff", () => {
    expect([0, 1, 2, 8].map(retryDelay)).toEqual([250, 500, 1_000, 4_000])
  })
})
