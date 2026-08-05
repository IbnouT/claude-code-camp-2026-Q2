import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("@/data/transport", () => ({
  fetchValidated: vi.fn<(...args: never[]) => unknown>(),
  postValidated: vi.fn<(...args: never[]) => unknown>(),
}))

import { HttpResponseError } from "@/data/contracts/response-contract"
import { sendOperatorMessage } from "@/data/message-command"
import { fetchValidated, postValidated } from "@/data/transport"

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
  it("submits the composite cursor read from the session summary", async () => {
    fetchMock.mockResolvedValue({ source_cursor: "obc1_x" } as never)
    postMock.mockResolvedValue({ command_id: "c1", state: "queued" } as never)

    await sendOperatorMessage(input)

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/sessions/session-a",
      expect.anything()
    )
    expect(postMock).toHaveBeenCalledWith(
      "/api/v1/sessions/session-a/commands",
      expect.objectContaining({ expected_cursor: "obc1_x" }),
      202,
      expect.anything()
    )
  })

  it("retries a cursor conflict with a fresh cursor, bounded", async () => {
    fetchMock
      .mockResolvedValueOnce({ source_cursor: "obc1_stale" } as never)
      .mockResolvedValueOnce({ source_cursor: "obc1_stale" } as never)
      .mockResolvedValueOnce({ source_cursor: "obc1_fresh" } as never)
    postMock
      .mockRejectedValueOnce(conflict())
      .mockRejectedValueOnce(conflict())
      .mockResolvedValueOnce({ command_id: "c1", state: "queued" } as never)

    const result = await sendOperatorMessage(input)

    expect(result).toMatchObject({ command_id: "c1" })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(postMock).toHaveBeenCalledTimes(3)
    expect(postMock).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.objectContaining({ expected_cursor: "obc1_fresh" }),
      202,
      expect.anything()
    )
  })

  it("surfaces the conflict after the attempt budget", async () => {
    fetchMock.mockResolvedValue({ source_cursor: "obc1_x" } as never)
    postMock.mockRejectedValue(conflict())

    await expect(sendOperatorMessage(input)).rejects.toThrow(/command_conflict/)
    expect(postMock).toHaveBeenCalledTimes(3)
  })

  it("never retries a non conflict failure", async () => {
    fetchMock.mockResolvedValue({ source_cursor: "obc1_x" } as never)
    postMock.mockRejectedValue(new Error("network down"))

    await expect(sendOperatorMessage(input)).rejects.toThrow("network down")
    expect(postMock).toHaveBeenCalledTimes(1)
  })
})
