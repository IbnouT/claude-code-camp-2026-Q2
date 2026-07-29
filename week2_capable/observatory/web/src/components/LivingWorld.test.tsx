import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { WorldProjection } from "../data/investigation";
import { LivingWorld } from "./LivingWorld";

const world: WorldProjection = {
  nodes: [
    {
      id: "place:101",
      place: 101,
      title: "White Square",
      exits: ["south", "east"],
      visits: 3,
      first_seq: 1,
      last_seq: 20,
      state: "candidate",
      confidence: "tracked",
      method: "exits-and-neighbourhood",
    },
    {
      id: "place:202",
      place: 202,
      title: "Nexus",
      exits: ["west", "north"],
      visits: 2,
      first_seq: 21,
      last_seq: 30,
      state: "observed",
      confidence: "tracked",
      method: "exits-and-neighbourhood",
    },
    {
      id: "place:303",
      place: 303,
      title: "White Square",
      exits: ["south", "west"],
      visits: 4,
      first_seq: 31,
      last_seq: 50,
      state: "candidate",
      confidence: "tracked",
      method: "exits-and-neighbourhood",
    },
  ],
  edges: [
    {
      id: "101:202:east",
      source: "place:101",
      target: "place:202",
      direction: "east",
      traversals: 2,
      evidence: [21, 40],
    },
    {
      id: "202:303:north",
      source: "place:202",
      target: "place:303",
      direction: "north",
      traversals: 1,
      evidence: [31],
    },
  ],
  current_title: "White Square",
  current_confidence: "ambiguous",
  candidates: ["place:101", "place:303"],
  parse_miss_rate: 0.125,
  unknown_positions: 1,
};

describe("living world", () => {
  it("keeps duplicate room titles as separate candidate identities", () => {
    render(<LivingWorld world={world} />);
    expect(
      screen.getByRole("button", {
        name: "White Square, place 101, candidate",
      }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", {
        name: "White Square, place 303, candidate",
      }),
    ).toBeVisible();
    expect(screen.getByText("12.5% parse miss")).toBeVisible();
  });

  it("explains candidates through exits and neighbourhood evidence", async () => {
    const user = userEvent.setup();
    render(<LivingWorld world={world} />);
    await user.click(
      screen.getByRole("button", {
        name: "White Square, place 303, candidate",
      }),
    );
    expect(screen.getByText("Why this remains a candidate")).toBeVisible();
    expect(screen.getByText("south, west")).toBeVisible();
    expect(screen.getByText(/1 recorded neighbourhood link/)).toBeVisible();
  });
});
