import {
  ArrowRight,
  CircleStop,
  MessageSquareText,
  Pause,
  Play,
  ShieldAlert,
  Target,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { WorkspaceFixture } from "../../app/shellTypes";
import { StateBadge } from "../system/StateBadge";

type Action = "guide" | "revise" | "pause" | "resume" | "stop";

type Props = {
  fixture: WorkspaceFixture;
  open: boolean;
  selectedPlayer: string;
  selectedSession: string;
  onClose: () => void;
};

const actions: { id: Action; label: string; icon: typeof Target }[] = [
  { id: "guide", label: "Guide", icon: MessageSquareText },
  { id: "revise", label: "Revise goal", icon: Target },
  { id: "pause", label: "Pause", icon: Pause },
  { id: "resume", label: "Resume", icon: Play },
  { id: "stop", label: "Stop", icon: CircleStop },
];

export function AgentControlDialog({
  fixture,
  open,
  selectedPlayer,
  selectedSession,
  onClose,
}: Props) {
  const [action, setAction] = useState<Action>("guide");
  const input = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      input.current?.focus();
    }
  }, [open]);

  if (!open) {
    return null;
  }

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
          <button className="icon-button" type="button" aria-label="Close agent control" onClick={onClose}>
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="control-scope">
          <div><small>Player</small><strong>{selectedPlayer}</strong></div>
          <div><small>Session</small><strong>{selectedSession}</strong></div>
          <div><small>Observed sequence</small><strong>#{fixture.sequence}</strong></div>
          <StateBadge state="actual">Authenticated live session</StateBadge>
        </div>

        <div className="action-picker" role="tablist" aria-label="Agent control action">
          {actions.map(({ id, icon: Icon, label }) => (
            <button
              aria-selected={action === id}
              key={id}
              role="tab"
              type="button"
              onClick={() => setAction(id)}
            >
              <Icon size={14} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>

        <label className="control-message">
          <span>{action === "revise" ? "Replacement goal" : "Operator guidance"}</span>
          <textarea
            ref={input}
            rows={3}
            placeholder={
              action === "revise"
                ? "State the new verified objective"
                : "Add guidance for the next safe turn boundary"
            }
          />
        </label>

        <section className="control-preview" aria-labelledby="control-preview-heading">
          <div className="panel-heading">
            <span>
              <p className="eyebrow">Before confirmation</p>
              <h3 id="control-preview-heading">Effective control preview</h3>
            </span>
            <StateBadge state="incomplete">Fixture only</StateBadge>
          </div>
          <dl>
            <div><dt>Insertion</dt><dd>Next safe turn boundary</dd></div>
            <div><dt>Current goal</dt><dd>{fixture.objective}</dd></div>
            <div><dt>Allowed tools</dt><dd>Selected agent policy · 8 tools</dd></div>
            <div><dt>Remaining spend</dt><dd>$0.3158</dd></div>
            <div><dt>Maximum additional spend</dt><dd>$0.3158</dd></div>
            <div><dt>Concurrency check</dt><dd>Session must remain at seq {fixture.sequence}</dd></div>
          </dl>
        </section>

        <div className="control-warning">
          <ShieldAlert size={17} aria-hidden="true" />
          <p>
            B1 demonstrates the complete control contract but cannot send.
            Sending requires the authenticated gateway mutation and isolation
            gate in the Live increment.
          </p>
        </div>

        <footer className="dialog-actions">
          <button className="secondary-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary-button" type="button" disabled>
            Preview only <ArrowRight size={14} aria-hidden="true" />
          </button>
        </footer>
      </section>
    </div>
  );
}
