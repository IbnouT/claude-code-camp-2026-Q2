import {
  ChevronDown,
  ChevronRight,
  List,
} from "lucide-react";
import type {
  RecordedSessionInvestigation,
  SessionEvidenceRecord,
} from "../../data/recordedSession";
import {
  formatSessionDuration,
  formatSessionRecordLabel,
  formatSessionRecordPreview,
  type SessionIteration,
  sessionStepKind,
} from "./sessionsUnifiedModel";

type Props = {
  investigation: RecordedSessionInvestigation;
  iterations: SessionIteration[];
  selectedIteration: number;
  selectedRecord: SessionEvidenceRecord | null;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
};

export function SessionsSequenceLens({
  investigation,
  iterations,
  selectedIteration,
  selectedRecord,
  onSelectRecord,
}: Props) {
  return (
    <section className="sessions-unified-pane is-sequence">
      <div className="sessions-unified-pane-header">
        <List size={14} aria-hidden="true" />
        Temporal lens · Sequence
      </div>
      <div className="sessions-unified-sequence">
        {iterations.map((iteration) => (
          <IterationGroup
            investigation={investigation}
            iteration={iteration.iteration}
            key={iteration.iteration}
            records={iteration.records}
            selectedRecord={selectedRecord}
            selected={iteration.iteration === selectedIteration}
            onSelectRecord={onSelectRecord}
          />
        ))}
      </div>
    </section>
  );
}

function IterationGroup({
  investigation,
  iteration,
  records,
  selected,
  selectedRecord,
  onSelectRecord,
}: {
  investigation: RecordedSessionInvestigation;
  iteration: number;
  records: SessionEvidenceRecord[];
  selected: boolean;
  selectedRecord: SessionEvidenceRecord | null;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
}) {
  const duration = records.reduce((total, record) => total + record.duration_ms, 0);
  const cost = records.reduce((total, record) => total + record.cost_usd, 0);
  const toolCount = records.filter((record) => record.kind.includes("tool")).length;

  return (
    <article className="sessions-unified-iteration">
      <button
        className={`sessions-unified-iteration-head${selected ? " is-selected" : ""}`}
        type="button"
        onClick={() => {
          const record = records.find((item) => item.id === selectedRecord?.id)
            ?? records.at(-1);
          if (record) onSelectRecord(record);
        }}
      >
        {selected
          ? <ChevronDown size={13} aria-hidden="true" />
          : <ChevronRight size={13} aria-hidden="true" />}
        <b>ITERATION {iteration}</b>
        <span>
          <small>{formatSessionDuration(duration)}</small>
          <small><strong>{toolCount}</strong> tool calls</small>
          {selected && investigation.model ? <small>{investigation.model}</small> : null}
          <small className="is-cost">${cost.toFixed(4)}</small>
        </span>
      </button>
      {selected ? (
        <div className="sessions-unified-steps">
          {records
            .filter((record) => record.kind !== "iteration")
            .slice(0, 5)
            .map((record) => (
            <EvidenceStep
              key={record.id}
              record={record}
              selected={record.id === selectedRecord?.id}
              onSelect={() => onSelectRecord(record)}
            />
            ))}
        </div>
      ) : null}
    </article>
  );
}

function EvidenceStep({
  record,
  selected,
  onSelect,
}: {
  record: SessionEvidenceRecord;
  selected: boolean;
  onSelect: () => void;
}) {
  const kind = sessionStepKind(record);
  const expanded = selected || kind === "plan" || kind === "tool";

  return (
    <article className={`sessions-unified-step is-${kind}${selected ? " is-selected" : ""}`}>
      <button type="button" onClick={onSelect}>
        {expanded
          ? <ChevronDown size={12} aria-hidden="true" />
          : <ChevronRight size={12} aria-hidden="true" />}
        <b>{formatSessionRecordLabel(record)}</b>
        <span>
          {record.duration_ms > 0
            ? formatSessionDuration(record.duration_ms)
            : record.form}
        </span>
      </button>
      {expanded ? (
        <div className="sessions-unified-step-body">
          <div className={kind === "tool" ? "is-terminal" : "is-preview"}>
            {formatSessionRecordPreview(record)}
          </div>
          <div className="sessions-unified-deep-links">
            <button type="button" onClick={onSelect}>exact fields →</button>
            {record.source === "gateway" ? (
              <>
                <button type="button" onClick={onSelect}>telnet / raw wire →</button>
                <button type="button" onClick={onSelect}>gateway log →</button>
              </>
            ) : null}
            {record.kind === "response" ? (
              <button type="button" onClick={onSelect}>model response →</button>
            ) : null}
          </div>
        </div>
      ) : null}
    </article>
  );
}
