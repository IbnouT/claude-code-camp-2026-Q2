import * as zod from "zod/mini"

import { ApiError, type ApiErrorOutput } from "@/data/generated/validators"

type ContractSchema<Output> = zod.ZodMiniType<Output>

export class ContractFault extends Error {
  readonly status: number
  readonly body: ApiErrorOutput | null

  constructor(
    message: string,
    status: number,
    body: ApiErrorOutput | null = null
  ) {
    super(message)
    this.name = "ContractFault"
    this.status = status
    this.body = body
  }
}

export async function parseContractResponse<Output>(
  response: Response,
  success: ReadonlyMap<number, ContractSchema<Output>>
): Promise<Output> {
  const body: unknown = await response.json()
  const successSchema = success.get(response.status)

  if (successSchema !== undefined) {
    const result = successSchema.safeParse(body)
    if (!result.success) {
      throw new ContractFault(
        `Response ${response.status} violated its success contract`,
        response.status
      )
    }
    return result.data
  }

  const error = ApiError.safeParse(body)
  if (!error.success) {
    throw new ContractFault(
      `Response ${response.status} violated its error contract`,
      response.status
    )
  }
  throw new ContractFault(error.data.error, response.status, error.data)
}
