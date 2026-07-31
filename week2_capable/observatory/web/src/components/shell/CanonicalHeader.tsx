import {
  Activity,
  BookOpen,
  ChevronDown,
  CircleStop,
  Download,
  DoorOpen,
  FlaskConical,
  Moon,
  Sun,
  Telescope,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
} from "react";
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
  canStopSession: boolean;
  onLeaveLive: () => void;
  onPlayerChange: (player: string) => void;
  onRequestStop: () => void;
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
  canStopSession,
  onLeaveLive,
  onPlayerChange,
  onRequestStop,
  onSessionChange,
  onSpaceChange,
  onThemeChange,
  onLoadEvidence,
}: Props) {
  const evidenceInput = useRef<HTMLInputElement>(null);
  const sessionMenu = useRef<HTMLDivElement>(null);
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const sessionApplies = activeSpace === "live" || activeSpace === "sessions";
  const loadApplies = activeSpace === "sessions" || activeSpace === "live";
  const selectedSessionLabel = sessions.find(
    (session) => session.id === selectedSession,
  )?.label ?? sessions[0]?.label ?? "No sessions";

  useEffect(() => {
    if (!sessionMenuOpen) return;
    const close = (event: KeyboardEvent | PointerEvent) => {
      if (event instanceof KeyboardEvent && event.key === "Escape") {
        setSessionMenuOpen(false);
        return;
      }
      if (
        event instanceof PointerEvent
        && !sessionMenu.current?.contains(event.target as Node)
      ) {
        setSessionMenuOpen(false);
      }
    };
    window.addEventListener("keydown", close);
    window.addEventListener("pointerdown", close);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("pointerdown", close);
    };
  }, [sessionMenuOpen]);

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
          <small>Player</small>
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
          <div className="session-context" ref={sessionMenu}>
            <button
              aria-expanded={sessionMenuOpen}
              aria-haspopup="menu"
              aria-label="Session"
              className="context-select session-select session-menu-trigger"
              type="button"
              onClick={() => setSessionMenuOpen((open) => !open)}
            >
              <small>Session</small>
              <span>{selectedSessionLabel}</span>
              <ChevronDown size={13} aria-hidden="true" />
            </button>
            {sessionMenuOpen ? (
              <div
                aria-label="Session menu"
                className="session-menu"
                role="menu"
              >
                {sessions.map((session) => (
                  <button
                    aria-current={
                      session.id === selectedSession ? "true" : undefined
                    }
                    disabled={!session.id}
                    key={session.id || "empty"}
                    role="menuitem"
                    type="button"
                    onClick={() => {
                      onSessionChange(session.id);
                      setSessionMenuOpen(false);
                    }}
                  >
                    <strong>{session.label}</strong>
                    <small>{session.detail}</small>
                  </button>
                ))}
                {activeSpace === "live" ? (
                  <>
                    <div className="session-menu-separator" />
                    <button
                      role="menuitem"
                      type="button"
                      onClick={() => {
                        setSessionMenuOpen(false);
                        onLeaveLive();
                      }}
                    >
                      <DoorOpen size={14} aria-hidden="true" />
                      <span>
                        <strong>Leave Live view</strong>
                        <small>The agent keeps running</small>
                      </span>
                    </button>
                    {canStopSession ? (
                      <button
                        className="session-stop-action"
                        role="menuitem"
                        type="button"
                        onClick={() => {
                          setSessionMenuOpen(false);
                          onRequestStop();
                        }}
                      >
                        <CircleStop size={14} aria-hidden="true" />
                        <span>
                          <strong>Stop session…</strong>
                          <small>End the agent and game connection</small>
                        </span>
                      </button>
                    ) : null}
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
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
