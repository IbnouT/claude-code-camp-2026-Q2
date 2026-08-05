// @vitest-environment jsdom

import {
  render,
  screen,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  beforeEach,
  expect,
  it,
  vi,
} from "vitest";
import { Launcher } from "./Launcher";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("fetch", vi.fn());
});

it("owns the screen while a new session is connecting", async () => {
  const user = userEvent.setup();
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    if (String(input).endsWith("/api/sessions")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          version: 1,
          players: [{ id: "poucet", label: "poucet" }],
          sessions: [],
        }),
      } as Response);
    }
    return new Promise<Response>(() => undefined);
  });

  render(<Launcher theme="dark" onThemeChange={() => undefined} />);
  await user.click(
    await screen.findByRole("button", {
      name: /Start session as poucet/,
    }),
  );

  const transition = screen.getByRole("status");
  expect(transition).toHaveTextContent("Starting poucet");
  expect(transition).toHaveTextContent(
    "Connecting the agent and opening Live automatically",
  );
});
