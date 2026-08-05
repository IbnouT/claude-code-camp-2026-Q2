// @vitest-environment jsdom

import {
  act,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
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
