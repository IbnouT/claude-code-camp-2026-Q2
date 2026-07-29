import { useEffect, useState } from "react";
import { ChevronDown, Command, Radio, Search, Telescope } from "lucide-react";
import type { Mode } from "./types";
import { useCapabilities } from "./useCapabilities";
import { BeliefReality } from "../components/BeliefReality";
import { Chronicle } from "../components/Chronicle";
import { CommandPalette } from "../components/CommandPalette";
import { DiagnosticStack } from "../components/DiagnosticStack";
import { ModeNav } from "../components/ModeNav";
import { SourceHealth } from "../components/SourceHealth";
import { WorldCanvas } from "../components/WorldCanvas";

export function App() {
  const [mode, setMode] = useState<Mode>("live");
  const [selected, setSelected] = useState(82);
  const [paused, setPaused] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const sources = useCapabilities();

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
        setPaused((value) => !value);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  const selectEvidence = (sequence: number) => {
    setSelected(sequence);
    setPaused(true);
    setMode("investigate");
  };

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
              J2 · Massive Minotaur
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
              <span className="run-state"><Radio size={12} aria-hidden="true" />Recorded run</span>
              <strong>Find and kill the Massive Minotaur</strong>
            </div>
            <dl>
              <div><dt>Turn</dt><dd>90</dd></div>
              <div><dt>Position</dt><dd>Ambiguous</dd></div>
              <div><dt>Cost</dt><dd>$0.2109</dd></div>
              <div><dt>Confidence</dt><dd>50%</dd></div>
            </dl>
          </div>
          <WorldCanvas />
        </div>

        <aside className="insight-rail">
          <BeliefReality />
          <DiagnosticStack onSelect={selectEvidence} />
        </aside>

        <Chronicle
          selected={selected}
          paused={paused}
          onSelect={selectEvidence}
          onTogglePause={() => setPaused((value) => !value)}
        />
      </main>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
