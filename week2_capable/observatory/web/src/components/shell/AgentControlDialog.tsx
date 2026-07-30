import {
  ArrowRight,
  CheckCircle2,
  CircleStop,
  MessageSquareText,
  Pause,
  Play,
  ShieldAlert,
  Target,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { StateBadge } from "../system/StateBadge";

export type ControlAction = "guide" | "revise" | "pause" | "resume" | "stop";

export type ControlDraft = {
  request_id: string;
  action: ControlAction;
  instruction: string | null;
  expected_sequence: number;
};

export type ControlReceipt = {
  request_id: string;
  action: ControlAction;
  state: string;
  insertion: string;
};

type Props = {
  open: boolean;
  selectedPlayer: string;
  selectedSession: string;
  sequence: number;
  objective: string | null;
  model: string | null;
  tools: string[];
  onClose: () => void;
  onSubmit: (draft: ControlDraft) => Promise<ControlReceipt>;
};

const actions: {
  id: ControlAction;
  label: string;
  icon: typeof Target;
}[] = [
  { id: "guide", label: "Guide", icon: MessageSquareText },
  { id: "revise", label: "Revise goal", icon: Target },
  { id: "pause", label: "Pause", icon: Pause },
  { id: "resume", label: "Resume", icon: Play },
  { id: "stop", label: "Stop", icon: CircleStop },
];

export function AgentControlDialog({
  open,
  selectedPlayer,
  selectedSession,
  sequence,
  objective,
  model,
  tools,
  onClose,
  onSubmit,
}: Props) {
  const [action, setAction] = useState<ControlAction>("guide");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<ControlReceipt | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const needsInstruction = action === "guide" || action === "revise";
  const canSubmit = !busy && (!needsInstruction || instruction.trim().length > 0);

  useEffect(() => {
    if (open) {
      setError(null);
      setReceipt(null);
      input.current?.focus();
    }
  }, [open]);

  if (!open) {
    return null;
  }

  const submit = async () => {
    if (!canSubmit) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await onSubmit({
        request_id: crypto.randomUUID(),
        action,
        instruction: needsInstruction ? instruction.trim() : null,
        expected_sequence: sequence,
      });
      setReceipt(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Control failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        aria-label="Direct the selected agent"
        aria-modal="true"
        className="control-dialog"
        role="dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="dialog-heading">
          <span>
            <p className="eyebrow">Mortal control plane</p>
            <h2>Direct the selected agent</h2>
          </span>
          <button
            className="icon-button"
            type="button"
            aria-label="Close agent control"
            onClick={onClose}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="control-scope">
          <div><small>Player</small><strong>{selectedPlayer}</strong></div>
          <div><small>Session</small><strong>{selectedSession}</strong></div>
          <div><small>Expected sequence</small><strong>#{sequence}</strong></div>
          <StateBadge state="actual">Authenticated live session</StateBadge>
        </div>

        <div className="action-picker" role="tablist" aria-label="Agent control action">
          {actions.map(({ id, icon: Icon, label }) => (
            <button
              aria-selected={action === id}
              key={id}
              role="tab"
              type="button"
              onClick={() => {
                setAction(id);
                setError(null);
                setReceipt(null);
              }}
            >
              <Icon size={14} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>

        {needsInstruction ? (
          <label className="control-message">
            <span>{action === "revise" ? "Replacement goal" : "Operator guidance"}</span>
            <textarea
              ref={input}
              rows={3}
              value={instruction}
              placeholder={
                action === "revise"
                  ? "State the new verified objective"
                  : "Add guidance for the next safe iteration boundary"
              }
              onChange={(event) => setInstruction(event.target.value)}
            />
          </label>
        ) : (
          <div className="control-lifecycle-summary">
            <strong>{lifecycleTitle(action)}</strong>
            <span>{lifecycleDetail(action)}</span>
          </div>
        )}

        <section className="control-preview" aria-labelledby="control-preview-heading">
          <div className="panel-heading">
            <span>
              <p className="eyebrow">Before confirmation</p>
              <h3 id="control-preview-heading">Effective control preview</h3>
            </span>
            <StateBadge state="actual">Live target</StateBadge>
          </div>
          <dl>
            <div><dt>Insertion</dt><dd>Next safe iteration boundary</dd></div>
            <div><dt>Current goal</dt><dd>{objective ?? "Not captured"}</dd></div>
            <div>
              <dt>Allowed tools</dt>
              <dd>{tools.length > 0 ? tools.join(", ") : "Not captured"}</dd>
            </div>
            <div><dt>Model</dt><dd>{model ?? "Not captured"}</dd></div>
            <div><dt>Maximum additional spend</dt><dd>Not captured</dd></div>
            <div><dt>Concurrency check</dt><dd>Session must remain at seq {sequence}</dd></div>
          </dl>
        </section>

        <div className="control-warning">
          <ShieldAlert size={17} aria-hidden="true" />
          <p>
            This targets only the selected launcher-owned agent. Guidance is
            labeled as an operator message. It is never presented as agent
            reasoning, a benchmark result, or game truth.
          </p>
        </div>

        {error !== null ? (
          <div className="control-result is-error" role="alert">
            <ShieldAlert size={16} aria-hidden="true" />
            <span><strong>Control was not sent</strong><small>{error}</small></span>
          </div>
        ) : null}
        {receipt !== null ? (
          <div className="control-result is-success" role="status">
            <CheckCircle2 size={16} aria-hidden="true" />
            <span>
              <strong>{receipt.action} accepted</strong>
              <small>{receipt.insertion.replaceAll("_", " ")} · {receipt.state}</small>
            </span>
          </div>
        ) : null}

        <footer className="dialog-actions">
          <button className="secondary-button" type="button" onClick={onClose}>
            {receipt === null ? "Cancel" : "Close"}
          </button>
          <button
            className="primary-button"
            type="button"
            disabled={!canSubmit || receipt !== null}
            onClick={() => void submit()}
          >
            {busy ? "Sending…" : `Confirm ${action}`}
            <ArrowRight size={14} aria-hidden="true" />
          </button>
        </footer>
      </section>
    </div>
  );
}

function lifecycleTitle(action: ControlAction): string {
  return {
    guide: "",
    revise: "",
    pause: "Pause before the next model request",
    resume: "Resume from the blocked iteration boundary",
    stop: "End the selected agent session",
  }[action];
}

function lifecycleDetail(action: ControlAction): string {
  return {
    guide: "",
    revise: "",
    pause: "The current provider request cannot be interrupted. No later iteration starts.",
    resume: "The agent continues with the same context and objective.",
    stop: "The agent records an operator stop and exits without another model request.",
  }[action];
}
