import {
  AlertTriangle,
  ArrowRight,
  CircleDollarSign,
  Clock3,
  Crosshair,
  Database,
  Gauge,
  Map,
  MoreHorizontal,
  Pause,
  Play,
  Radio,
  Route,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type {
  ShellCapabilities,
  Space,
  WorkspaceFixture,
} from "../../app/shellTypes";
import { EvidenceForms } from "../system/EvidenceForms";
import { StateBadge } from "../system/StateBadge";

type Props = {
  activeSpace: Space;
  capabilities: ShellCapabilities;
  fixture: WorkspaceFixture;
  onOpenControl: () => void;
  onOpenSearch: () => void;
};

const spaceCopy: Record<
  Space,
  { eyebrow: string; title: string; detail: string; askLabel: string }
> = {
  live: {
    eyebrow: "Live · representative fixture",
    title: "See the journey, then decide whether it needs attention",
    detail: "The workspace is read-only in B1. Live and replay behavior arrives in Increment 2.",
    askLabel: "Ask about this run",
  },
  sessions: {
    eyebrow: "Sessions · shell preview",
    title: "Move from outcome to cause without losing context",
    detail: "Map, sequence, cost, and evidence share one selection.",
    askLabel: "Ask this session",
  },
  experiments: {
    eyebrow: "Experiments · shell preview",
    title: "Design controlled comparisons before spending",
    detail: "Validation, execution, and comparison behavior arrives in later increments.",
    askLabel: "Search experiments",
  },
  knowledge: {
    eyebrow: "Knowledge · shell preview",
    title: "Separate what the player learned from verified truth",
    detail: "Facts, contradictions, snapshots, and history keep their provenance.",
    askLabel: "Search knowledge",
  },
};

export function InvestigationShell({
  activeSpace,
  capabilities,
  fixture,
  onOpenControl,
  onOpenSearch,
}: Props) {
  const copy = spaceCopy[activeSpace];
  const readySources = capabilities.sources.filter(
    (source) => source.state === "ready",
  ).length;
  const unavailableSource = capabilities.sources.find(
    (source) => source.state === "unavailable",
  );

  return (
    <div className="workspace">
      <section className="workspace-intro" aria-labelledby="workspace-title">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1 id="workspace-title">{copy.title}</h1>
          <p>{copy.detail}</p>
        </div>
        <div className="workspace-actions">
          <button className="secondary-button" type="button" onClick={onOpenSearch}>
            <Search size={14} aria-hidden="true" />
            {copy.askLabel}
          </button>
          <div className="workspace-status">
            <StateBadge state="actual">{fixture.runState}</StateBadge>
            {(activeSpace === "live" || activeSpace === "sessions") ? (
              <>
                <span><Clock3 size={13} aria-hidden="true" /> seq {fixture.sequence}</span>
                <span><Radio size={13} aria-hidden="true" /> {fixture.sourceAge}</span>
              </>
            ) : null}
          </div>
        </div>
      </section>

      <section className="workspace-grid">
        <section className="world-card" aria-labelledby="world-heading">
          <div className="panel-heading">
            <span>
              <p className="eyebrow">Selected journey</p>
              <h2 id="world-heading">Living world</h2>
            </span>
            <div className="segmented-control" aria-label="Map mode">
              <button aria-pressed="true" type="button">Grow</button>
              <button aria-pressed="false" type="button">Focus</button>
              <button aria-pressed="false" type="button">Lantern</button>
            </div>
          </div>

          <div className="world-stage">
            <div className="stage-toolbar">
              <button className="icon-button" type="button" aria-label="Fit journey">
                <Crosshair size={15} aria-hidden="true" />
              </button>
              <button className="icon-button" type="button" aria-label="Map options">
                <MoreHorizontal size={15} aria-hidden="true" />
              </button>
            </div>
            <svg
              aria-label="Representative journey from Market Square to the Temple"
              className="journey-map"
              role="img"
              viewBox="0 0 760 330"
            >
              <defs>
                <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                  <path className="map-grid-line" d="M 30 0 L 0 0 0 30" />
                </pattern>
              </defs>
              <rect className="map-grid" width="760" height="330" />
              <path className="journey-edge is-observed" d="M100 225 C180 225 190 165 265 165" />
              <path className="journey-edge is-observed" d="M295 165 C370 165 380 90 455 90" />
              <path className="journey-edge is-candidate" d="M485 90 C575 90 565 170 645 170" />
              <g className="room-node is-observed" transform="translate(100 225)">
                <circle r="18" />
                <text y="38">Market Square</text>
              </g>
              <g className="room-node is-observed" transform="translate(280 165)">
                <circle r="18" />
                <text y="38">Great Field</text>
              </g>
              <g className="room-node is-current" transform="translate(470 90)">
                <circle r="24" />
                <circle className="node-pulse" r="31" />
                <text y="48">Temple of Midgaard</text>
              </g>
              <g className="room-node is-candidate" transform="translate(650 170)">
                <rect x="-19" y="-19" width="38" height="38" rx="8" />
                <text y="42">Duplicate candidate</text>
              </g>
            </svg>
            <div className="map-legend" aria-label="Map legend">
              <span><i className="legend-actual" />Observed</span>
              <span><i className="legend-current" />Current</span>
              <span><i className="legend-candidate" />Candidate</span>
            </div>
          </div>

          <div className="room-summary">
            <span className="room-icon" aria-hidden="true"><Map size={17} /></span>
            <span>
              <small>Current room</small>
              <strong>{fixture.currentRoom}</strong>
            </span>
            <StateBadge state="inferred">{fixture.confidence}</StateBadge>
            <button className="text-button" type="button">
              Open evidence <ArrowRight size={13} aria-hidden="true" />
            </button>
          </div>
        </section>

        <aside className="attention-rail" aria-label="Run context and attention">
          <section className="attention-card">
            <div className="panel-heading">
              <span>
                <p className="eyebrow">Objective</p>
                <h2>{fixture.objective}</h2>
              </span>
              <Route size={17} aria-hidden="true" />
            </div>
            <div className="belief-block">
              <StateBadge state="believed">Agent belief</StateBadge>
              <p>The target is likely beyond the newbie-zone entrance.</p>
            </div>
            <div className="belief-block">
              <StateBadge state="actual">Observed</StateBadge>
              <p>The entrance was found. No target observation is captured yet.</p>
            </div>
            {activeSpace === "live" ? (
              <button className="primary-button full-width" type="button" onClick={onOpenControl}>
                Direct the agent <ArrowRight size={14} aria-hidden="true" />
              </button>
            ) : null}
          </section>

          <section className="attention-card diagnostic-card">
            <div className="diagnostic-icon" aria-hidden="true">
              <AlertTriangle size={17} />
            </div>
            <div>
              <p className="eyebrow">Needs attention</p>
              <h2>{fixture.diagnostic.title}</h2>
              <p>{fixture.diagnostic.detail}</p>
              <button className="text-button" type="button">
                Investigate evidence <ArrowRight size={13} aria-hidden="true" />
              </button>
            </div>
          </section>

          <section className="metrics-card" aria-label="Live economics">
            <div>
              <CircleDollarSign size={15} aria-hidden="true" />
              <span><small>Cost</small><strong>{fixture.cost}</strong></span>
            </div>
            <div>
              <Gauge size={15} aria-hidden="true" />
              <span><small>Spend cap</small><strong>{fixture.spendCap}</strong></span>
            </div>
            <div>
              <Database size={15} aria-hidden="true" />
              <span><small>Tokens</small><strong>{fixture.tokens}</strong></span>
            </div>
          </section>

          <section className="source-card">
            <ShieldCheck size={17} aria-hidden="true" />
            <span>
              <small>
                {unavailableSource ? "Instrumentation issue" : "Instrumentation completeness"}
              </small>
              <strong>
                {unavailableSource?.detail
                  ?? `${readySources}/${capabilities.sources.length} sources ready`}
              </strong>
            </span>
            <StateBadge state="incomplete">Incomplete</StateBadge>
          </section>
        </aside>

        <section className="timeline-card" aria-labelledby="timeline-heading">
          <div className="panel-heading">
            <span>
              <p className="eyebrow">Causal time</p>
              <h2 id="timeline-heading">Activity</h2>
            </span>
            {(activeSpace === "live" || activeSpace === "sessions") ? (
              <div className="timeline-controls">
                <button className="icon-button" type="button" aria-label="Pause replay">
                  <Pause size={14} aria-hidden="true" />
                </button>
                <button className="icon-button" type="button" aria-label="Return to live">
                  <Play size={14} aria-hidden="true" />
                </button>
              </div>
            ) : null}
          </div>
          <ol className="timeline-list">
            {fixture.timeline.map((item) => (
              <li className={`timeline-item item-${item.kind}`} key={item.id}>
                <span className="timeline-symbol" aria-hidden="true" />
                <time>{item.time}</time>
                <span className="timeline-label">{item.label}</span>
                <code>#{item.sequence}</code>
                <span className="timeline-cost">{item.cost}</span>
              </li>
            ))}
          </ol>
        </section>

        <EvidenceForms evidence={fixture.evidence} />
      </section>

      <footer className="workspace-footer">
        <span><Sparkles size={13} aria-hidden="true" /> Representative fixture</span>
        <span>Read-only shell · no gameplay or model call</span>
      </footer>
    </div>
  );
}
