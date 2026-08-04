import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("@/data/transport", () => ({
  fetchValidated: vi.fn(),
  postValidated: vi.fn(),
}))

import { HttpResponseError } from "@/data/contracts/response-contract"
import { fetchValidated, postValidated } from "@/data/transport"
import { sendOperatorMessage } from "@/data/message-command"

const fetchMock = vi.mocked(fetchValidated)
const postMock = vi.mocked(postValidated)

afterEach(() => {
  vi.clearAllMocks()
})

const input = {
  session_id: "session-a",
  player_id: "player-a",
  action: "guide" as const,
  instruction: "Head north.",
}

function conflict() {
  return new HttpResponseError(409, {
    contract_version: "v1",
    error: "command_conflict",
    detail: "the selected session advanced",
  })
}

describe("operator message delivery", () => {
  it("retries a cursor conflict with a fresh cursor, bounded", async () => {
    fetchMock.mockResolvedValue({ source_cursor: "obv1_x" } as never)
    postMock
      .mockRejectedValueOnce(conflict())
      .mockRejectedValueOnce(conflict())
      .mockResolvedValueOnce({ command_id: "c1", state: "queued" } as never)

    const result = await sendOperatorMessage(input)

    expect(result).toMatchObject({ command_id: "c1" })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(postMock).toHaveBeenCalledTimes(3)
  })

  it("surfaces the conflict after the attempt budget", async () => {
    fetchMock.mockResolvedValue({ source_cursor: "obv1_x" } as never)
    postMock.mockRejectedValue(conflict())

    await expect(sendOperatorMessage(input)).rejects.toThrow(
      /command_conflict/
    )
    expect(postMock).toHaveBeenCalledTimes(3)
  })

  it("never retries a non conflict failure", async () => {
    fetchMock.mockResolvedValue({ source_cursor: "obv1_x" } as never)
    postMock.mockRejectedValue(new Error("network down"))

    await expect(sendOperatorMessage(input)).rejects.toThrow("network down")
    expect(postMock).toHaveBeenCalledTimes(1)
  })
})
