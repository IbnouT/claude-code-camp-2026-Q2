import { Pause, Play, Radio, SkipBack, SkipForward } from "lucide-react";
import { chronicle } from "../app/demo";

type Props = {
  selected: number;
  paused: boolean;
  onSelect: (sequence: number) => void;
  onTogglePause: () => void;
};

export function Chronicle({
  selected,
  paused,
  onSelect,
  onTogglePause,
}: Props) {
  const totalCost = chronicle.reduce((sum, event) => sum + event.cost, 0);
  const maxCost = Math.max(...chronicle.map((event) => event.cost));

  return (
    <section className="chronicle-panel" aria-labelledby="chronicle-title">
      <header className="chronicle-heading">
        <div className="chronicle-title">
          <p className="eyebrow">Causal time</p>
          <h2 id="chronicle-title">Chronicle</h2>
        </div>
        <div className="playback-controls">
          <button className="icon-button" type="button" aria-label="Previous model turn">
            <SkipBack size={15} aria-hidden="true" />
          </button>
          <button
            className="play-button"
            type="button"
            onClick={onTogglePause}
            aria-label={paused ? "Resume live clock" : "Pause live clock"}
          >
            {paused ? <Play size={15} aria-hidden="true" /> : <Pause size={15} aria-hidden="true" />}
            {paused ? "Resume" : "Pause"}
          </button>
          <button className="icon-button" type="button" aria-label="Next model turn">
            <SkipForward size={15} aria-hidden="true" />
          </button>
        </div>
        <div className="chronicle-metrics">
          <span><b>11</b> events</span>
          <span><b>${totalCost.toFixed(4)}</b> selected range</span>
          <span className={paused ? "clock-state paused" : "clock-state live"}>
            <Radio size={12} aria-hidden="true" />
            {paused ? "Paused at evidence" : "Following live"}
          </span>
        </div>
      </header>
      <div className="chronicle-track" role="list" aria-label="Causal event timeline">
        <div className="cost-baseline" aria-hidden="true" />
        {chronicle.map((event) => {
          const costHeight = event.cost === 0 ? 0 : 8 + (event.cost / maxCost) * 28;
          return (
            <button
              key={event.seq}
              type="button"
              role="listitem"
              className={
                event.seq === selected
                  ? `chronicle-event kind-${event.kind} is-selected`
                  : `chronicle-event kind-${event.kind}`
              }
              onClick={() => onSelect(event.seq)}
              aria-label={`Sequence ${event.seq}, ${event.label}`}
            >
              <span className="cost-bar" style={{ height: `${costHeight}px` }} />
              <span className="event-mark" />
              <span className="event-seq">{event.seq}</span>
              <span className="event-label">{event.label}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
