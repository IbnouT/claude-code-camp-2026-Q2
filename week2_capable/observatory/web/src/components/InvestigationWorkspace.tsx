import {
  Braces,
  ChevronRight,
  CircleDollarSign,
  Search,
  Sparkles,
  Waypoints,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  matchesInvestigationQuery,
  type Investigation,
} from "../data/investigation";

type Props = {
  investigation: Investigation;
  selected: number;
  onSelect: (sequence: number) => void;
};

const savedViews = [
  { label: "Model claims", query: "phase:response" },
  { label: "Movement", query: "tool:move" },
  { label: "Tool failures", query: "phase:tool_result" },
];

const phaseIcon = {
  plan: Sparkles,
  response: Braces,
  tool_call: Waypoints,
  tool_result: ChevronRight,
  turn_end: CircleDollarSign,
};

export function InvestigationWorkspace({
  investigation,
  selected,
  onSelect,
}: Props) {
  const [query, setQuery] = useState(
    () => new URL(window.location.href).searchParams.get("q") ?? "",
  );
  const listRef = useRef<HTMLDivElement | null>(null);
  const selectedRef = useRef<HTMLButtonElement | null>(null);
  const visible = useMemo(
    () => investigation.events.filter((event) => matchesInvestigationQuery(event, query)),
    [investigation.events, query],
  );
  const selectedEvent = investigation.events.find((event) => event.seq === selected)
    ?? investigation.events.at(-1);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (query) {
      url.searchParams.set("q", query);
    } else {
      url.searchParams.delete("q");
    }
    window.history.replaceState(null, "", url);
  }, [query]);

  useEffect(() => {
    if (listRef.current !== null && selectedRef.current !== null) {
      listRef.current.scrollTop = Math.max(
        0,
        selectedRef.current.offsetTop - listRef.current.clientHeight / 2,
      );
    }
  }, [selected]);

  return (
    <section className="investigation-workspace" aria-labelledby="causal-title">
      <header className="investigation-toolbar">
        <div>
          <p className="eyebrow">Causal investigation</p>
          <h2 id="causal-title">Claim to consequence</h2>
        </div>
        <label className="evidence-search">
          <Search size={14} aria-hidden="true" />
          <span className="sr-only">Search causal evidence</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="phase:response tool:move"
          />
        </label>
      </header>

      <div className="saved-views" aria-label="Saved investigation views">
        {savedViews.map((view) => (
          <button
            key={view.query}
            type="button"
            className={query === view.query ? "is-active" : ""}
            onClick={() => setQuery(view.query)}
          >
            {view.label}
          </button>
        ))}
        {query && (
          <button type="button" onClick={() => setQuery("")}>
            Clear · {visible.length} matches
          </button>
        )}
      </div>

      <div className="causal-surface">
        <div
          ref={listRef}
          className="causal-waterfall"
          role="list"
          aria-label="Causal event waterfall"
        >
          {visible.slice(-120).map((event) => {
            const Icon = phaseIcon[event.phase as keyof typeof phaseIcon] ?? ChevronRight;
            const iteration = event.attributes.iteration;
            return (
              <button
                key={event.seq}
                ref={event.seq === selected ? selectedRef : undefined}
                type="button"
                role="listitem"
                className={
                  event.seq === selected
                    ? `causal-row phase-${event.phase} is-selected`
                    : `causal-row phase-${event.phase}`
                }
                onClick={() => onSelect(event.seq)}
              >
                <span className="causal-spine" aria-hidden="true" />
                <span className="causal-icon"><Icon size={13} aria-hidden="true" /></span>
                <span className="causal-copy">
                  <strong>{event.label}</strong>
                  <small>
                    {iteration ? `turn ${String(iteration)}` : event.phase}
                    {event.attributes.tool ? ` · ${String(event.attributes.tool)}` : ""}
                  </small>
                </span>
                <span className="causal-cost">
                  {event.cost_usd > 0 ? `$${event.cost_usd.toFixed(4)}` : "evidence"}
                </span>
              </button>
            );
          })}
        </div>

        <article className="causal-inspector">
          <p className="eyebrow">Selected causal node</p>
          <h3>{selectedEvent?.label ?? "No event selected"}</h3>
          <dl>
            <div><dt>Sequence</dt><dd>{selectedEvent?.seq ?? 0}</dd></div>
            <div><dt>Phase</dt><dd>{selectedEvent?.phase ?? "unknown"}</dd></div>
            <div><dt>Parent</dt><dd>{selectedEvent?.parent ?? "root"}</dd></div>
            <div>
              <dt>Trace</dt>
              <dd>{selectedEvent?.citation ?? "No citation"}</dd>
            </div>
          </dl>
          <p>
            The waterfall keeps model intent, tool action, result, cost, and
            evidence separate while preserving their causal order.
          </p>
        </article>
      </div>
    </section>
  );
}
