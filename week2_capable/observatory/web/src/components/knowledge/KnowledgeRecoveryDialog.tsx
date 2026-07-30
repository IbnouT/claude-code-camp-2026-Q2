import { useEffect, useState } from "react";
import type { KnowledgeRecoveryAction } from "../../data/recoverKnowledge";

type Props = {
  action: KnowledgeRecoveryAction | null;
  snapshotDigest: string | null;
  onCancel: () => void;
  onConfirm: (request: KnowledgeRecoveryAction) => Promise<void>;
};

export function KnowledgeRecoveryDialog({
  action,
  snapshotDigest,
  onCancel,
  onConfirm,
}: Props) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    if (action) {
      setReason(action.reason);
      setError(null);
      setWorking(false);
    }
  }, [action]);

  if (!action) return null;
  const restoring = action.action === "restore";
  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={onCancel}
    >
      <form
        aria-labelledby="knowledge-recovery-title"
        aria-modal="true"
        className="control-dialog knowledge-recovery-dialog"
        role="dialog"
        method="dialog"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          setWorking(true);
          setError(null);
          void onConfirm({ ...action, reason }).catch((failure: unknown) => {
            setError(
              failure instanceof Error
                ? failure.message
                : "Knowledge recovery failed.",
            );
            setWorking(false);
          });
        }}
      >
        <p className="eyebrow">Authenticated session control</p>
        <h2 id="knowledge-recovery-title">
          {restoring ? "Restore this snapshot?" : "Snapshot and reset knowledge?"}
        </h2>
        <p>
          This action uses session <strong>{action.sessionId}</strong> at exact
          sequence <strong>{action.expectedSequence}</strong>. It fails if the
          session advances before confirmation.
        </p>
        {restoring ? (
          <dl>
            <div><dt>Snapshot</dt><dd>{action.snapshotId}</dd></div>
            <div><dt>Verified digest</dt><dd>{snapshotDigest}</dd></div>
          </dl>
        ) : (
          <p>
            A verified snapshot is created first. Learned assertions are then
            retracted through append-only history.
          </p>
        )}
        <label>
          Reason
          <input
            required
            maxLength={240}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <footer>
          <button
            className="secondary-button"
            type="button"
            disabled={working}
            onClick={onCancel}
          >
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={working}>
            {working
              ? "Applying…"
              : restoring
                ? "Confirm restore"
                : "Confirm snapshot and reset"}
          </button>
        </footer>
      </form>
    </div>
  );
}
