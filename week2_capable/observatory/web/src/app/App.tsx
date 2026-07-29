import { useEffect, useState } from "react";
import {
  ChevronDown,
  Command,
  GitBranch,
  MapPinned,
  Radio,
  Search,
  Telescope,
} from "lucide-react";
import type { Mode } from "./types";
import { chronicle as demoChronicle } from "./demo";
import { useCapabilities } from "./useCapabilities";
import { toChronicle } from "../data/reducer";
import { useSessionStream } from "../data/useSessionStream";
import { useInvestigation } from "../data/useInvestigation";
import { useComparison } from "../data/useComparison";
import type { ChronicleEvent } from "./types";
import { BeliefReality } from "../components/BeliefReality";
import { Chronicle } from "../components/Chronicle";
import { CommandPalette } from "../components/CommandPalette";
import { DiagnosticStack } from "../components/DiagnosticStack";
import { ModeNav } from "../components/ModeNav";
import { SourceHealth } from "../components/SourceHealth";
import { WorldCanvas } from "../components/WorldCanvas";
import { EvidenceLens } from "../components/EvidenceLens";
import { InvestigationDiagnostics } from "../components/InvestigationDiagnostics";
import { InvestigationWorkspace } from "../components/InvestigationWorkspace";
import { LivingWorld } from "../components/LivingWorld";
import { CompareWorkspace } from "../components/CompareWorkspace";
import { ComparisonInsights } from "../components/ComparisonInsights";
import { ComparisonTimeline } from "../components/ComparisonTimeline";

