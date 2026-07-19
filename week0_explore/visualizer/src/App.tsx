import MapView from "./map/MapView";
import Cockpit from "./cockpit/Cockpit";
import { useGameState } from "./state";
import { CombatPanel, TerminalDrawer, Toasts, useVoice } from "./overlays";

export default function App() {
  const { state, mode, lastChange, ready } = useGameState();
  const { voiceOn, toggle } = useVoice(state, ready);
  const empty = Object.keys(state.rooms).length === 0;

  return (
    <div className="flex h-full">
      <main className="relative min-w-0 flex-1">
        {empty ? (
          <div className="map-plane flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="text-4xl">🗺️</div>
            <div className="text-lg text-[var(--ink-2)]">waiting for first data…</div>
            <div className="max-w-sm text-sm text-[var(--ink-3)]">
              start a play-mud session and the map will grow here as the agent
              explores — or open <span className="font-mono">?demo=1</span> for a
              scripted session
            </div>
          </div>
        ) : (
          <MapView state={state} />
        )}
        <CombatPanel combat={state.combat} />
        <TerminalDrawer feed={state.feed} />
        <Toasts events={state.events} deaths={state.deaths} ready={ready} />
      </main>
      <Cockpit
        state={state}
        mode={mode}
        lastChange={lastChange}
        voiceOn={voiceOn}
        onToggleVoice={toggle}
      />
    </div>
  );
}
