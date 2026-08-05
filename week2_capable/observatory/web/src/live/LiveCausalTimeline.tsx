import type {
  LiveEconomicsPoint,
  Snapshot,
} from "../contracts";
import type { LiveSnapshotState } from "./useLiveSnapshot";

type TimelineLandmark = {
  id: string;
  sequence: number;
  kind: "room" | "level_up" | "friction" | "operator_message";
  label: string;
  shortLabel: string;
};

const landmarkKindLabel: Record<TimelineLandmark["kind"], string> = {
  room: "Room",
  level_up: "Level up",
  friction: "Friction",
  operator_message: "Operator message",
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
      shortLabel: "room",
    });
  }
  const milestones = snapshot.milestones
    .filter((milestone) => milestone.sequence >= firstRetainedSequence)
    .map((milestone): TimelineLandmark => ({
      id: `level-${milestone.sequence}`,
      sequence: milestone.sequence,
      kind: "level_up",
      label: `Level ${milestone.current}`,
      shortLabel: `level ${milestone.current}`,
    }));
  const operatorMessages = snapshot.timeline
    .filter((item) => (
      item.source === "agent"
      && item.kind === "operator_control"
      && item.sequence >= firstRetainedSequence
    ))
    .map((item): TimelineLandmark => ({
      id: `operator-${item.id}`,
      sequence: item.sequence,
      kind: "operator_message",
      label: item.label,
      shortLabel: "your message",
    }));
  const frictionSequence = snapshot.friction.evidence.length === 0
    ? null
    : Math.max(...snapshot.friction.evidence);
  const friction = (
    snapshot.friction.kind === null
    || frictionSequence === null
    || frictionSequence < firstRetainedSequence
    || (
      snapshot.friction.kind === "confusion_loop"
      && snapshot.friction.repeated_command === null
    )
  )
    ? []
    : [{
      id: `friction-${snapshot.friction.kind}-${frictionSequence}`,
      sequence: frictionSequence,
      kind: "friction" as const,
      label: snapshot.friction.kind === "confusion_loop"
        ? `repeated “${snapshot.friction.repeated_command}”`
        : "no new place",
      shortLabel: snapshot.friction.kind === "confusion_loop"
        ? `repeated “${snapshot.friction.repeated_command}”`
        : "no new place",
    }];
  return [
    ...rooms,
    ...milestones,
    ...operatorMessages,
    ...friction,
  ].sort(
    (left, right) => left.sequence - right.sequence,
  );
}

function costCurve(points: LiveEconomicsPoint[]): string {
  const highest = points.at(-1)?.cumulative_cost_usd ?? 0;
  if (points.length < 2 || highest <= 0) return "";
  return points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 900;
      const y = 46 - (point.cumulative_cost_usd / highest) * 33;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
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
  const eventSequences = [...new Set(
    [
      ...latestSnapshot.timeline.map((item) => item.sequence),
      latestSnapshot.latest_sequence,
    ],
  )].sort((left, right) => left - right);
  const previousEventSequence = [...eventSequences].reverse().find(
    (sequence) => sequence < selectedSequence,
  );
  const nextEventSequence = eventSequences.find(
    (sequence) => sequence > selectedSequence,
  );
  const labelledLandmarks = ([
    "level_up",
    "operator_message",
    "friction",
  ] as const)
    .map((kind) => [...landmarks].reverse().find(
      (landmark) => landmark.kind === kind,
    ))
    .filter((landmark): landmark is TimelineLandmark => landmark !== undefined);
  const curve = costCurve(latestSnapshot.economics);

  return (
    <>
      <div className="live-timeline-heading">
        <small>
          Recent journey
          <span> · last {latestSnapshot.timeline.length} events</span>
        </small>
        <span className={[
          "live-timeline-prefix-state",
          snapshot.following_live ? "is-live" : "is-paused",
        ].join(" ")}>
          <i aria-hidden="true" />
          {snapshot.following_live ? "following live" : "paused"}
        </span>
        <span className="live-timeline-reading">
          {snapshot.turn === null ? null : <span>turn {snapshot.turn} · </span>}
          <span>seq {selectedSequence}</span>
        </span>
        <div className="live-timeline-transport" aria-label="Timeline transport">
          <button
            aria-label={snapshot.following_live
              ? "Pause timeline"
              : "Resume timeline"}
            type="button"
            onClick={() => onSelectThrough(
              snapshot.following_live ? snapshot.through_sequence : null,
            )}
          >
            {snapshot.following_live ? "⏸ Pause" : "▶ Resume"}
          </button>
          <button
            aria-label="Step to previous event"
            disabled={previousEventSequence === undefined}
            type="button"
            onClick={() => onSelectThrough(previousEventSequence ?? null)}
          >
            ◀ Step
          </button>
          <button
            aria-label="Step to next event"
            disabled={snapshot.following_live || nextEventSequence === undefined}
            type="button"
            onClick={() => onSelectThrough(nextEventSequence ?? null)}
          >
            Step ▶
          </button>
          <button
            aria-label="Jump to live"
            className="live-timeline-return"
            disabled={snapshot.following_live}
            type="button"
            onClick={() => onSelectThrough(null)}
          >
            ⏭ Jump to live
          </button>
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
            viewBox="0 0 900 52"
          >
            <polyline points={curve} />
          </svg>
        )}
        {landmarks.map((landmark) => (
          <button
            aria-label={`${landmarkKindLabel[landmark.kind]}: ${landmark.label}, ${landmark.kind === "operator_message" ? "retained at " : ""}sequence ${landmark.sequence}`}
            className={`live-timeline-landmark is-${landmark.kind}`}
            key={landmark.id}
            style={{ left: `${position(landmark.sequence)}%` }}
            title={`${landmarkKindLabel[landmark.kind]}: ${landmark.label} · ${landmark.kind === "operator_message" ? "retained at " : ""}seq ${landmark.sequence}`}
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
            {landmark.shortLabel}
          </span>
        ))}
        <div
          aria-hidden="true"
          className="live-timeline-cursor"
          style={{ left: `${position(selectedSequence)}%` }}
        />
        <input
          aria-label="Observed prefix"
          className="live-timeline-scrubber"
          max={lastSequence}
          min={firstSequence}
          type="range"
          value={Math.min(lastSequence, Math.max(firstSequence, selectedSequence))}
          onChange={(event) => onSelectThrough(Number(event.currentTarget.value))}
        />
        {landmarks.length === 0 ? (
          <span className="live-timeline-no-landmarks">
            No causal landmarks in the recent retained window
          </span>
        ) : null}
      </div>
    </>
  );
}
