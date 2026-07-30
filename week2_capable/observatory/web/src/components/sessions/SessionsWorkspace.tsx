import {
  AlertTriangle,
  ArrowUpRight,
  BookMarked,
  Bot,
  Braces,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Eye,
  FileJson2,
  GitBranch,
  Layers3,
  Map as MapIcon,
  MessageSquareText,
  Pause,
  Play,
  Radio,
  Search,
  SkipBack,
  SkipForward,
  Sparkles,
  Telescope,
  TriangleAlert,
  Waypoints,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import "../../styles/sessions.css";
import "../../styles/world.css";
import type {
  RecordedSessionInvestigation,
  SessionDiagnostic,
  SessionEvidenceForm,
  SessionEvidenceRecord,
  SessionsLens,
} from "../../data/recordedSession";
import type {
  DiagnosticHistory,
  InvestigatorAnnotation,
} from "../../data/incidents";
import { useDiagnosticHistory } from "../../data/useDiagnosticHistory";
import {
  matchesSessionQuery,
  recordAncestry,
} from "../../data/recordedSession";
import { StateBadge } from "../system/StateBadge";
import { WorldExplorer } from "../world/WorldExplorer";
import { IncidentWorkflow } from "./IncidentWorkflow";

type Props = {
  investigation: RecordedSessionInvestigation | null;
  loading: boolean;
  error: string | null;
  sourceState: "recorded" | "offline";
  incident: {
    annotations: InvestigatorAnnotation[];
    sourceVersions: Record<string, string>;
    redactionPolicy: string | null;
    history: DiagnosticHistory | null;
  };
  onOpenSearch: () => void;
  onOpenRun: (runId: string) => void;
};

const lenses: {
  id: SessionsLens;
  label: string;
  icon: typeof MapIcon;
}[] = [
  { id: "story", label: "Story", icon: MapIcon },
  { id: "sequence", label: "Sequence", icon: GitBranch },
  { id: "evidence", label: "Evidence", icon: Layers3 },
  { id: "cost", label: "Cost", icon: CircleDollarSign },
  { id: "diagnostics", label: "Diagnostics", icon: TriangleAlert },
];

const forms: {
  id: SessionEvidenceForm;
  label: string;
  icon: typeof Radio;
}[] = [
  { id: "wire", label: "Wire", icon: Radio },
  { id: "parsed", label: "Parsed", icon: Braces },
  { id: "rendered", label: "Rendered", icon: Eye },
  { id: "believed", label: "Believed", icon: Sparkles },
  { id: "truth", label: "Truth", icon: Telescope },
];

type ReplayStep = "event" | "turn" | "milestone";

const defaultSavedViews = [
  { label: "Model work", query: "kind:response" },
  { label: "Wire frames", query: "form:wire" },
  { label: "Failures", query: "failed" },
  { label: "Costed calls", query: "source:agent kind:response" },
];

function lensFromUrl(): SessionsLens {
  const value = new URL(window.location.href).searchParams.get("lens");
  return lenses.some(({ id }) => id === value)
    ? value as SessionsLens
    : "story";
}

export function SessionsWorkspace({
  investigation,
  loading,
  error,
  sourceState,
  incident,
  onOpenSearch,
  onOpenRun,
}: Props) {
  const [lens, setLens] = useState<SessionsLens>(lensFromUrl);
  const [selectedRecordId, setSelectedRecordId] = useState(
    () => new URL(window.location.href).searchParams.get("record"),
  );
  const [selectedRoomId, setSelectedRoomId] = useState(
    () => new URL(window.location.href).searchParams.get("room"),
  );
  const [query, setQuery] = useState("");
  const [replayStep, setReplayStep] = useState<ReplayStep>("turn");
  const [playing, setPlaying] = useState(false);
  const [savedViews, setSavedViews] = useState(defaultSavedViews);
  const diagnosticHistory = useDiagnosticHistory(
    investigation?.player_id ?? "",
    sourceState === "recorded",
  );
  const chronologicalRecords = useMemo(
    () => orderRecords(investigation?.records ?? []),
    [investigation],
  );
  const selectedRecord = investigation?.records.find(
    (record) => record.id === selectedRecordId,
  ) ?? null;
  const selectedIndex = Math.max(
    0,
    chronologicalRecords.findIndex((record) => record.id === selectedRecordId),
  );
  const visibleRecords = chronologicalRecords.slice(0, selectedIndex + 1);
  const throughGatewaySequence = Math.max(
    0,
    ...visibleRecords
      .filter((record) => record.source === "gateway")
      .map((record) => record.sequence),
  );

  useEffect(() => {
    if (investigation === null) return;
    if (
      selectedRecordId !== null
      && investigation.records.some((record) => record.id === selectedRecordId)
    ) return;
    const diagnostic = investigation.diagnostics[0];
    const initial = diagnostic?.at_record
      ?? investigation.records.find((record) => record.kind === "response")?.id
      ?? investigation.records[0]?.id
      ?? null;
    setSelectedRecordId(initial);
  }, [investigation, selectedRecordId]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("lens", lens);
    if (selectedRecordId) url.searchParams.set("record", selectedRecordId);
    else url.searchParams.delete("record");
    if (selectedRoomId) url.searchParams.set("room", selectedRoomId);
    else url.searchParams.delete("room");
    window.history.replaceState(null, "", url);
  }, [lens, selectedRecordId, selectedRoomId]);

  useEffect(() => {
    const restore = () => {
      const url = new URL(window.location.href);
      setLens(lensFromUrl());
      setSelectedRecordId(url.searchParams.get("record"));
      setSelectedRoomId(url.searchParams.get("room"));
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => {
    if (!playing || chronologicalRecords.length === 0) return;
    const timer = window.setTimeout(() => {
      const next = nextReplayIndex(
        chronologicalRecords,
        selectedIndex,
        replayStep,
        1,
      );
      if (next === selectedIndex) {
        setPlaying(false);
        return;
      }
      setSelectedRecordId(chronologicalRecords[next]?.id ?? null);
    }, replayStep === "event" ? 650 : 950);
    return () => window.clearTimeout(timer);
  }, [
    chronologicalRecords,
    playing,
    replayStep,
    selectedIndex,
  ]);

  if (loading) {
    return (
      <section className="sessions-state" aria-live="polite">
        <Waypoints size={24} aria-hidden="true" />
        <strong>Reconstructing recorded evidence</strong>
        <span>Joining agent, gateway, wire, parse, and outcome records.</span>
      </section>
    );
  }
  if (error) {
    return (
      <section className="sessions-state is-error" role="alert">
        <AlertTriangle size={24} aria-hidden="true" />
        <strong>Recorded session unavailable</strong>
        <span>{error}</span>
      </section>
    );
  }
  if (investigation === null) {
    return (
      <section className="sessions-state">
        <FileJson2 size={24} aria-hidden="true" />
        <strong>No recorded session selected</strong>
        <span>
          Configure a benchmark evidence root or load a sanitized incident
          capsule.
        </span>
      </section>
    );
  }

  const selectRecord = (record: SessionEvidenceRecord) => {
    setPlaying(false);
    setSelectedRecordId(record.id);
    if (record.room_id) setSelectedRoomId(record.room_id);
  };
  const selectRoom = (roomId: string) => {
    setPlaying(false);
    setSelectedRoomId(roomId);
    const record = [...investigation.records].reverse().find(
      (candidate) => candidate.room_id === roomId,
    );
    if (record) setSelectedRecordId(record.id);
  };
  const moveReplay = (direction: -1 | 1) => {
    setPlaying(false);
    const next = nextReplayIndex(
      chronologicalRecords,
      selectedIndex,
      replayStep,
      direction,
    );
    const record = chronologicalRecords[next];
    if (record) selectRecord(record);
  };
  const saveCurrentView = () => {
    const trimmed = query.trim();
    if (!trimmed || savedViews.some((view) => view.query === trimmed)) return;
    setSavedViews((current) => [
      ...current,
      { label: trimmed, query: trimmed },
    ]);
  };

  return (
    <section className="sessions-workspace">
      <SessionHeader
        investigation={investigation}
        sourceState={sourceState}
        onOpenSearch={onOpenSearch}
      />
      <div className="sessions-lensbar">
        <div className="sessions-lenses" role="tablist" aria-label="Session lenses">
          {lenses.map(({ id, label, icon: Icon }) => (
            <button
              aria-selected={lens === id}
              key={id}
              role="tab"
              type="button"
              onClick={() => setLens(id)}
            >
              <Icon size={14} aria-hidden="true" />
              {label}
              {id === "diagnostics" && investigation.diagnostics.length > 0
                ? <span>{investigation.diagnostics.length}</span>
                : null}
            </button>
          ))}
        </div>
        <div className="sessions-query">
          <label className="sessions-filter">
            <Search size={14} aria-hidden="true" />
            <span className="sr-only">Filter session evidence</span>
            <input
              value={query}
              placeholder="Filter, for example source:gateway or kind:wire"
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <button
            aria-label="Save current evidence view"
            className="icon-button"
            disabled={!query.trim()}
            title="Keep this query as a local view"
            type="button"
            onClick={saveCurrentView}
          >
            <BookMarked size={14} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="sessions-controlbar">
        <div className="replay-controls" aria-label="Recorded session replay">
          <button
            aria-label={`Previous ${replayStep}`}
            className="icon-button"
            type="button"
            onClick={() => moveReplay(-1)}
          >
            <SkipBack size={14} aria-hidden="true" />
          </button>
          <button
            aria-label={playing ? "Pause replay" : "Play replay"}
            className="replay-button"
            type="button"
            onClick={() => setPlaying((current) => !current)}
          >
            {playing
              ? <Pause size={13} aria-hidden="true" />
              : <Play size={13} aria-hidden="true" />}
            {playing ? "Pause" : "Replay"}
          </button>
          <button
            aria-label={`Next ${replayStep}`}
            className="icon-button"
            type="button"
            onClick={() => moveReplay(1)}
          >
            <SkipForward size={14} aria-hidden="true" />
          </button>
          <label>
            <span className="sr-only">Replay step</span>
            <select
              aria-label="Replay step"
              value={replayStep}
              onChange={(event) => setReplayStep(
                event.target.value as ReplayStep,
              )}
            >
              <option value="event">event</option>
              <option value="turn">turn</option>
              <option value="milestone">milestone</option>
            </select>
          </label>
          <span>
            {selectedIndex + 1} / {chronologicalRecords.length}
            <small>{selectedRecord?.at ?? "No retained time"}</small>
          </span>
        </div>
        <div className="saved-views" aria-label="Saved evidence views">
          {savedViews.map((view) => (
            <button
              aria-pressed={query === view.query}
              key={`${view.label}:${view.query}`}
              type="button"
              onClick={() => setQuery(
                query === view.query ? "" : view.query,
              )}
            >
              {view.label}
            </button>
          ))}
        </div>
      </div>
      <IncidentWorkflow
        runId={investigation.run.id}
        selectedRecordId={selectedRecord?.id ?? null}
        diagnosticId={
          investigation.diagnostics.find(
            (item) => item.at_record === selectedRecord?.id,
          )?.id
          ?? null
        }
        lens={lens}
        mode={sourceState}
        initialAnnotations={incident.annotations}
        sourceVersions={incident.sourceVersions}
        redactionPolicy={incident.redactionPolicy}
      />

      {lens === "story" ? (
        <StoryLens
          investigation={investigation}
          records={visibleRecords}
          throughGatewaySequence={throughGatewaySequence}
          query={query}
          selectedRecord={selectedRecord}
          selectedRoomId={selectedRoomId}
          onSelectRecord={selectRecord}
          onSelectRoom={selectRoom}
        />
      ) : null}
      {lens === "sequence" ? (
        <SequenceLens
          investigation={investigation}
          records={visibleRecords}
          query={query}
          selectedRecord={selectedRecord}
          onSelectRecord={selectRecord}
        />
      ) : null}
      {lens === "evidence" ? (
        <EvidenceLens
          investigation={investigation}
          selectedRecord={selectedRecord}
          onSelectRecord={selectRecord}
        />
      ) : null}
      {lens === "cost" ? (
        <CostLens
          investigation={investigation}
          selectedRecord={selectedRecord}
          onSelectRecord={selectRecord}
        />
      ) : null}
      {lens === "diagnostics" ? (
        <DiagnosticsLens
          investigation={investigation}
          history={incident.history ?? diagnosticHistory.history}
          historyError={sourceState === "recorded" ? diagnosticHistory.error : null}
          selectedRecord={selectedRecord}
          onSelectRecord={selectRecord}
          onOpenRun={onOpenRun}
        />
      ) : null}
    </section>
  );
}

function SessionHeader({
  investigation,
  sourceState,
  onOpenSearch,
}: {
  investigation: RecordedSessionInvestigation;
  sourceState: "recorded" | "offline";
  onOpenSearch: () => void;
}) {
  return (
    <header className="sessions-summary">
      <div>
        <span className="evidence-relationship">
          <BookMarked size={13} aria-hidden="true" />
          {sourceState === "offline"
            ? "Offline · integrity-verified incident capsule"
            : "Recorded experiment sample"}
        </span>
        <h1>
          {investigation.run.journey}
          <span>{investigation.objective ?? "Objective not retained"}</span>
        </h1>
        <p>{investigation.correlation}</p>
      </div>
      <div className="session-kpis" aria-label="Recorded session summary">
        <span>
          <small>Outcome</small>
          <b className={investigation.run.success ? "is-good" : "is-bad"}>
            {investigation.run.success ? "Verified success" : "Not satisfied"}
          </b>
        </span>
        <span>
          <small>Stop reason</small>
          <b>{investigation.run.stop_reason}</b>
        </span>
        <span>
          <small>Iterations</small>
          <b>{investigation.run.iterations}</b>
        </span>
        <span>
          <small>Cost</small>
          <b className="is-cost">${investigation.cost.total_usd.toFixed(4)}</b>
        </span>
        <span>
          <small>Evidence</small>
          <b className={investigation.capture_gaps.length > 0 ? "is-bad" : "is-good"}>
            {investigation.capture_gaps.length > 0
              ? `${investigation.capture_gaps.length} gaps`
              : "Complete"}
          </b>
        </span>
        {sourceState === "recorded" ? (
          <button className="secondary-button" type="button" onClick={onOpenSearch}>
            <MessageSquareText size={14} aria-hidden="true" />
            Ask why
          </button>
        ) : null}
      </div>
    </header>
  );
}

function StoryLens({
  investigation,
  records,
  throughGatewaySequence,
  query,
  selectedRecord,
  selectedRoomId,
  onSelectRecord,
  onSelectRoom,
}: {
  investigation: RecordedSessionInvestigation;
  records: SessionEvidenceRecord[];
  throughGatewaySequence: number;
  query: string;
  selectedRecord: SessionEvidenceRecord | null;
  selectedRoomId: string | null;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
  onSelectRoom: (roomId: string) => void;
}) {
  return (
    <div className="sessions-story">
      <SessionMap
        investigation={investigation}
        selectedRoomId={selectedRoomId}
        throughGatewaySequence={throughGatewaySequence}
        onSelectRoom={onSelectRoom}
      />
      <section className="session-sequence-card">
        <PanelTitle
          eyebrow="Synchronized run"
          title="Agent story"
          detail={`${records.length} of ${investigation.records.length} retained records`}
        />
        <SequenceTree
          records={records}
          query={query}
          selectedRecord={selectedRecord}
          compact
          onSelectRecord={onSelectRecord}
        />
      </section>
      <EvidenceDrawer
        investigation={investigation}
        selectedRecord={selectedRecord}
        onSelectRecord={onSelectRecord}
      />
    </div>
  );
}

function SequenceLens({
  investigation,
  records,
  query,
  selectedRecord,
  onSelectRecord,
}: {
  investigation: RecordedSessionInvestigation;
  records: SessionEvidenceRecord[];
  query: string;
  selectedRecord: SessionEvidenceRecord | null;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
}) {
  return (
    <div className="sessions-detail-layout">
      <section className="session-sequence-card is-full">
        <PanelTitle
          eyebrow="Causal sequence"
          title="From intent to resulting state"
          detail="Expand only the branch you need"
        />
        <SequenceTree
          records={records}
          query={query}
          selectedRecord={selectedRecord}
          onSelectRecord={onSelectRecord}
        />
      </section>
      <EvidenceDrawer
        investigation={investigation}
        selectedRecord={selectedRecord}
        onSelectRecord={onSelectRecord}
      />
    </div>
  );
}

function SessionMap({
  investigation,
  selectedRoomId,
  throughGatewaySequence,
  onSelectRoom,
}: {
  investigation: RecordedSessionInvestigation;
  selectedRoomId: string | null;
  throughGatewaySequence: number;
  onSelectRoom: (roomId: string) => void;
}) {
  return (
    <WorldExplorer
      eyebrow="Spatial lens"
      onSelectNode={onSelectRoom}
      selectedNodeId={selectedRoomId}
      throughSequence={throughGatewaySequence}
      title="Where the evidence places the agent"
      world={investigation.world}
    />
  );
}

function SequenceTree({
  records,
  query,
  selectedRecord,
  compact = false,
  onSelectRecord,
}: {
  records: SessionEvidenceRecord[];
  query: string;
  selectedRecord: SessionEvidenceRecord | null;
  compact?: boolean;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
}) {
  const matching = useMemo(
    () => new Set(
      records
        .filter((record) => matchesSessionQuery(record, query))
        .map((record) => record.id),
    ),
    [query, records],
  );
  const byParent = useMemo(() => {
    const result = new Map<string | null, SessionEvidenceRecord[]>();
    const ids = new Set(records.map((record) => record.id));
    for (const record of records) {
      const parent = record.parent_id && ids.has(record.parent_id)
        ? record.parent_id
        : null;
      const children = result.get(parent) ?? [];
      children.push(record);
      result.set(parent, children);
    }
    return result;
  }, [records]);
  const visibleBranch = (record: SessionEvidenceRecord): boolean => {
    if (matching.has(record.id)) return true;
    return (byParent.get(record.id) ?? []).some(visibleBranch);
  };
  const roots = (byParent.get(null) ?? []).filter(visibleBranch);
  const selectedPath = new Set(
    selectedRecord ? recordAncestry(records, selectedRecord).map(
      (record) => record.id,
    ) : [],
  );
  const selectedRoot = roots.find((record) => selectedPath.has(record.id));
  const limitedRoots = compact
    ? uniqueRecords([
      ...roots.slice(0, 4),
      ...(selectedRoot ? [selectedRoot] : []),
      ...roots.slice(-5),
    ])
    : roots;

  if (limitedRoots.length === 0) {
    return (
      <div className="sessions-empty">
        <Search size={20} aria-hidden="true" />
        <b>No evidence matches this filter</b>
        <span>Try source:gateway, form:wire, trace:, room:, or plain text.</span>
      </div>
    );
  }
  return (
    <div className="sequence-tree">
      {limitedRoots.map((record) => (
        <SequenceBranch
          key={record.id}
          record={record}
          children={byParent}
          selectedRecord={selectedRecord}
          selectedPath={selectedPath}
          visibleBranch={visibleBranch}
          onSelectRecord={onSelectRecord}
        />
      ))}
      {compact && roots.length > limitedRoots.length ? (
        <p className="sequence-more">
          {roots.length - limitedRoots.length} more root records are available
          in the Sequence lens.
        </p>
      ) : null}
    </div>
  );
}

function SequenceBranch({
  record,
  children,
  selectedRecord,
  selectedPath,
  visibleBranch,
  onSelectRecord,
}: {
  record: SessionEvidenceRecord;
  children: Map<string | null, SessionEvidenceRecord[]>;
  selectedRecord: SessionEvidenceRecord | null;
  selectedPath: Set<string>;
  visibleBranch: (record: SessionEvidenceRecord) => boolean;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
}) {
  const descendants = (children.get(record.id) ?? []).filter(visibleBranch);
  const onPath = selectedPath.has(record.id);
  const [open, setOpen] = useState(onPath);
  useEffect(() => {
    if (onPath) setOpen(true);
  }, [onPath]);
  const content = (
    <>
      <span className={`record-source is-${record.source}`}>
        {record.source === "agent"
          ? <Bot size={13} aria-hidden="true" />
          : record.source === "gateway"
            ? <Waypoints size={13} aria-hidden="true" />
            : <CheckCircle2 size={13} aria-hidden="true" />}
      </span>
      <span>
        <b>{record.label}</b>
        <small>
          {record.source} · {record.form}
          {record.iteration ? ` · iteration ${record.iteration}` : ""}
          {record.trace_id ? ` · trace ${record.trace_id.slice(0, 7)}` : ""}
        </small>
      </span>
      {record.cost_usd > 0 ? (
        <em>${record.cost_usd.toFixed(4)}</em>
      ) : null}
      <ChevronRight size={13} aria-hidden="true" />
    </>
  );
  if (descendants.length === 0) {
    return (
      <button
        aria-current={selectedRecord?.id === record.id ? "true" : undefined}
        className="sequence-record"
        type="button"
        onClick={() => onSelectRecord(record)}
      >
        {content}
      </button>
    );
  }
  return (
    <details
      className="sequence-branch"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary
        aria-current={selectedRecord?.id === record.id ? "true" : undefined}
        className="sequence-record"
        onClick={() => onSelectRecord(record)}
      >
        {content}
      </summary>
      {open ? <div className="sequence-children">
        {descendants.map((child) => (
          <SequenceBranch
            key={child.id}
            record={child}
            children={children}
            selectedRecord={selectedRecord}
            selectedPath={selectedPath}
            visibleBranch={visibleBranch}
            onSelectRecord={onSelectRecord}
          />
        ))}
      </div> : null}
    </details>
  );
}

function EvidenceDrawer({
  investigation,
  selectedRecord,
  onSelectRecord,
}: {
  investigation: RecordedSessionInvestigation;
  selectedRecord: SessionEvidenceRecord | null;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
}) {
  if (selectedRecord === null) {
    return (
      <aside className="session-inspector">
        <div className="sessions-empty">
          <ArrowUpRight size={20} aria-hidden="true" />
          <b>Select evidence to inspect it</b>
          <span>Every record opens source, ancestry, fields, and pivots.</span>
        </div>
      </aside>
    );
  }
  const ancestry = recordAncestry(investigation.records, selectedRecord);
  const related = investigation.records.filter((record) => (
    record.id !== selectedRecord.id
    && (
      selectedRecord.trace_id && record.trace_id === selectedRecord.trace_id
      || selectedRecord.room_id && record.room_id === selectedRecord.room_id
      || selectedRecord.turn && record.turn === selectedRecord.turn
    )
  )).slice(0, 8);
  return (
    <aside className="session-inspector" aria-label="Selected evidence detail">
      <div className="inspector-heading">
        <span className={`record-source is-${selectedRecord.source}`}>
          {selectedRecord.source}
        </span>
        <StateBadge state={
          selectedRecord.status === "failed"
            ? "attention"
            : selectedRecord.capture_gaps.length > 0
              ? "incomplete"
              : "actual"
        }>
          {selectedRecord.status}
        </StateBadge>
      </div>
      <h2>{selectedRecord.label}</h2>
      <p>{selectedRecord.preview}</p>
      <div className="evidence-ancestry" aria-label="Evidence ancestry">
        {ancestry.map((record, index) => (
          <button key={record.id} type="button" onClick={() => onSelectRecord(record)}>
            {record.label}
            {index < ancestry.length - 1
              ? <ChevronRight size={11} aria-hidden="true" />
              : null}
          </button>
        ))}
      </div>
      <dl className="evidence-metadata">
        <div><dt>Exact source</dt><dd>{selectedRecord.source_ref}</dd></div>
        <div><dt>Evidence form</dt><dd>{selectedRecord.form}</dd></div>
        <div><dt>Trace</dt><dd>{selectedRecord.trace_id ?? "Not captured"}</dd></div>
        <div><dt>Room</dt><dd>{selectedRecord.room_id ?? "Not correlated"}</dd></div>
        <div><dt>Iteration</dt><dd>{selectedRecord.iteration ?? "Not applicable"}</dd></div>
        <div><dt>Cost</dt><dd>${selectedRecord.cost_usd.toFixed(6)}</dd></div>
      </dl>
      {selectedRecord.capture_gaps.length > 0 ? (
        <div className="capture-gap">
          <AlertTriangle size={14} aria-hidden="true" />
          <span>
            {selectedRecord.capture_gaps.map((gap) => <b key={gap}>{gap}</b>)}
          </span>
        </div>
      ) : null}
      <details className="exact-fields">
        <summary>Exact sanitized fields</summary>
        <pre>{JSON.stringify(selectedRecord.fields, null, 2)}</pre>
      </details>
      {related.length > 0 ? (
        <div className="related-evidence">
          <h3>Correlated evidence</h3>
          {related.map((record) => (
            <button key={record.id} type="button" onClick={() => onSelectRecord(record)}>
              <span>{record.label}</span>
              <small>{record.source_ref}</small>
            </button>
          ))}
        </div>
      ) : (
        <div className="capture-gap">
          <AlertTriangle size={14} aria-hidden="true" />
          <span><b>No correlated record was captured</b></span>
        </div>
      )}
    </aside>
  );
}

function EvidenceLens({
  investigation,
  selectedRecord,
  onSelectRecord,
}: {
  investigation: RecordedSessionInvestigation;
  selectedRecord: SessionEvidenceRecord | null;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
}) {
  const initial = selectedRecord?.form ?? "parsed";
  const [active, setActive] = useState<SessionEvidenceForm>(initial);
  const form = investigation.lens[active];
  const cited = form.citations
    .map((id) => investigation.records.find((record) => record.id === id))
    .filter((record): record is SessionEvidenceRecord => record !== undefined);
  return (
    <div className="sessions-evidence-lens">
      <section className="evidence-comparison">
        <PanelTitle
          eyebrow="Five distinct forms"
          title="What was captured, interpreted, shown, believed, and verified"
          detail="Changing form never changes the selected evidence identity"
        />
        <div className="form-switcher" role="tablist" aria-label="Evidence forms">
          {forms.map(({ id, label, icon: Icon }) => (
            <button
              aria-selected={active === id}
              key={id}
              role="tab"
              type="button"
              onClick={() => setActive(id)}
            >
              <Icon size={15} aria-hidden="true" />
              {label}
              <span className={`availability is-${investigation.lens[id].state}`} />
            </button>
          ))}
        </div>
        <article className={`evidence-form-detail is-${active}`}>
          <StateBadge state={form.state === "available" ? "actual" : "incomplete"}>
            {form.state}
          </StateBadge>
          <h2>{form.title}</h2>
          <pre>{form.text}</pre>
          {cited.map((record) => (
            <button key={record.id} type="button" onClick={() => onSelectRecord(record)}>
              Open {record.source_ref}
              <ArrowUpRight size={13} aria-hidden="true" />
            </button>
          ))}
        </article>
      </section>
      <EvidenceDrawer
        investigation={investigation}
        selectedRecord={selectedRecord}
        onSelectRecord={onSelectRecord}
      />
    </div>
  );
}

function CostLens({
  investigation,
  selectedRecord,
  onSelectRecord,
}: {
  investigation: RecordedSessionInvestigation;
  selectedRecord: SessionEvidenceRecord | null;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
}) {
  const max = Math.max(
    ...investigation.cost.points.map((point) => point.cost_usd),
    0.000001,
  );
  return (
    <div className="sessions-cost-layout">
      <section className="cost-analysis">
        <PanelTitle
          eyebrow="Attention economics"
          title="Where the money went and what it bought"
          detail={investigation.cost.completeness_detail}
        />
        <div className="cost-total">
          <span>
            <small>Reconciled total</small>
            <b>${investigation.cost.total_usd.toFixed(6)}</b>
          </span>
          <span className="cost-raw">
            <small>Raw response fields</small>
            <b>${investigation.cost.raw_response_total_usd.toFixed(6)}</b>
          </span>
          <StateBadge state={investigation.cost.complete ? "actual" : "incomplete"}>
            {investigation.cost.complete ? "complete ledger" : "incomplete ledger"}
          </StateBadge>
        </div>
        <div className="token-composition">
          <span><b>{investigation.cost.fresh_input_tokens.toLocaleString()}</b> fresh input</span>
          <span><b>{investigation.cost.cache_read_tokens.toLocaleString()}</b> cache read</span>
          <span><b>{investigation.cost.cache_write_tokens.toLocaleString()}</b> cache write</span>
          <span><b>{investigation.cost.output_tokens.toLocaleString()}</b> output</span>
        </div>
        <div className="cost-points">
          {investigation.cost.points.map((point, index) => {
            const record = investigation.records.find(
              (candidate) => candidate.id === point.record_id,
            );
            return (
              <button
                key={point.record_id}
                type="button"
                onClick={() => {
                  if (record) onSelectRecord(record);
                }}
              >
                <span>Turn {index + 1}</span>
                <span className="cost-bar">
                  <i style={{ width: `${Math.max(3, point.cost_usd / max * 100)}%` }} />
                </span>
                <b>${point.cost_usd.toFixed(4)}</b>
                <small>
                  {point.context_tokens.toLocaleString()} context · {
                    point.pricing_source === "attempt_cost_curve"
                      ? "cache-aware curve"
                      : "raw response"
                  }
                </small>
                <em>
                  {point.progress} · raw response ${
                    point.raw_response_cost_usd.toFixed(4)
                  }
                </em>
              </button>
            );
          })}
        </div>
      </section>
      <EvidenceDrawer
        investigation={investigation}
        selectedRecord={selectedRecord}
        onSelectRecord={onSelectRecord}
      />
    </div>
  );
}

function DiagnosticsLens({
  investigation,
  history,
  historyError,
  selectedRecord,
  onSelectRecord,
  onOpenRun,
}: {
  investigation: RecordedSessionInvestigation;
  history: DiagnosticHistory;
  historyError: string | null;
  selectedRecord: SessionEvidenceRecord | null;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
  onOpenRun: (runId: string) => void;
}) {
  return (
    <div className="sessions-diagnostic-layout">
      <section className="diagnostic-analysis">
        <PanelTitle
          eyebrow="Deterministic rules"
          title="Suspicious behavior with its evidence attached"
          detail={`${investigation.diagnostic_coverage.length} rules evaluated`}
        />
        {investigation.diagnostics.length === 0 ? (
          <div className="sessions-empty">
            <CheckCircle2 size={22} aria-hidden="true" />
            <b>No diagnostic fired</b>
            <span>This does not claim the run is correct, only that no rule fired.</span>
          </div>
        ) : (
          <div className="diagnostic-list">
            {investigation.diagnostics.map((diagnostic) => (
              <DiagnosticCard
                key={diagnostic.id}
                diagnostic={diagnostic}
                investigation={investigation}
                onSelectRecord={onSelectRecord}
              />
            ))}
          </div>
        )}
        <details className="diagnostic-coverage">
          <summary>Rules that did not fire</summary>
          <div>
            {investigation.diagnostic_coverage
              .filter((kind) => !investigation.diagnostics.some(
                (diagnostic) => diagnostic.kind === kind,
              ))
              .map((kind) => <span key={kind}>{kind.replaceAll("_", " ")}</span>)}
          </div>
        </details>
        <section className="diagnostic-history">
          <PanelTitle
            eyebrow="This player across sessions"
            title="Diagnostic history"
            detail={`${history.total_runs} recorded sessions · ${history.failed_runs} unsuccessful`}
          />
          {history.items.map((item) => (
            <article key={item.kind}>
              <span>
                <strong>{item.kind.replaceAll("_", " ")}</strong>
                <small>
                  {item.runs} sessions · {item.critical} critical · {
                    item.warning
                  } warning · {item.notice} notice
                </small>
              </span>
              <div>
                {item.run_ids.map((runId) => (
                  <button
                    key={runId}
                    type="button"
                    onClick={() => onOpenRun(runId)}
                  >
                    {runId}
                  </button>
                ))}
              </div>
            </article>
          ))}
          {history.items.length === 0 ? (
            <p>
              {historyError
                ?? "No matching diagnostic is retained for this player."}
            </p>
          ) : null}
        </section>
      </section>
      <EvidenceDrawer
        investigation={investigation}
        selectedRecord={selectedRecord}
        onSelectRecord={onSelectRecord}
      />
    </div>
  );
}

function DiagnosticCard({
  diagnostic,
  investigation,
  onSelectRecord,
}: {
  diagnostic: SessionDiagnostic;
  investigation: RecordedSessionInvestigation;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
}) {
  return (
    <article className={`session-diagnostic-card is-${diagnostic.severity}`}>
      <header>
        <StateBadge state={diagnostic.severity === "critical" ? "attention" : "incomplete"}>
          {diagnostic.severity}
        </StateBadge>
        <span>{diagnostic.state} · {diagnostic.rule_version}</span>
      </header>
      <h2>{diagnostic.title}</h2>
      <p>{diagnostic.consequence}</p>
      <dl>
        <div><dt>Trigger</dt><dd>{diagnostic.threshold}</dd></div>
        <div><dt>Affects</dt><dd>{diagnostic.affected_conclusions.join(", ")}</dd></div>
        <div><dt>Alternatives</dt><dd>{diagnostic.alternatives.join(". ")}</dd></div>
        <div>
          <dt>Resolution</dt>
          <dd>{diagnostic.resolution ?? "No resolution recorded"}</dd>
        </div>
        <div>
          <dt>Related</dt>
          <dd>
            {diagnostic.related_occurrences.length > 0
              ? diagnostic.related_occurrences.join(", ")
              : "No related occurrences retained"}
          </dd>
        </div>
      </dl>
      <div className="diagnostic-evidence">
        {diagnostic.evidence.map((id) => {
          const record = investigation.records.find((candidate) => candidate.id === id);
          return record ? (
            <button key={id} type="button" onClick={() => onSelectRecord(record)}>
              {record.label}
              <ArrowUpRight size={12} aria-hidden="true" />
            </button>
          ) : (
            <span key={id}>{id} · capture gap</span>
          );
        })}
      </div>
    </article>
  );
}

function PanelTitle({
  eyebrow,
  title,
  detail,
}: {
  eyebrow: string;
  title: string;
  detail: string;
}) {
  return (
    <header className="sessions-panel-title">
      <span>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </span>
      <small>{detail}</small>
    </header>
  );
}

function uniqueRecords(
  records: SessionEvidenceRecord[],
): SessionEvidenceRecord[] {
  return [...new Map(records.map((record) => [record.id, record])).values()];
}

export function orderRecords(
  records: SessionEvidenceRecord[],
): SessionEvidenceRecord[] {
  return [...records].sort((left, right) => {
    const leftTime = Date.parse(left.at);
    const rightTime = Date.parse(right.at);
    const leftHasTime = Number.isFinite(leftTime);
    const rightHasTime = Number.isFinite(rightTime);
    if (leftHasTime && rightHasTime) {
      const timeDifference = leftTime - rightTime;
      if (timeDifference !== 0) return timeDifference;
    }
    if (leftHasTime !== rightHasTime) return leftHasTime ? -1 : 1;
    if (left.source === right.source) return left.sequence - right.sequence;
    return left.id.localeCompare(right.id);
  });
}

export function nextReplayIndex(
  records: SessionEvidenceRecord[],
  current: number,
  step: ReplayStep,
  direction: -1 | 1,
): number {
  if (records.length === 0) return 0;
  const bounded = Math.min(Math.max(current, 0), records.length - 1);
  if (step === "event") {
    return Math.min(Math.max(bounded + direction, 0), records.length - 1);
  }
  if (step === "turn") {
    const currentTurn = records[bounded]?.turn;
    let index = bounded + direction;
    while (index >= 0 && index < records.length) {
      const candidateTurn = records[index]?.turn;
      if (
        candidateTurn !== currentTurn
        && candidateTurn !== null
      ) return index;
      index += direction;
    }
    return direction > 0 ? records.length - 1 : 0;
  }
  let index = bounded + direction;
  while (index >= 0 && index < records.length) {
    if (isMilestone(records[index])) return index;
    index += direction;
  }
  return direction > 0 ? records.length - 1 : 0;
}

function isMilestone(record: SessionEvidenceRecord | undefined): boolean {
  if (!record) return false;
  return record.room_id !== null
    || record.status === "failed"
    || record.kind.includes("objective")
    || record.kind.includes("stop")
    || record.kind.includes("session_start")
    || record.kind.includes("session_end");
}
