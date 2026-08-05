import { useEffect, useRef } from "react";
import type { LiveCombatEpisode, LiveCombatLine } from "../contracts";

function combatLineTone(line: LiveCombatLine): string {
  if (/is dead!|death cry|you receive .*experience/i.test(line.text)) {
    return "is-kill";
  }
  if (/critical|obliterate|annihilate|massacre/i.test(line.text)) {
    return "is-critical";
  }
  if (
    /hits you|slashes you|pierces you|pounds you|crushes you|rakes you|bites you|kicks you|you are dead/i
      .test(line.text)
  ) {
    return "is-incoming";
  }
  return "is-outgoing";
}

export function LiveCombatPanel({
  episode,
}: {
  episode: LiveCombatEpisode | null;
}) {
  const streamRef = useRef<HTMLDivElement>(null);
  const latestSequence = episode?.lines.at(-1)?.sequence;

  useEffect(() => {
    const stream = streamRef.current;
    if (stream !== null) {
      stream.scrollTop = stream.scrollHeight;
    }
  }, [latestSequence]);

  if (episode?.active !== true) return null;

  const lineCount = episode.lines.length;
  const since = episode.first_observed_turn === null
    ? "turn unknown"
    : `since turn ${episode.first_observed_turn}`;

  return (
    <aside
      aria-label="Active combat"
      className="live-combat-panel"
      data-map-focus-occluder="true"
    >
      <header className="live-combat-header">
        <span className="live-combat-icon" aria-hidden="true">⚔</span>
        <div>
          <strong>
            In combat{episode.opponent === null ? "" : `: ${episode.opponent}`}
          </strong>
          <small>
            {lineCount} combat {lineCount === 1 ? "event" : "events"} · {since}
          </small>
        </div>
      </header>
      <div
        ref={streamRef}
        aria-label="Combat events"
        aria-live="polite"
        className="live-combat-events"
        role="log"
      >
        {episode.lines.map((line) => (
          <span
            className={combatLineTone(line)}
            key={`${line.sequence}:${line.evidence}`}
          >
            {line.text}
          </span>
        ))}
      </div>
    </aside>
  );
}
