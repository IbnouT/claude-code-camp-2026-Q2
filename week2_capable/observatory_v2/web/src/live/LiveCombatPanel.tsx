import type { LiveCombatEpisode } from "../contracts";

export function LiveCombatPanel({
  episode,
}: {
  episode: LiveCombatEpisode | null;
}) {
  if (episode?.active !== true) return null;
  return (
    <aside
      aria-label="Active combat"
      className="live-combat-panel"
      data-map-focus-occluder="true"
    >
      <span>IN COMBAT</span>
      <strong>{episode.opponent ?? "Opponent not observed"}</strong>
      <dl>
        <div>
          <dt>Since</dt>
          <dd>{episode.first_observed_turn === null
            ? "turn unknown"
            : `turn ${episode.first_observed_turn}`}</dd>
        </div>
        <div>
          <dt>Outcome</dt>
          <dd>pending</dd>
        </div>
      </dl>
    </aside>
  );
}
