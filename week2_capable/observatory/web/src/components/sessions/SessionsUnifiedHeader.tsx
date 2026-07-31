import {
  CircleDollarSign,
  List,
  Map as MapIcon,
} from "lucide-react";
import type {
  RecordedSessionInvestigation,
  SessionEvidenceRecord,
  SessionsLens,
} from "../../data/recordedSession";
import {
  countSessionTurns,
  formatSessionTitle,
  formatSessionTokens,
  maxSessionContextTokens,
} from "./sessionsUnifiedModel";

type Props = {
  investigation: RecordedSessionInvestigation;
  records: SessionEvidenceRecord[];
  selectedIteration: number;
  selectedTurn: number | "unknown";
  selectedLabel: string;
  onLensChange: (lens: SessionsLens) => void;
};

export function SessionsUnifiedHeader({
  investigation,
  records,
  selectedIteration,
  selectedTurn,
  selectedLabel,
  onLensChange,
}: Props) {
  return (
    <>
      <div className="sessions-unified-subbar">
        <h1>
          {formatSessionTitle(investigation)}
          <span className={`sessions-unified-badge ${
            investigation.run.success ? "is-success" : "is-failed"
          }`}>
            {investigation.run.success ? "success" : "failed"}
          </span>
        </h1>
        <div className="sessions-unified-meters">
          <span><b>{investigation.run.iterations}</b> iterations</span>
          <span><b>{countSessionTurns(records)}</b> turns</span>
          <span>
            ctx peak <b>{formatSessionTokens(maxSessionContextTokens(investigation))}</b>
          </span>
          <button type="button" onClick={() => onLensChange("cost")}>
            total <b>${investigation.cost.total_usd.toFixed(3)}</b>
          </button>
        </div>
        <div className="sessions-unified-switch" role="tablist" aria-label="Session view">
          <button aria-selected="true" role="tab" type="button">
            <MapIcon size={14} aria-hidden="true" />
            Map + Sequence
          </button>
          <button
            aria-selected="false"
            role="tab"
            type="button"
            onClick={() => onLensChange("sequence")}
          >
            <List size={14} aria-hidden="true" />
            Sequence
          </button>
          <button
            aria-selected="false"
            role="tab"
            type="button"
            onClick={() => onLensChange("cost")}
          >
            <CircleDollarSign size={14} aria-hidden="true" />
            Cost
          </button>
        </div>
      </div>
      <div className="sessions-unified-sync" role="status">
        <span aria-hidden="true" />
        Linked selection:
        <b>
          Iteration {selectedIteration} · Turn {selectedTurn} · {selectedLabel}
        </b>
        : highlighted in both lenses. Pick in either, the other follows.
      </div>
    </>
  );
}
