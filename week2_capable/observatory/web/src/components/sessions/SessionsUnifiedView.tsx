import type {
  RecordedSessionInvestigation,
  SessionEvidenceRecord,
  SessionsLens,
} from "../../data/recordedSession";
import "../../styles/sessions-unified.css";
import { SessionsMapLens } from "./SessionsMapLens";
import { SessionsReplayBar } from "./SessionsReplayBar";
import { SessionsSequenceLens } from "./SessionsSequenceLens";
import { SessionsUnifiedHeader } from "./SessionsUnifiedHeader";
import {
  effectiveSelectedRoom,
  groupSessionIterations,
} from "./sessionsUnifiedModel";

type Props = {
  investigation: RecordedSessionInvestigation;
  records: SessionEvidenceRecord[];
  selectedRecord: SessionEvidenceRecord | null;
  selectedRoomId: string | null;
  playing: boolean;
  onPlayingChange: (playing: boolean) => void;
  onLensChange: (lens: SessionsLens) => void;
  onMoveReplay: (direction: -1 | 1) => void;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
  onSelectRoom: (roomId: string) => void;
};

export function SessionsUnifiedView({
  investigation,
  records,
  selectedRecord,
  selectedRoomId,
  playing,
  onPlayingChange,
  onLensChange,
  onMoveReplay,
  onSelectRecord,
  onSelectRoom,
}: Props) {
  const iterations = groupSessionIterations(records);
  const selectedIteration = selectedRecord?.iteration
    ?? iterations.find((item) => item.records.length > 0)?.iteration
    ?? 1;
  const selectedTurn = selectedRecord?.turn ?? "unknown";
  const effectiveRoomId = effectiveSelectedRoom(
    records,
    selectedRoomId,
    selectedRecord?.id ?? null,
  );
  const selectedRoom = investigation.world.nodes.find(
    (node) => node.id === effectiveRoomId,
  );
  const selectedLabel = selectedRoom?.title
    ?? selectedRecord?.label
    ?? "No retained selection";
  const activeIterationIndex = Math.max(
    0,
    iterations.findIndex((item) => item.iteration === selectedIteration),
  );

  return (
    <section className="sessions-unified" aria-label="Recorded session investigation">
      <SessionsUnifiedHeader
        investigation={investigation}
        records={records}
        selectedIteration={selectedIteration}
        selectedTurn={selectedTurn}
        selectedLabel={selectedLabel}
        onLensChange={onLensChange}
      />
      <div className="sessions-unified-body">
        <SessionsMapLens
          investigation={investigation}
          selectedRoomId={effectiveRoomId}
          onSelectRoom={onSelectRoom}
        />
        <SessionsSequenceLens
          investigation={investigation}
          iterations={iterations}
          selectedIteration={selectedIteration}
          selectedRecord={selectedRecord}
          onSelectRecord={onSelectRecord}
        />
      </div>
      <SessionsReplayBar
        activeIterationIndex={activeIterationIndex}
        iterationCount={iterations.length}
        playing={playing}
        records={records}
        selectedRecord={selectedRecord}
        onLensChange={onLensChange}
        onMoveReplay={onMoveReplay}
        onPlayingChange={onPlayingChange}
        onSelectRecord={onSelectRecord}
      />
    </section>
  );
}
