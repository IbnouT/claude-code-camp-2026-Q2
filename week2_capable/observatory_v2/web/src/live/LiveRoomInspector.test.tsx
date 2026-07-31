// @vitest-environment jsdom

import {
  render,
  screen,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { LiveRoomInspector } from "./LiveRoomInspector";
import type { RoomInspectorProjection } from "./roomInspector";

describe("Live room inspector", () => {
  it("renders retained detail and closes from its control", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<LiveRoomInspector room={room()} onClose={onClose} />);

    expect(screen.getByRole("complementary", {
      name: "Room inspector, A Nexus",
    })).toHaveTextContent(
      "A Nexusurbanpassed ×5first s10 · last s44vnum 3001",
    );
    expect(screen.getByText("A broad crossing.")).toBeInTheDocument();
    expect(screen.getByText("south ?")).toHaveClass("is-unconfirmed");
    expect(screen.getByText("a large kobold")).toBeInTheDocument();
    expect(screen.getByText("$0.014")).toBeInTheDocument();
    expect(screen.queryByText("Open full evidence")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", {
      name: "Close room inspector",
    }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("keeps unavailable values absent and names retained empty lists", () => {
    render(
      <LiveRoomInspector
        room={{
          ...room(),
          sector: null,
          vnum: null,
          description: null,
          spendUsd: null,
          mobSightings: [],
          objectSightings: [],
          evidence: {
            room: 1,
            atlas: 0,
            description: 0,
            exits: 0,
            sightings: 0,
            economics: 0,
          },
        }}
        onClose={vi.fn()}
      />,
    );

    expect(screen.queryByText("urban")).not.toBeInTheDocument();
    expect(screen.queryByText(/vnum/)).not.toBeInTheDocument();
    expect(screen.queryByText("A broad crossing.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Spent here/)).not.toBeInTheDocument();
    expect(screen.getByText("no mob sightings retained")).toBeInTheDocument();
    expect(screen.getByText("none retained")).toBeInTheDocument();
  });
});

function room(): RoomInspectorProjection {
  return {
    id: "vnum:3001",
    title: "A Nexus",
    sector: "urban",
    vnum: 3001,
    description: "A broad crossing.",
    exits: [
      { direction: "north", confirmed: true, evidence: [] },
      { direction: "south", confirmed: false, evidence: [18] },
    ],
    mobSightings: [{
      name: "a large kobold",
      count: 2,
      first_seq: 20,
      last_seq: 40,
      evidence: [20],
    }],
    objectSightings: [{
      name: "a brass key",
      count: 1,
      first_seq: 23,
      last_seq: 23,
      evidence: [23],
    }],
    visits: 5,
    firstSequence: 10,
    lastSequence: 44,
    spendUsd: 0.014,
    confidence: "tracked",
    evidence: {
      room: 2,
      atlas: 1,
      description: 1,
      exits: 1,
      sightings: 2,
      economics: 1,
    },
  };
}
