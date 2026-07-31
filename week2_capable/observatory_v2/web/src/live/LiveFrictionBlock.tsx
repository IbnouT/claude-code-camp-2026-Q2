import {
  useState,
} from "react";
import type {
  LiveFrictionDiagnostic,
  Snapshot,
} from "../contracts";
import type { LiveSnapshotState } from "./useLiveSnapshot";

export function LiveFrictionBlock({
  captureStatus,
  connectionState,
  snapshot,
}: {
  captureStatus: string | null;
  connectionState: LiveSnapshotState;
  snapshot: Snapshot;
}) {
  const [showEvidence, setShowEvidence] = useState(false);
  const guarded = guardState(snapshot, connectionState, captureStatus);
  const fired = guarded === null && snapshot.friction.kind !== null;
  return (
    <section className={["live-rail-block", "live-friction-block", fired ? "is-fired" : ""].join(" ")}>
      <h2>Progress</h2>
      {guarded === null ? (
        <FrictionResult
          combat={snapshot.combat}
          diagnostic={snapshot.friction}
          showEvidence={showEvidence}
          onToggleEvidence={() => setShowEvidence((current) => !current)}
        />
      ) : guarded}
    </section>
  );
}

function FrictionResult({
  combat,
  diagnostic,
  onToggleEvidence,
  showEvidence,
}: {
  combat: boolean;
  diagnostic: LiveFrictionDiagnostic;
  onToggleEvidence: () => void;
  showEvidence: boolean;
}) {
  const loop = diagnostic.kind === "confusion_loop";
  const fired = diagnostic.kind !== null;
  return (
    <div className="live-friction-result">
      {fired ? (
        <>
          <strong>{loop ? "Possible navigation loop" : "Possible progress stall"}</strong>
          <small><code>{diagnostic.kind}</code> · {diagnostic.threshold}</small>
        </>
      ) : null}
      <p>
        {diagnostic.new_places} new {diagnostic.new_places === 1 ? "place" : "places"}
        {" · "}{diagnostic.window_iterations} iterations
      </p>
      <p>{diagnostic.iterations_since_new_place === null
        ? "No new place retained"
        : `${diagnostic.iterations_since_new_place} iterations since the last new place`}</p>
      {diagnostic.repeated_count > 1 ? (
        <p>
          <code>{diagnostic.repeated_command}</code>
          {" repeated "}×{diagnostic.repeated_count} in the current room
        </p>
      ) : null}
      {combat ? <small>Combat in progress. Spatial progress may pause.</small> : null}
      {fired ? (
        <>
          <button type="button" onClick={onToggleEvidence}>
            {showEvidence ? "Hide attempts" : "Inspect attempts"}
          </button>
          {showEvidence ? (
            <p className="live-friction-evidence">
              Evidence sequences {diagnostic.evidence.join(", ") || "not retained"}
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function guardState(
  snapshot: Snapshot,
  connectionState: LiveSnapshotState,
  captureStatus: string | null,
): React.ReactNode | null {
  if (connectionState === "reconnecting") {
    return <GuardedState title="Live evidence connection lost" detail="Agent state is unknown until the connection recovers." />;
  }
  if (snapshot.lifecycle === "crashed") {
    return <GuardedState title="Agent process ended unexpectedly" detail={`Retained evidence stops at sequence ${snapshot.latest_sequence}.`} />;
  }
  if (snapshot.lifecycle === "stopped") {
    return <GuardedState title="Session stopped" detail={`No further activity is expected after sequence ${snapshot.latest_sequence}.`} />;
  }
  if (snapshot.control_state === "paused") {
    return <GuardedState title="Agent paused by operator" detail="No new activity is expected until it is resumed." />;
  }
  const progressGaps = new Set([
    "agent_events_missing",
    "agent_events_incomplete",
    "gateway_events_missing",
    "position_not_observed",
  ]);
  if (
    captureStatus !== "complete"
    || snapshot.capture_gaps.some((gap) => progressGaps.has(gap))
  ) {
    return <GuardedState title="Progress cannot be determined" detail="This session reports incomplete retained evidence." />;
  }
  return null;
}

function GuardedState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="live-friction-result is-guarded">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}
