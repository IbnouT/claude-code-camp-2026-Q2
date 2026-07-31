import {
  render,
  screen,
} from "@testing-library/react";
import {
  describe,
  expect,
  it,
  vi,
} from "vitest";
import type { WorldNode } from "../contracts";
import {
  LiveMapRoom,
  roomStateClass,
  sectorClass,
} from "./LiveMapRoom";

const onSelect = vi.fn();
const rooms = [
  room("a", "city"),
  room("b", "inside"),
  room("c", "forest"),
];

describe("live map room rendering", () => {
  it("derives sector classes from atlas sectors", () => {
    expect(sectorClass("city")).toBe("is-sector-city");
    expect(sectorClass("urban")).toBe("is-sector-urban");
    expect(sectorClass("inside")).toBe("is-sector-inside");
    expect(sectorClass("interior")).toBe("is-sector-interior");
    expect(sectorClass("field")).toBe("is-sector-field");
    expect(sectorClass("open-land")).toBe("is-sector-open-land");
    expect(sectorClass("forest")).toBe("is-sector-forest");
    expect(sectorClass("woodland")).toBe("is-sector-woodland");
    expect(sectorClass("hills")).toBe("is-sector-hills");
    expect(sectorClass("mountain")).toBe("is-sector-mountain");
    expect(sectorClass("highland")).toBe("is-sector-highland");
    expect(sectorClass("water (swimmable)")).toBe("is-sector-water");
    expect(sectorClass("underwater")).toBe("is-sector-water");
    expect(sectorClass("water")).toBe("is-sector-semantic-water");
    expect(sectorClass("route")).toBe("is-sector-route");
    expect(sectorClass("underground")).toBe("is-sector-underground");
    expect(sectorClass("commerce")).toBe("is-sector-commerce");
    expect(sectorClass("civic")).toBe("is-sector-civic");
    expect(sectorClass("sacred")).toBe("is-sector-sacred");
    expect(sectorClass("special")).toBe("is-sector-special");
    expect(sectorClass(undefined)).toBe("is-sector-neutral");
  });

  it("applies the state priority combat, current, selected, beacon", () => {
    expect(roomStateClass({
      combat: true,
      current: true,
      selected: true,
      beacon: true,
    })).toBe("is-combat");
    expect(roomStateClass({
      combat: false,
      current: true,
      selected: true,
      beacon: true,
    })).toBe("is-current");
    expect(roomStateClass({
      combat: false,
      current: false,
      selected: true,
      beacon: true,
    })).toBe("is-selected");
    expect(roomStateClass({
      combat: false,
      current: false,
      selected: false,
      beacon: true,
    })).toBe("is-beacon");
  });

  it("renders the selected-room ring outside the enlarged square", () => {
    render(
      <svg>
        <LiveMapRoom
          node={rooms[0]}
          point={{ x: 0, y: 0 }}
          current={false}
          selected
          combat={false}
          beacon={false}
          onSelect={onSelect}
        />
      </svg>,
    );

    const selectedRoom = screen.getByRole("button", {
      name: /Room a/,
    });
    const ring = selectedRoom.querySelector(".live-selected-room-ring");
    expect(ring).not.toBeNull();
    expect(Number(ring?.getAttribute("r"))).toBeGreaterThan(
      Math.hypot(64, 64) / 2,
    );
    expect(selectedRoom).toHaveClass("is-selected");
  });

  it("keeps the selection affordance when the selected room is current", () => {
    render(
      <svg>
        <LiveMapRoom
          node={rooms[0]}
          point={{ x: 0, y: 0 }}
          current
          selected
          combat={false}
          beacon={false}
          onSelect={onSelect}
        />
      </svg>,
    );

    const selectedRoom = screen.getByRole("button", {
      name: /Agent in Room a/,
    });
    expect(selectedRoom).toHaveClass("is-current", "is-selected");
    expect(
      selectedRoom.querySelector(".live-selected-room-ring"),
    ).not.toBeNull();
  });

  it("re-renders exactly the old and new current rooms", () => {
    const view = renderRooms({
      currentId: "a",
      selectedId: null,
      combat: false,
    });
    view.rerender(roomSet({
      currentId: "b",
      selectedId: null,
      combat: false,
    }));

    expect(renderCounts()).toEqual({ a: 2, b: 2, c: 1 });
  });

  it("re-renders exactly the old and new selected rooms", () => {
    const view = renderRooms({
      currentId: null,
      selectedId: "a",
      combat: false,
    });
    view.rerender(roomSet({
      currentId: null,
      selectedId: "b",
      combat: false,
    }));

    expect(renderCounts()).toEqual({ a: 2, b: 2, c: 1 });
  });

  it("re-renders exactly the current room when combat changes", () => {
    const view = renderRooms({
      currentId: "a",
      selectedId: null,
      combat: false,
    });
    view.rerender(roomSet({
      currentId: "a",
      selectedId: null,
      combat: true,
    }));

    expect(renderCounts()).toEqual({ a: 2, b: 1, c: 1 });
  });
});

type RoomSetState = {
  currentId: string | null;
  selectedId: string | null;
  combat: boolean;
};

function renderRooms(state: RoomSetState) {
  return render(roomSet(state));
}

function roomSet(state: RoomSetState) {
  return (
    <svg>
      {rooms.map((node, index) => (
        <LiveMapRoom
          key={node.id}
          node={node}
          point={{ x: index * 100, y: 0 }}
          current={node.id === state.currentId}
          selected={node.id === state.selectedId}
          combat={state.combat && node.id === state.currentId}
          beacon={false}
          onSelect={onSelect}
        />
      ))}
    </svg>
  );
}

function renderCounts(): Record<string, number> {
  return Object.fromEntries(
    rooms.map(({ id }) => {
      const element = screen.getByRole("button", {
        name: new RegExp(`Room ${id}`),
      });
      return [id, Number(element.getAttribute("data-render-count"))];
    }),
  );
}

function room(id: string, sector: string): WorldNode {
  return {
    id,
    place: id.charCodeAt(0),
    title: `Room ${id}`,
    atlas: {
      vnum: id.charCodeAt(0),
      zone_id: 30,
      zone_label: "Midgaard",
      sector,
      atlas_digest: "fixture",
      confidence: "high",
      evidence: ["fixture"],
    },
    exits: [],
    visits: 1,
    evidence: [1],
    first_seq: 1,
    last_seq: 1,
    state: "observed",
    confidence: "tracked",
    method: "fixture",
  };
}
