import { describe, expect, it } from "vitest"

import sessionCatalogFixture from "../../../../backend/openapi/fixtures/session-catalog.json?raw"
import {
  SessionCatalogResponse,
  type SessionCatalogResponseOutput,
} from "@/data/generated/validators"

import { parseContractResponse } from "./response-contract"

describe("parseContractResponse", () => {
  it("accepts the sanitized Python fixture with the generated validator", async () => {
    const response = new Response(sessionCatalogFixture, {
      status: 200,
      headers: { "content-type": "application/json" },
    })

    const parsed = await parseContractResponse<SessionCatalogResponseOutput>(
      response,
      new Map([[200, SessionCatalogResponse]])
    )

    expect(parsed.sessions[0]?.goal_count).toBe(2)
    expect(parsed.sessions[0]?.nudge_count).toBe(1)
  })

  it("rejects a success body that violates the selected status contract", async () => {
    const response = Response.json({ sessions: [] }, { status: 200 })

    await expect(
      parseContractResponse<SessionCatalogResponseOutput>(
        response,
        new Map([[200, SessionCatalogResponse]])
      )
    ).rejects.toMatchObject({
      name: "ContractFault",
      status: 200,
    })
  })

  it("validates a typed error before exposing it", async () => {
    const response = Response.json(
      {
        contract_version: "v1",
        error: "source_unavailable",
        detail: "The selected source is offline",
      },
      { status: 503 }
    )

    await expect(
      parseContractResponse<SessionCatalogResponseOutput>(
        response,
        new Map([[200, SessionCatalogResponse]])
      )
    ).rejects.toMatchObject({
      name: "ContractFault",
      status: 503,
      body: { error: "source_unavailable" },
    })
  })

  it("rejects unknown fields to match Pydantic extra-forbid models", async () => {
    const body: unknown = JSON.parse(sessionCatalogFixture)
    const baseline = SessionCatalogResponse.parse(body)
    const response = Response.json({ ...baseline, uncontracted: true })

    await expect(
      parseContractResponse<SessionCatalogResponseOutput>(
        response,
        new Map([[200, SessionCatalogResponse]])
      )
    ).rejects.toMatchObject({
      name: "ContractFault",
      status: 200,
    })
  })
})
