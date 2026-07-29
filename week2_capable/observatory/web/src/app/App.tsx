import { useEffect, useState } from "react";
import { ChevronDown, Command, Radio, Search, Telescope } from "lucide-react";
import type { Mode } from "./types";
import { chronicle as demoChronicle } from "./demo";
import { useCapabilities } from "./useCapabilities";
import { toChronicle } from "../data/reducer";
import { useSessionStream } from "../data/useSessionStream";
import { BeliefReality } from "../components/BeliefReality";
import { Chronicle } from "../components/Chronicle";
import { CommandPalette } from "../components/CommandPalette";
import { DiagnosticStack } from "../components/DiagnosticStack";
import { ModeNav } from "../components/ModeNav";
import { SourceHealth } from "../components/SourceHealth";
import { WorldCanvas } from "../components/WorldCanvas";

export function App() {
  const [mode, setMode] = useState<Mode>("live");
  const [demoSelected, setDemoSelected] = useState(82);
  const [demoPaused, setDemoPaused] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const sources = useCapabilities();
  const evidence = useSessionStream();
  const liveEvents = toChronicle(evidence.state.events);
  const chronicle = evidence.available ? liveEvents : demoChronicle;
  const selected = evidence.available
    ? evidence.state.selectedSeq
    : demoSelected;
  const paused = evidence.available
    ? !evidence.state.followingLive
    : demoPaused;

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
      }
      if (event.key === " " && event.target === document.body) {
        event.preventDefault();
        togglePause();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [
    evidence.available,
    evidence.state.followingLive,
    evidence.state.selectedSeq,
  ]);

  const selectEvidence = (sequence: number) => {
    if (evidence.available) {
      evidence.select(sequence);
    } else {
      setDemoSelected(sequence);
      setDemoPaused(true);
    }
    setMode("investigate");
  };

  const togglePause = () => {
    if (evidence.available) {
      if (evidence.state.followingLive) {
        evidence.select(evidence.state.selectedSeq);
      } else {
        evidence.resume();
        setMode("live");
      }
      return;
    }
    setDemoPaused((value) => !value);
  };

  const sessionLabel = evidence.available
    ? evidence.state.session
    : "J2 · Massive Minotaur";
  const runState = evidence.available ? "Gateway evidence" : "Recorded run";
  const position = evidence.available
    ? evidence.projection.positionTitle ?? "Unknown"
    : "Ambiguous";
  const confidence = evidence.available
    ? evidence.projection.positionConfidence ?? "unknown"
    : "50%";
  const selectedCost = chronicle
    .filter((event) => event.seq <= selected)
    .reduce((total, event) => total + event.cost, 0);

  return (
    <div className="observatory-shell">
      <header className="app-header">
        <a className="brand" href="/" aria-label="Boukensha Observatory home">
          <span className="brand-mark"><Telescope size={18} aria-hidden="true" /></span>
          <span>
            <strong>Boukensha</strong>
            <small>Observatory</small>
          </span>
        </a>
        <ModeNav active={mode} onChange={setMode} />
        <div className="header-actions">
          <button className="session-picker" type="button">
            <span className="live-pulse" aria-hidden="true" />
            <span>
              <small>Active session</small>
              {sessionLabel}
            </span>
            <ChevronDown size={15} aria-hidden="true" />
          </button>
          <button
            className="search-trigger"
            type="button"
            onClick={() => setPaletteOpen(true)}
          >
            <Search size={15} aria-hidden="true" />
            Ask or search
            <kbd><Command size={11} aria-hidden="true" />K</kbd>
          </button>
          <SourceHealth sources={sources} />
        </div>
      </header>

      <main className={`workspace mode-${mode}`}>
        <div className="workspace-main">
          <div className="run-strip">
            <div>
              <span className="run-state"><Radio size={12} aria-hidden="true" />{runState}</span>
              <strong>
                {evidence.available
                  ? evidence.projection.roomTitle ?? "Reconstructing session"
                  : "Find and kill the Massive Minotaur"}
              </strong>
            </div>
            <dl>
              <div><dt>Sequence</dt><dd>{selected}</dd></div>
              <div><dt>Position</dt><dd>{position}</dd></div>
              <div><dt>Cost</dt><dd>
                {evidence.available ? `$${selectedCost.toFixed(4)}` : "$0.2109"}
              </dd></div>
              <div><dt>Confidence</dt><dd>{confidence}</dd></div>
            </dl>
          </div>
          <WorldCanvas
            evidenceActive={evidence.available}
            roomTitle={evidence.available ? evidence.projection.roomTitle : null}
            positionTitle={evidence.available ? evidence.projection.positionTitle : null}
            positionConfidence={
              evidence.available ? evidence.projection.positionConfidence : null
            }
            throughSequence={selected}
          />
        </div>

        <aside className="insight-rail">
          <BeliefReality
            evidenceActive={evidence.available}
            roomTitle={evidence.available ? evidence.projection.roomTitle : null}
            roomConfidence={evidence.available ? evidence.projection.roomConfidence : null}
            parseMissRate={evidence.available ? evidence.projection.parseMissRate : null}
            evidenceCount={
              evidence.available ? evidence.projection.events.length : 4
            }
          />
          <DiagnosticStack
            onSelect={selectEvidence}
            items={evidence.available ? [] : undefined}
          />
        </aside>

        <Chronicle
          events={chronicle}
          selected={selected}
          paused={paused}
          onSelect={selectEvidence}
          onTogglePause={togglePause}
        />
      </main>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
