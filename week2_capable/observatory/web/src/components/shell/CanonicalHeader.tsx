import {
  Activity,
  BookOpen,
  ChevronDown,
  Download,
  FlaskConical,
  Moon,
  Sun,
  Telescope,
  Users,
} from "lucide-react";
import { useRef } from "react";
import type {
  SelectorOption,
  Space,
  Theme,
} from "../../app/shellTypes";

type Props = {
  activeSpace: Space;
  players: SelectorOption[];
  selectedPlayer: string;
  selectedSession: string;
  sessions: SelectorOption[];
  theme: Theme;
  onPlayerChange: (player: string) => void;
  onSessionChange: (session: string) => void;
  onSpaceChange: (space: Space) => void;
  onThemeChange: (theme: Theme) => void;
  onLoadEvidence: (file: File) => void;
};

const spaces: {
  id: Space;
  label: string;
  icon: typeof Activity;
}[] = [
  { id: "live", label: "Live", icon: Activity },
  { id: "sessions", label: "Sessions", icon: Telescope },
  { id: "experiments", label: "Experiments", icon: FlaskConical },
  { id: "knowledge", label: "Knowledge", icon: BookOpen },
];

export function CanonicalHeader({
  activeSpace,
  players,
  selectedPlayer,
  selectedSession,
  sessions,
  theme,
  onPlayerChange,
  onSessionChange,
  onSpaceChange,
  onThemeChange,
  onLoadEvidence,
}: Props) {
  const evidenceInput = useRef<HTMLInputElement>(null);
  const sessionApplies = activeSpace === "live" || activeSpace === "sessions";
  const loadApplies = activeSpace === "sessions";

  return (
    <header className="canonical-header">
      <a className="brand" href="/?space=live" aria-label="Boukensha Observatory home">
        <span className="brand-mark" aria-hidden="true">
          <Telescope size={19} />
        </span>
        <span className="brand-name">
          <strong>Boukensha</strong>
          <small>Observatory</small>
        </span>
      </a>

      <nav className="space-nav" aria-label="Observatory spaces">
        {spaces.map(({ id, icon: Icon, label }) => (
          <button
            aria-current={activeSpace === id ? "page" : undefined}
            className="space-link"
            key={id}
            type="button"
            onClick={() => onSpaceChange(id)}
          >
            <Icon size={15} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="header-context">
        <label className="context-select">
          <Users size={14} aria-hidden="true" />
          <span className="sr-only">Player</span>
          <select
            aria-label="Player"
            value={selectedPlayer}
            onChange={(event) => onPlayerChange(event.target.value)}
          >
            {players.map((player) => (
              <option key={player.id} value={player.id}>
                {player.label}
              </option>
            ))}
          </select>
          <ChevronDown size={13} aria-hidden="true" />
        </label>

        {sessionApplies ? (
          <label className="context-select session-select">
            <span className="connection-dot" aria-hidden="true" />
            <span className="sr-only">Session</span>
            <select
              aria-label="Session"
              value={selectedSession}
              onChange={(event) => onSessionChange(event.target.value)}
            >
              {sessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.label}
                </option>
              ))}
            </select>
            <ChevronDown size={13} aria-hidden="true" />
          </label>
        ) : null}

        {loadApplies ? (
          <>
            <input
              accept=".json,application/json,application/vnd.boukensha.incident+json"
              aria-label="Incident capsule file"
              className="sr-only"
              ref={evidenceInput}
              type="file"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) onLoadEvidence(file);
                event.target.value = "";
              }}
            />
            <button
              aria-label="Load recorded evidence"
              className="header-action"
              title="Open a sanitized incident capsule without live services"
              type="button"
              onClick={() => evidenceInput.current?.click()}
            >
              <Download size={14} aria-hidden="true" />
              <span>Load…</span>
            </button>
          </>
        ) : null}

        <button
          className="icon-button"
          type="button"
          aria-label={`Use ${theme === "dark" ? "light" : "dark"} theme`}
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
