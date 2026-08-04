import type { ContractSchema } from "@/data/contracts/response-contract"
import {
  TransportError,
  parseContractResponse,
} from "@/data/contracts/response-contract"

type FetchImplementation = typeof globalThis.fetch

type RequestOptions = {
  fetcher?: FetchImplementation
  signal?: AbortSignal
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError"
}

async function fetchResponse(
  path: string,
  { fetcher = globalThis.fetch, signal }: RequestOptions = {}
): Promise<Response> {
  try {
    return await fetcher(path, {
      headers: { accept: "application/json" },
      method: "GET",
      signal,
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw error
    }
    throw new TransportError(`GET ${path} failed before a response arrived`, {
      cause: error,
    })
  }
}

async function fetchValidated<Output>(
  path: string,
  schema: ContractSchema<Output>,
  options: RequestOptions = {}
): Promise<Output> {
  const response = await fetchResponse(path, options)
  return parseContractResponse(response, new Map([[200, schema]]))
}

async function postValidated<Output>(
  path: string,
  body: unknown,
  successStatus: number,
  schema: ContractSchema<Output>,
  { fetcher = globalThis.fetch, signal }: RequestOptions = {}
): Promise<Output> {
  let response: Response
  try {
    response = await fetcher(path, {
      body: JSON.stringify(body),
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      method: "POST",
      signal,
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw error
    }
    throw new TransportError(`POST ${path} failed before a response arrived`, {
      cause: error,
    })
  }
  return parseContractResponse(response, new Map([[successStatus, schema]]))
}

function withQuery(
  path: string,
  parameters: Readonly<Record<string, number | string | undefined>>
): string {
  const search = new URLSearchParams()
  for (const [name, value] of Object.entries(parameters)) {
    if (value !== undefined) {
      search.set(name, String(value))
    }
  }
  const serialized = search.toString()
  return serialized === "" ? path : `${path}?${serialized}`
}

export {
  fetchResponse,
  fetchValidated,
  isAbortError,
  postValidated,
  withQuery,
  type FetchImplementation,
  type RequestOptions,
}
