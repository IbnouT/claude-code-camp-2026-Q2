import { describe, expect, it } from "vitest"

import { ResponseValidationError } from "@/data/contracts/response-contract"
import { toServerStateResult, type ResultSnapshot } from "@/data/query-result"

type Resource = {
  completeness: "complete" | "degraded" | "partial"
  items: string[]
}

function snapshot(
  overrides: Partial<ResultSnapshot<Resource>> = {}
): ResultSnapshot<Resource> {
  return {
    data: undefined,
    error: null,
    fetchStatus: "idle",
    isError: false,
    isPending: false,
    isStale: false,
    ...overrides,
  }
}

const options = {
  getCompleteness: (resource: Resource) => resource.completeness,
  isEmpty: (resource: Resource) => resource.items.length === 0,
}

describe("typed server-state results", () => {
  it("maps loading, empty, ready, and partial resources", () => {
    expect(toServerStateResult(snapshot(), options)).toEqual({
      status: "loading",
    })
    expect(
      toServerStateResult(
        snapshot({
          data: { completeness: "complete", items: [] },
        }),
        options
      )
    ).toMatchObject({ status: "empty" })
    expect(
      toServerStateResult(
        snapshot({
          data: { completeness: "complete", items: ["one"] },
        }),
        options
      )
    ).toMatchObject({ status: "ready" })
    expect(
      toServerStateResult(
        snapshot({
          data: { completeness: "degraded", items: ["one"] },
        }),
        options
      )
    ).toMatchObject({ completeness: "degraded", status: "partial" })
  })

  it("maps paused, stale, and typed error lifecycles", () => {
    expect(
      toServerStateResult(snapshot({ fetchStatus: "paused" }), options)
    ).toMatchObject({ status: "reconnecting" })
    expect(
      toServerStateResult(
        snapshot({
          data: { completeness: "complete", items: ["one"] },
          isStale: true,
        }),
        options
      )
    ).toMatchObject({ status: "stale" })
    expect(
      toServerStateResult(
        snapshot({
          error: new ResponseValidationError("invalid", 200),
          isError: true,
        }),
        options
      )
    ).toMatchObject({
      error: { kind: "validation" },
      status: "error",
    })
  })
})
