import { X } from "lucide-react";
import type { RoomInspectorProjection } from "./roomInspector";

type Props = {
  room: RoomInspectorProjection;
  onClose: () => void;
};

export function LiveRoomInspector({
  room,
  onClose,
}: Props) {
  const provenanceRows: Array<[string, number]> = [
    ["Room observations", room.evidence.room],
    ["Description observations", room.evidence.description],
    ["Frontier observations", room.evidence.exits],
    ["Sighting observations", room.evidence.sightings],
    ["Economics records", room.evidence.economics],
  ];
  const provenance = provenanceRows.filter(([, count]) => count > 0);

  return (
    <aside
      aria-label={`Room inspector, ${room.title}`}
      className="live-room-inspector"
      data-map-overlay-edge="right"
      data-room-id={room.id}
    >
      <header className="live-room-inspector-header">
        <div>
          <div className="live-room-inspector-name">
            <strong>{room.title}</strong>
          </div>
          <div className="live-room-inspector-meta">
            <span>passed ×{room.visits}</span>
            <span>
              first s{room.firstSequence} · last s{room.lastSequence}
            </span>
          </div>
        </div>
        <button
          aria-label="Close room inspector"
          className="live-room-inspector-close"
          type="button"
          onClick={onClose}
        >
          <X aria-hidden="true" size={15} />
        </button>
      </header>

      <div className="live-room-inspector-body">
        {room.description === null ? null : (
          <p className="live-room-inspector-description">
            {room.description}
          </p>
        )}

        <InspectorHeading>Exits</InspectorHeading>
        <div className="live-room-inspector-exits">
          {room.exits.length === 0 ? (
            <span className="is-unavailable">none observed</span>
          ) : room.exits.map((exit) => (
            <span
              className={exit.confirmed ? "" : "is-unconfirmed"}
              key={exit.direction}
            >
              {exit.direction}{exit.confirmed ? "" : " ?"}
            </span>
          ))}
        </div>

        <InspectorHeading>Seen here</InspectorHeading>
        <SightingList
          empty="no mob sightings retained"
          icon="☠"
          items={room.mobSightings}
          tone="mob"
        />

        <InspectorHeading>Objects known here</InspectorHeading>
        <SightingList
          empty="none retained"
          icon="◇"
          items={room.objectSightings}
          tone="object"
        />

        <div className="live-room-inspector-stats">
          <div>
            <small>Passed</small>
            <strong>{room.visits}×</strong>
          </div>
          {room.spendUsd === null ? null : (
            <div>
              <small>Spent here</small>
              <strong>${room.spendUsd.toFixed(3)}</strong>
            </div>
          )}
          <div>
            <small>Confidence</small>
            <strong>{room.confidence}</strong>
          </div>
        </div>

        {provenance.length === 0 ? null : (
          <>
            <InspectorHeading>Agent evidence</InspectorHeading>
            <dl className="live-room-inspector-provenance">
              {provenance.map(([label, count]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{count}</dd>
                </div>
              ))}
            </dl>
          </>
        )}

        {room.atlas === null ? null : (
          <section
            aria-label="Atlas reference"
            className="live-room-inspector-atlas"
          >
            <InspectorHeading>Atlas reference</InspectorHeading>
            <dl>
              <div>
                <dt>Vnum</dt>
                <dd>{room.atlas.vnum}</dd>
              </div>
              <div>
                <dt>Sector</dt>
                <dd>{room.atlas.sector}</dd>
              </div>
              <div>
                <dt>Zone</dt>
                <dd>{room.atlas.zoneLabel}</dd>
              </div>
              <div>
                <dt>Correlation</dt>
                <dd>{room.atlas.confidence}</dd>
              </div>
              <div>
                <dt>Atlas sources</dt>
                <dd>{room.atlas.sources}</dd>
              </div>
            </dl>
          </section>
        )}
      </div>
    </aside>
  );
}

function InspectorHeading({ children }: { children: string }) {
  return <h2 className="live-room-inspector-heading">{children}</h2>;
}

function SightingList({
  empty,
  icon,
  items,
  tone,
}: {
  empty: string;
  icon: string;
  items: RoomInspectorProjection["mobSightings"];
  tone: "mob" | "object";
}) {
  if (items.length === 0) {
    return <p className="live-room-inspector-empty">{empty}</p>;
  }
  return (
    <ul className="live-room-inspector-sightings">
      {items.map((item) => (
        <li key={item.name}>
          <span aria-hidden="true" className={`is-${tone}`}>{icon}</span>
          <span>{item.name}</span>
          <small>×{item.count}</small>
        </li>
      ))}
    </ul>
  );
}
