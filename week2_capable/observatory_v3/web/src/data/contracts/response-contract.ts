import * as zod from "zod/mini"

import { ApiError, type ApiErrorOutput } from "@/data/generated/validators"

type ContractSchema<Output> = zod.ZodMiniType<Output>

abstract class DataAccessError extends Error {
  abstract readonly kind: "http" | "transport" | "validation"
}

class HttpResponseError extends DataAccessError {
  readonly kind = "http"
  readonly status: number
  readonly body: ApiErrorOutput

  constructor(status: number, body: ApiErrorOutput) {
    super(body.error)
    this.name = "HttpResponseError"
    this.status = status
    this.body = body
  }
}

class ResponseValidationError extends DataAccessError {
  readonly kind = "validation"
  readonly status: number | null

  constructor(message: string, status: number | null = null) {
    super(message)
    this.name = "ResponseValidationError"
    this.status = status
  }
}

class TransportError extends DataAccessError {
  readonly kind = "transport"
  readonly status = null

  constructor(message: string, options?: ErrorOptions) {
    super(message, options)
    this.name = "TransportError"
  }
}

export async function parseContractResponse<Output>(
  response: Response,
  success: ReadonlyMap<number, ContractSchema<Output>>
): Promise<Output> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ResponseValidationError(
      `Response ${response.status} was not valid JSON`,
      response.status
    )
  }
  const successSchema = success.get(response.status)

  if (successSchema !== undefined) {
    const result = successSchema.safeParse(body)
    if (!result.success) {
      throw new ResponseValidationError(
        `Response ${response.status} violated its success contract`,
        response.status
      )
    }
    return result.data
  }

  const error = ApiError.safeParse(body)
  if (!error.success) {
    throw new ResponseValidationError(
      `Response ${response.status} violated its error contract`,
      response.status
    )
  }
  throw new HttpResponseError(response.status, error.data)
}

export {
  DataAccessError,
  HttpResponseError,
  ResponseValidationError,
  TransportError,
  type ContractSchema,
}