export function App() {
  const [mode, setMode] = useState<Mode>(() => {
    const requested = new URL(window.location.href).searchParams.get("mode");
    return requested === "investigate" || requested === "compare"
      ? requested
      : "live";
  });
  const [demoSelected, setDemoSelected] = useState(82);
  const [demoPaused, setDemoPaused] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const sources = useCapabilities();
  const evidence = useSessionStream();
  const recorded = useInvestigation();
  const compared = useComparison();
  const investigation = recorded.investigation;
  const comparison = compared.comparison;
  const [investigationSelected, setInvestigationSelected] = useState(0);
  const [selectedDiagnostic, setSelectedDiagnostic] = useState<string | null>(null);
  const [activeEvidence, setActiveEvidence] = useState<string[]>([]);
  const [comparisonSelected, setComparisonSelected] = useState(() => {
    const value = Number(
      new URL(window.location.href).searchParams.get("compareAction"),
    );
    return Number.isInteger(value) && value > 0 ? value : 1;
  });
  const [investigationView, setInvestigationView] = useState<"causal" | "world">(
    () => new URL(window.location.href).searchParams.get("lens") === "world"
      ? "world"
      : "causal",
  );
  const investigating = mode === "investigate" && investigation !== null;
  const comparing = mode === "compare" && comparison !== null;
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
  const investigationChronicle: ChronicleEvent[] = investigation?.events
    .filter((event) => ["plan", "response", "tool_call", "tool_result", "turn_end"].includes(event.phase))
    .map((event) => ({
      seq: event.seq,
      label: event.label,
      kind: event.phase.startsWith("tool_") ? "tool" : "model",
      cost: event.cost_usd,
      duration: event.duration_ms,
    })) ?? [];

  useEffect(() => {
    if (investigation === null) {
      return;
    }
    const parameters = new URL(window.location.href).searchParams;
    const requestedDiagnostic = parameters.get("diagnostic");
    const diagnostic = investigation.diagnostics.find(
      (item) => item.id === requestedDiagnostic,
    ) ?? investigation.diagnostics.find(
      (item) => item.kind === "false_completion",
    ) ?? investigation.diagnostics[0];
    const requestedSequence = Number(parameters.get("iSeq"));
    setInvestigationSelected(
      Number.isInteger(requestedSequence) && requestedSequence > 0
        ? requestedSequence
        : diagnostic?.at ?? investigation.events.at(-1)?.seq ?? 0,
    );
    setSelectedDiagnostic(diagnostic?.id ?? null);
    setActiveEvidence(diagnostic?.evidence ?? []);
  }, [investigation]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("mode", mode);
    if (investigating) {
      url.searchParams.set("iSeq", String(investigationSelected));
      url.searchParams.set("lens", investigationView);
      if (selectedDiagnostic) {
        url.searchParams.set("diagnostic", selectedDiagnostic);
      }
    }
    if (comparing) {
      url.searchParams.set("compareAction", String(comparisonSelected));
    }
    window.history.replaceState(null, "", url);
  }, [
    comparing,
    comparisonSelected,
    investigating,
    investigationSelected,
    investigationView,
    mode,
    selectedDiagnostic,
  ]);

  const selectDiagnostic = (
    diagnostic: NonNullable<typeof investigation>["diagnostics"][number],
  ) => {
    setInvestigationSelected(diagnostic.at);
    setSelectedDiagnostic(diagnostic.id);
    setActiveEvidence(diagnostic.evidence);
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
          {mode === "investigate" && recorded.runs.length > 0 ? (
            <label className="session-picker recorded-picker">
              <span className="live-pulse" aria-hidden="true" />
              <span>
                <small>Recorded run</small>
                <select
                  aria-label="Recorded run"
                  value={recorded.selectedRun ?? ""}
                  onChange={(event) => recorded.selectRun(event.target.value)}
                >
                  {recorded.runs.map((run) => (
                    <option key={run.id} value={run.id}>{run.label}</option>
                  ))}
                </select>
              </span>
              <ChevronDown size={15} aria-hidden="true" />
            </label>
          ) : comparing ? (
            <div className="session-picker comparison-picker">
              <span className="mode-dot mode-full" aria-hidden="true" />
              <span>
                <small>Comparison set</small>
                {comparison.title}
              </span>
            </div>
          ) : (
            <button className="session-picker" type="button">
              <span className="live-pulse" aria-hidden="true" />
              <span>
                <small>Active session</small>
                {sessionLabel}
              </span>
              <ChevronDown size={15} aria-hidden="true" />
            </button>
          )}
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
              <span className="run-state">
                <Radio size={12} aria-hidden="true" />
                {comparing
                  ? "Reset-verified cohorts"
                  : investigating ? "Verified benchmark evidence" : runState}
              </span>
              <strong>
                {comparing
                  ? "Raw, minimal, and full · 30 successful journeys"
                  : investigating
                  ? `${investigation.run.journey} · ${investigation.run.success ? "succeeded" : "objective unmet"}`
                  : evidence.available
                  ? evidence.projection.roomTitle ?? "Reconstructing session"
                  : "Find and kill the Massive Minotaur"}
              </strong>
            </div>
            <dl>
              <div><dt>Sequence</dt><dd>
                {comparing
                  ? `action ${comparisonSelected}`
                  : investigating ? investigationSelected : selected}
              </dd></div>
              <div><dt>Position</dt><dd>
                {comparing
                  ? "Semantically aligned"
                  : investigating ? "Evidence linked" : position}
              </dd></div>
              <div><dt>Cost</dt><dd>
                {comparing
                  ? "30 measured runs"
                  : investigating
                  ? `$${investigation.run.cost_usd.toFixed(4)}`
                  : evidence.available ? `$${selectedCost.toFixed(4)}` : "$0.2109"}
              </dd></div>
              <div><dt>Outcome</dt><dd>
                {comparing
                  ? "30/30 success"
                  : investigating
                  ? investigation.run.success ? "success" : "failed"
                  : confidence}
              </dd></div>
            </dl>
          </div>
          {comparing ? (
            <CompareWorkspace
              comparison={comparison}
              selected={comparisonSelected}
              onSelect={setComparisonSelected}
            />
          ) : investigating ? (
            <div className="investigation-stage">
              <nav className="investigation-lens-nav" aria-label="Investigation lens">
                <button
                  type="button"
                  className={investigationView === "causal" ? "is-active" : ""}
                  onClick={() => setInvestigationView("causal")}
                >
                  <GitBranch size={13} aria-hidden="true" /> Causal trace
                </button>
                <button
                  type="button"
                  className={investigationView === "world" ? "is-active" : ""}
                  onClick={() => setInvestigationView("world")}
                >
                  <MapPinned size={13} aria-hidden="true" /> Living world
                </button>
              </nav>
              {investigationView === "world" ? (
                <LivingWorld world={investigation.world} />
              ) : (
                <InvestigationWorkspace
                  investigation={investigation}
                  selected={investigationSelected}
                  onSelect={(sequence) => {
                    setInvestigationSelected(sequence);
                    setActiveEvidence([]);
                  }}
                />
              )}
            </div>
          ) : (
            <WorldCanvas
              evidenceActive={evidence.available}
              roomTitle={evidence.available ? evidence.projection.roomTitle : null}
              positionTitle={evidence.available ? evidence.projection.positionTitle : null}
              positionConfidence={
                evidence.available ? evidence.projection.positionConfidence : null
              }
              throughSequence={selected}
            />
          )}
        </div>

        <aside className="insight-rail">
          {comparing ? (
            <ComparisonInsights comparison={comparison} />
          ) : investigating ? (
            <>
              <EvidenceLens
                investigation={investigation}
                activeEvidence={activeEvidence}
                onSelect={setInvestigationSelected}
              />
              <InvestigationDiagnostics
                diagnostics={investigation.diagnostics}
                selected={selectedDiagnostic}
                onSelect={selectDiagnostic}
              />
            </>
          ) : (
            <>
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
            </>
          )}
        </aside>

        {comparing ? (
          <ComparisonTimeline
            comparison={comparison}
            selected={comparisonSelected}
            onSelect={setComparisonSelected}
          />
        ) : (
          <Chronicle
            events={investigating ? investigationChronicle : chronicle}
            selected={investigating ? investigationSelected : selected}
            paused={investigating || paused}
            onSelect={investigating ? setInvestigationSelected : selectEvidence}
            onTogglePause={investigating ? () => setMode("live") : togglePause}
          />
        )}
      </main>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        runId={recorded.selectedRun}
        comparisonId={comparison?.id ?? null}
        onOpenCitation={(citation) => {
          if (citation.sequence !== null) {
            setInvestigationSelected(citation.sequence);
            setMode("investigate");
            setPaletteOpen(false);
          }
        }}
      />
    </div>
  );
}
