import { AlertTriangle, ChevronRight, CircleAlert, Info } from "lucide-react";
import { diagnostics } from "../app/demo";
import type { Diagnostic } from "../app/types";

const icons = {
  critical: CircleAlert,
  warning: AlertTriangle,
  notice: Info,
};

type Props = {
  onSelect: (sequence: number) => void;
  items?: Diagnostic[];
};

export function DiagnosticStack({ onSelect, items = diagnostics }: Props) {
  return (
    <section className="diagnostics-panel" aria-labelledby="diagnostics-title">
      <header className="rail-heading">
        <div>
          <p className="eyebrow">Needs attention</p>
          <h2 id="diagnostics-title">Diagnostics</h2>
        </div>
        <span className="count-badge">{items.length}</span>
      </header>
      <div className="diagnostic-list">
        {items.length === 0 && (
          <p className="source-empty">
            Deterministic diagnostics begin in the next analysis stage.
          </p>
        )}
        {items.map((diagnostic) => {
          const Icon = icons[diagnostic.severity];
          return (
            <button
              key={diagnostic.id}
              className={`diagnostic-card severity-${diagnostic.severity}`}
              type="button"
              onClick={() => onSelect(diagnostic.at)}
            >
              <span className="diagnostic-icon">
                <Icon size={16} aria-hidden="true" />
              </span>
              <span className="diagnostic-copy">
                <strong>{diagnostic.title}</strong>
                <span>{diagnostic.detail}</span>
                <small>Turn {diagnostic.at} · {diagnostic.evidence} evidence links</small>
              </span>
              <ChevronRight size={16} aria-hidden="true" className="diagnostic-arrow" />
            </button>
          );
        })}
      </div>
    </section>
  );
}
