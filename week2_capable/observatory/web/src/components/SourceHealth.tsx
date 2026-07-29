import { DatabaseZap } from "lucide-react";
import type { SourceState } from "../app/types";

type Props = {
  sources: SourceState[];
};

export function SourceHealth({ sources }: Props) {
  const ready = sources.filter((source) => source.state === "ready").length;

  return (
    <details className="source-health">
      <summary>
        <DatabaseZap size={14} aria-hidden="true" />
        Evidence
        <span>{ready}/{sources.length}</span>
      </summary>
      <div className="source-menu">
        <p className="eyebrow">Source capabilities</p>
        {sources.map((source) => (
          <div className="source-row" key={source.id}>
            <i className={`source-state state-${source.state}`} aria-hidden="true" />
            <span>
              <strong>{source.label}</strong>
              <small>{source.detail}</small>
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}
