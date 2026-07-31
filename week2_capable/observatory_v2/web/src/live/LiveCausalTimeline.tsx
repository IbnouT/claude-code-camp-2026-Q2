import type {
  LiveEconomicsPoint,
  Snapshot,
} from "../contracts";
import type { LiveSnapshotState } from "./useLiveSnapshot";

type TimelineLandmark = {
  id: string;
  sequence: number;
  kind: "room" | "level_up";
  label: string;
};

type Props = {
  latestSnapshot: Snapshot | null;
  snapshot: Snapshot | null;
  state: LiveSnapshotState;
  onSelectThrough: (sequence: number | null) => void;
};

function recentLandmarks(snapshot: Snapshot): TimelineLandmark[] {
  const gatewayItems = snapshot.timeline.filter(
    (item) => item.source === "gateway",
  );
  const firstRetainedSequence = gatewayItems.at(0)?.sequence
    ?? snapshot.latest_sequence;
  const rooms: TimelineLandmark[] = [];
  let previousPosition: string | null = null;
  for (const item of gatewayItems) {
    if (item.kind !== "position" || item.label === previousPosition) continue;
    previousPosition = item.label;
    rooms.push({
      id: `room-${item.id}`,
      sequence: item.sequence,
      kind: "room",
      label: item.label,
    });
  }
  const milestones = snapshot.milestones
    .filter((milestone) => milestone.sequence >= firstRetainedSequence)
    .map((milestone): TimelineLandmark => ({
      id: `level-${milestone.sequence}`,
      sequence: milestone.sequence,
      kind: "level_up",
      label: `Level ${milestone.current}`,
    }));
  return [...rooms, ...milestones].sort(
    (left, right) => left.sequence - right.sequence,
  );
}

function costCurve(points: LiveEconomicsPoint[]): string {
  const highest = points.at(-1)?.cumulative_cost_usd ?? 0;
  if (points.length < 2 || highest <= 0) return "";
  return points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 900;
      const y = 18 - (point.cumulative_cost_usd / highest) * 14;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function formatSelectedTime(seconds: number | null): string {
  if (seconds === null) return "time not retained";
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(seconds * 1_000));
}

function formatUsd(value: number): string {
  if (value === 0) return "$0.0000";
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(3)}`;
}

export function LiveCausalTimeline({
  latestSnapshot,
  snapshot,
  state,
  onSelectThrough,
}: Props) {
  if (snapshot === null || latestSnapshot === null) {
    return (
      <div className="live-timeline-empty" role="status">
        {state === "reconnecting"
          ? "Timeline evidence is reconnecting."
          : "Waiting for retained timeline evidence."}
      </div>
    );
  }

  const landmarks = recentLandmarks(latestSnapshot);
  const firstSequence = latestSnapshot.timeline.find(
    (item) => item.source === "gateway",
  )?.sequence
    ?? landmarks.at(0)?.sequence
    ?? latestSnapshot.latest_sequence;
  const lastSequence = latestSnapshot.latest_sequence;
  const position = (sequence: number): number => {
    if (lastSequence <= firstSequence) return 50;
    const ratio = (sequence - firstSequence) / (lastSequence - firstSequence);
    return 2 + Math.min(1, Math.max(0, ratio)) * 94;
  };
  const selectedSequence = snapshot.through_sequence;
  const previous = [...landmarks].reverse().find(
    (landmark) => landmark.sequence < selectedSequence,
  );
  const next = landmarks.find(
    (landmark) => landmark.sequence > selectedSequence,
  );
  const labelledLandmarks = (["room", "level_up"] as const)
    .map((kind) => [...landmarks].reverse().find(
      (landmark) => landmark.kind === kind,
    ))
    .filter((landmark): landmark is TimelineLandmark => landmark !== undefined);
  const curve = costCurve(latestSnapshot.economics);

  return (
    <>
      <div className="live-timeline-heading">
        <small>Causal timeline</small>
        <span className="live-timeline-reading">
          <span>seq {selectedSequence} / {latestSnapshot.latest_sequence}</span>
          <span>
            {" · "}
            {snapshot.following_live ? "following live" : "inspecting history"}
          </span>
          <span className="live-timeline-reading-secondary">
            {" · "}
            {formatSelectedTime(snapshot.selected_at)}
            {" · "}
            {formatUsd(snapshot.cost_usd)} at prefix
          </span>
        </span>
        <div className="live-timeline-transport" aria-label="Timeline transport">
          <button
            aria-label="Previous landmark"
            disabled={previous === undefined}
            type="button"
            onClick={() => onSelectThrough(previous?.sequence ?? null)}
          >
            ‹
          </button>
          <button
            aria-label="Next landmark"
            disabled={next === undefined}
            type="button"
            onClick={() => onSelectThrough(next?.sequence ?? null)}
          >
            ›
          </button>
          {!snapshot.following_live ? (
            <button
              className="live-timeline-return"
              type="button"
              onClick={() => onSelectThrough(null)}
            >
              Return to live
            </button>
          ) : null}
        </div>
      </div>
      <div className="live-timeline-track">
        <div className="live-timeline-axis" />
        {curve === "" ? null : (
          <svg
            aria-label="Cumulative session cost"
            className="live-timeline-cost"
            preserveAspectRatio="none"
            role="img"
            viewBox="0 0 900 22"
          >
            <polyline points={curve} />
          </svg>
        )}
        {landmarks.map((landmark) => (
          <button
            aria-label={`${landmark.kind === "room" ? "Room" : "Level up"}: ${landmark.label}, sequence ${landmark.sequence}`}
            className={`live-timeline-landmark is-${landmark.kind}`}
            key={landmark.id}
            style={{ left: `${position(landmark.sequence)}%` }}
            title={landmark.label}
            type="button"
            onClick={() => onSelectThrough(
              landmark.sequence === latestSnapshot.latest_sequence
                ? null
                : landmark.sequence,
            )}
          />
        ))}
        {labelledLandmarks.map((landmark) => (
          <span
            className="live-timeline-label"
            key={`label-${landmark.id}`}
            style={{ left: `${position(landmark.sequence)}%` }}
          >
            {landmark.kind === "room" ? "room" : "level up"}
          </span>
        ))}
        <div
          aria-hidden="true"
          className="live-timeline-cursor"
          style={{ left: `${position(selectedSequence)}%` }}
        />
        {landmarks.length === 0 ? (
          <span className="live-timeline-no-landmarks">
            No room or level landmarks in the recent retained window
          </span>
        ) : null}
      </div>
    </>
  );
}
