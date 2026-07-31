import {
  ChevronRight,
  Pause,
  Play,
  SkipBack,
  SkipForward,
} from "lucide-react";
import type {
  SessionEvidenceRecord,
  SessionsLens,
} from "../../data/recordedSession";

type Props = {
  activeIterationIndex: number;
  iterationCount: number;
  playing: boolean;
  records: SessionEvidenceRecord[];
  selectedRecord: SessionEvidenceRecord | null;
  onLensChange: (lens: SessionsLens) => void;
  onMoveReplay: (direction: -1 | 1) => void;
  onPlayingChange: (playing: boolean) => void;
  onSelectRecord: (record: SessionEvidenceRecord) => void;
};

export function SessionsReplayBar({
  activeIterationIndex,
  iterationCount,
  playing,
  records,
  selectedRecord,
  onLensChange,
  onMoveReplay,
  onPlayingChange,
  onSelectRecord,
}: Props) {
  const selectedProgress = records.length === 0
    ? 0
    : Math.round(
      ((records.findIndex((record) => record.id === selectedRecord?.id) + 1)
        / records.length) * 100,
    );

  return (
    <div className="sessions-unified-replay">
      <div className="sessions-unified-replay-buttons">
        <button aria-label="First retained record" type="button" onClick={() => {
          const first = records[0];
          if (first) onSelectRecord(first);
        }}>
          <SkipBack size={15} aria-hidden="true" />
        </button>
        <button aria-label="Previous retained record" type="button" onClick={() => onMoveReplay(-1)}>
          <ChevronRight className="is-back" size={15} aria-hidden="true" />
        </button>
        <button
          aria-label={playing ? "Pause replay" : "Play replay"}
          className="is-play"
          type="button"
          onClick={() => onPlayingChange(!playing)}
        >
          {playing
            ? <Pause size={15} aria-hidden="true" />
            : <Play size={15} aria-hidden="true" />}
        </button>
        <button aria-label="Next retained record" type="button" onClick={() => onMoveReplay(1)}>
          <ChevronRight size={15} aria-hidden="true" />
        </button>
        <button aria-label="Last retained record" type="button" onClick={() => {
          const last = records.at(-1);
          if (last) onSelectRecord(last);
        }}>
          <SkipForward size={15} aria-hidden="true" />
        </button>
      </div>
      <div className="sessions-unified-scrub" aria-label={`${selectedProgress}% through retained evidence`}>
        <i style={{ width: `${selectedProgress}%` }} />
        <span style={{ left: `${selectedProgress}%` }} />
      </div>
      <div className="sessions-unified-replay-meta">
        iteration <b>{activeIterationIndex + 1}</b> / {iterationCount}
        <span>following spatial + temporal together</span>
      </div>
      <button
        className="sessions-unified-open-detail"
        type="button"
        onClick={() => onLensChange("evidence")}
      >
        Open turn detail →
      </button>
    </div>
  );
}
