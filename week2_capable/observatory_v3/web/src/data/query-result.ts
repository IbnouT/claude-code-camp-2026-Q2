import type { QueryObserverResult } from "@tanstack/react-query"

import {
  DataAccessError,
  TransportError,
} from "@/data/contracts/response-contract"

type Completeness = "complete" | "degraded" | "partial"

type ServerStateResult<Data> =
  | { status: "loading" }
  | { data: Data; status: "empty" }
  | {
      data: Data
      completeness: Exclude<Completeness, "complete">
      status: "partial"
    }
  | { data: Data; status: "ready" }
  | { data: Data; error: DataAccessError | null; status: "stale" }
  | { data: Data | undefined; status: "reconnecting" }
  | { error: DataAccessError; status: "error" }

type ResultOptions<Data> = {
  getCompleteness?: (data: Data) => Completeness
  isEmpty?: (data: Data) => boolean
}

type ResultSnapshot<Data> = Pick<
  QueryObserverResult<Data, Error>,
  "data" | "error" | "fetchStatus" | "isError" | "isPending" | "isStale"
>

function normalizeError(error: Error): DataAccessError {
  return error instanceof DataAccessError
    ? error
    : new TransportError(error.message, { cause: error })
}

function toServerStateResult<Data>(
  snapshot: ResultSnapshot<Data>,
  options: ResultOptions<Data> = {}
): ServerStateResult<Data> {
  const { data, error, fetchStatus, isError, isStale } = snapshot

  if (fetchStatus === "paused") {
    return { data, status: "reconnecting" }
  }
  if (data === undefined) {
    return isError && error !== null
      ? { error: normalizeError(error), status: "error" }
      : { status: "loading" }
  }
  if (isError || isStale) {
    return {
      data,
      error: error === null ? null : normalizeError(error),
      status: "stale",
    }
  }

  const completeness = options.getCompleteness?.(data)
  if (completeness === "partial" || completeness === "degraded") {
    return { completeness, data, status: "partial" }
  }
  if (options.isEmpty?.(data) === true) {
    return { data, status: "empty" }
  }
  return { data, status: "ready" }
}

export {
  toServerStateResult,
  type Completeness,
  type ResultOptions,
  type ResultSnapshot,
  type ServerStateResult,
}
