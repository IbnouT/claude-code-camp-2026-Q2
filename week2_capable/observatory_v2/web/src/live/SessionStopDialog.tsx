import {
  CircleStop,
  ShieldAlert,
  X,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
} from "react";
import type { LiveRouteIdentity } from "../routes";

export type StopReceipt = {
  session_id: string;
  player_id: string;
  state: "stopped";
  mode: "cooperative" | "forced_after_grace";
};

type Props = {
  identity: LiveRouteIdentity;
  onCancel: () => void;
  onStopFailed: () => void;
  onStopping: () => void;
  onStopped: () => void;
};

type StopFailure = {
  detail?: string;
};

export function SessionStopDialog({
  identity,
  onCancel,
  onStopFailed,
  onStopping,
  onStopped,
}: Props) {
  const cancel = useRef<HTMLButtonElement>(null);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    window.setTimeout(() => cancel.current?.focus(), 0);
  }, []);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !stopping) {
        event.preventDefault();
        onCancel();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onCancel, stopping]);

  const stop = async () => {
    if (stopping) return;
    setStopping(true);
    setError(null);
    onStopping();
    try {
      const response = await fetch(
        `/api/sessions/${encodeURIComponent(identity.sessionId)}/stop`,
        { method: "POST" },
      );
      const payload = await response.json() as StopReceipt | StopFailure;
      if (!response.ok) {
        throw new Error(
          "detail" in payload && payload.detail
            ? payload.detail
            : "The session could not be stopped.",
        );
      }
      onStopped();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The session could not be stopped.",
      );
      setStopping(false);
      onStopFailed();
    }
  };

  return (
    <div className="live-dialog-backdrop" role="presentation">
      <section
        aria-labelledby="stop-session-heading"
        aria-modal="true"
        className="live-stop-dialog"
        role="dialog"
      >
        <header className="live-dialog-heading">
          <span>
            <p>Session lifecycle</p>
            <h2 id="stop-session-heading">Stop this session?</h2>
          </span>
          <button
            aria-label="Cancel stopping session"
            className="live-icon-button"
            disabled={stopping}
            type="button"
            onClick={onCancel}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="live-stop-scope">
          <div><small>Player</small><strong>{identity.playerId}</strong></div>
          <div><small>Session</small><strong>{identity.sessionId}</strong></div>
        </div>

        <div className="live-stop-summary">
          <CircleStop size={19} aria-hidden="true" />
          <span>
            <strong>The agent will leave the game.</strong>
            <small>
              The recording is preserved and the character becomes available
              for another session after cleanup completes.
            </small>
          </span>
        </div>

        <div className="live-stop-warning">
          <ShieldAlert size={17} aria-hidden="true" />
          <p>
            A turn already in progress gets a bounded grace period. If it does
            not finish, only this verified session process group is stopped.
          </p>
        </div>

        {error !== null ? (
          <div className="live-stop-error" role="alert">
            <ShieldAlert size={16} aria-hidden="true" />
            <span><strong>Session is still running</strong><small>{error}</small></span>
          </div>
        ) : null}

        <footer className="live-dialog-actions">
          <button
            className="live-secondary-button"
            disabled={stopping}
            ref={cancel}
            type="button"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            className="live-danger-button"
            disabled={stopping}
            type="button"
            onClick={() => void stop()}
          >
            {stopping ? "Stopping…" : "Stop session"}
          </button>
        </footer>
      </section>
    </div>
  );
}
