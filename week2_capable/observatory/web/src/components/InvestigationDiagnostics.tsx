import { AlertTriangle, ChevronRight, CircleAlert, Info } from "lucide-react";
import type { DiagnosticRecord } from "../data/investigation";

type Props = {
  diagnostics: DiagnosticRecord[];
  selected: string | null;
  onSelect: (diagnostic: DiagnosticRecord) => void;
};

const icons = {
  critical: CircleAlert,
  warning: AlertTriangle,
  notice: Info,
};

export function InvestigationDiagnostics({
  diagnostics,
  selected,
  onSelect,
}: Props) {
  return (
    <section className="diagnostics-panel investigation-diagnostics" aria-labelledby="run-diagnostics-title">
      <header className="rail-heading">
        <div>
          <p className="eyebrow">Deterministic findings</p>
          <h2 id="run-diagnostics-title">Diagnostics</h2>
        </div>
        <span className="count-badge">{diagnostics.length}</span>
      </header>
      <div className="diagnostic-list">
        {diagnostics.map((diagnostic) => {
          const Icon = icons[diagnostic.severity];
          return (
            <button
              key={diagnostic.id}
              type="button"
              className={
                selected === diagnostic.id
                  ? `diagnostic-card severity-${diagnostic.severity} is-selected`
                  : `diagnostic-card severity-${diagnostic.severity}`
              }
              onClick={() => onSelect(diagnostic)}
            >
              <span className="diagnostic-icon">
                <Icon size={16} aria-hidden="true" />
              </span>
              <span className="diagnostic-copy">
                <strong>{diagnostic.title}</strong>
                <span>{diagnostic.detail}</span>
                <small>{diagnostic.mechanism}</small>
              </span>
              <ChevronRight size={16} aria-hidden="true" className="diagnostic-arrow" />
            </button>
          );
        })}
      </div>
    </section>
  );
}
