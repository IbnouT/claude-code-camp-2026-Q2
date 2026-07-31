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

export type StopReceipt = {
  session_id: string;
  player_id: string;
  state: "stopped";
  mode: "cooperative" | "forced_after_grace";
};

type Props = {
  open: boolean;
  player: string;
  session: string;
  onCancel: () => void;
  onConfirm: () => Promise<StopReceipt>;
};

export function SessionExitDialog({
  open,
  player,
  session,
  onCancel,
  onConfirm,
}: Props) {
  const cancel = useRef<HTMLButtonElement>(null);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStopping(false);
    setError(null);
    window.setTimeout(() => cancel.current?.focus(), 0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !stopping) {
        event.preventDefault();
        onCancel();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onCancel, open, stopping]);

  if (!open) return null;

  const stop = async () => {
    if (stopping) return;
    setStopping(true);
    setError(null);
    try {
      await onConfirm();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The session could not be stopped.",
      );
      setStopping(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="presentation">
      <section
        aria-labelledby="stop-session-heading"
        aria-modal="true"
        className="control-dialog stop-session-dialog"
        role="dialog"
      >
        <header className="dialog-heading">
          <span>
            <p className="eyebrow">Session lifecycle</p>
            <h2 id="stop-session-heading">Stop this session?</h2>
          </span>
          <button
            aria-label="Cancel stopping session"
            className="icon-button"
            disabled={stopping}
            type="button"
            onClick={onCancel}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="control-scope">
          <div><small>Player</small><strong>{player}</strong></div>
          <div><small>Session</small><strong>{session}</strong></div>
        </div>

        <div className="stop-session-summary">
          <CircleStop size={19} aria-hidden="true" />
          <span>
            <strong>The agent will leave the game.</strong>
            <small>
              The recording is preserved and the character becomes available
              for another session after cleanup completes.
            </small>
          </span>
        </div>

        <div className="control-warning">
          <ShieldAlert size={17} aria-hidden="true" />
          <p>
            A turn already in progress gets a bounded grace period. If it does
            not finish, only this verified session process group is stopped.
          </p>
        </div>

        {error !== null ? (
          <div className="control-result is-error" role="alert">
            <ShieldAlert size={16} aria-hidden="true" />
            <span><strong>Session is still running</strong><small>{error}</small></span>
          </div>
        ) : null}

        <footer className="dialog-actions">
          <button
            className="secondary-button"
            disabled={stopping}
            ref={cancel}
            type="button"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            className="danger-button"
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
