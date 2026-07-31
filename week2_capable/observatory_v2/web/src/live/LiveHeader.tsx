import {
  Activity,
  BookOpen,
  FlaskConical,
  Moon,
  Search,
  Sun,
  Telescope,
} from "lucide-react";
import type { Catalog } from "../contracts";
import type { LiveRouteIdentity } from "../routes";
import type { Theme } from "../theme";
import {
  type ContextState,
  LiveContextSwitcher,
} from "./LiveContextSwitcher";

type Props = {
  identity: LiveRouteIdentity | null;
  catalog: Catalog | null;
  contextState: ContextState;
  theme: Theme;
  onAsk: () => void;
  onLeave: () => void;
  onNavigate: (href: string) => void;
  onRequestStop: () => void;
  onThemeChange: (theme: Theme) => void;
};

const spaces = [
  { label: "Live", icon: Activity, active: true },
  { label: "Sessions", icon: Telescope, active: false },
  { label: "Experiments", icon: FlaskConical, active: false },
  { label: "Knowledge", icon: BookOpen, active: false },
];

export function LiveHeader({
  identity,
  catalog,
  contextState,
  theme,
  onAsk,
  onLeave,
  onNavigate,
  onRequestStop,
  onThemeChange,
}: Props) {
  return (
    <header className="live-header">
      <a className="live-brand" href="/" aria-label="Boukensha Observatory launcher">
        <span className="live-brand-mark" aria-hidden="true">
          <Telescope size={19} />
        </span>
        <span className="live-brand-name">
          <strong>Boukensha</strong>
          <small>Observatory</small>
        </span>
      </a>

      <nav className="live-nav" aria-label="Observatory spaces">
        {spaces.map(({ active, icon: Icon, label }) => (
          <button
            aria-disabled={!active}
            aria-current={active ? "page" : undefined}
            className="live-nav-link"
            key={label}
            title={active ? undefined : `${label} will be rebuilt after Live`}
            type="button"
          >
            <Icon size={15} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="live-header-context">
        {identity !== null ? (
          <LiveContextSwitcher
            catalog={catalog}
            identity={identity}
            state={contextState}
            onLeave={onLeave}
            onNavigate={onNavigate}
            onRequestStop={onRequestStop}
          />
        ) : null}

        <button
          className="live-header-action live-ask-action"
          disabled={identity === null}
          type="button"
          onClick={onAsk}
        >
          <Search size={14} aria-hidden="true" />
          <span>Ask about this session</span>
          <kbd>⌘K</kbd>
        </button>

        <button
          aria-label={`Use ${theme === "dark" ? "light" : "dark"} theme`}
          className="live-icon-button"
          type="button"
          onClick={() => onThemeChange(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark"
            ? <Sun size={16} aria-hidden="true" />
            : <Moon size={16} aria-hidden="true" />}
        </button>
      </div>
    </header>
  );
}
