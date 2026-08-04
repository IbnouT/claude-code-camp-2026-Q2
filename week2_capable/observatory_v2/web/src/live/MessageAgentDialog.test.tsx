// @vitest-environment jsdom

import {
  act,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";
import { MessageAgentDialog } from "./MessageAgentDialog";

const identity = {
  playerId: "poucet",
  sessionId: "57a5315b-f1c1-4e7e-b7d7-ee41de85c90f",
};

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("finishes closing when snapshot polling rerenders the parent", () => {
  vi.useFakeTimers();
  const onClose = vi.fn();
  const props = {
    controlAvailable: true,
    followingLive: true,
    identity,
    messages: [],
    objectiveAvailable: true,
    selectedSequence: 42,
    sessionRunning: true,
  };
  const view = render(
    <MessageAgentDialog {...props} onClose={onClose} />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Close messages" }));
  view.rerender(
    <MessageAgentDialog {...props} onClose={() => onClose()} />,
  );
  act(() => vi.advanceTimersByTime(360));

  expect(onClose).toHaveBeenCalledOnce();
});

it("routes a session to V3 only when the frozen supervisor does not own it", async () => {
  const user = userEvent.setup();
  const calls: Array<{ body: unknown; url: string }> = [];
  vi.stubGlobal("fetch", vi.fn(
    (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({
        body: init?.body ? JSON.parse(String(init.body)) : null,
        url,
      });
      if (url.endsWith("/message")) {
        return Promise.resolve({
          ok: false,
          status: 409,
          text: async () => JSON.stringify({
            error: "supervisor_mismatch",
          }),
        } as Response);
      }
      if (url.endsWith("/commands")) {
        return Promise.resolve({
          ok: true,
          status: 202,
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ source_cursor: "obp1_current" }),
      } as Response);
    },
  ));
  render(
    <MessageAgentDialog
      controlAvailable
      followingLive
      identity={identity}
      messages={[]}
      objectiveAvailable
      selectedSequence={42}
      sessionRunning
      onClose={() => undefined}
    />,
  );

  await user.type(
    screen.getByLabelText("Message for the agent"),
    "Try the western exit",
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));

  expect(await screen.findByText(/waiting for the next iteration/))
    .toBeInTheDocument();
  expect(calls.map((call) => call.url)).toEqual([
    `http://localhost:8792/api/sessions/${identity.sessionId}/message`,
    `/api/v1/sessions/${identity.sessionId}`,
    `/api/v1/sessions/${identity.sessionId}/commands`,
  ]);
  expect(calls[2]?.body).toMatchObject({
    actor: "frozen-observatory",
    player_id: "poucet",
    action: "guide",
    instruction: "Try the western exit",
    expected_cursor: "obp1_current",
  });
});
