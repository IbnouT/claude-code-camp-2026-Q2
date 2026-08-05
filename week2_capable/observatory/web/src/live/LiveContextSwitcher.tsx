import {
  ChevronDown,
  CircleStop,
  DoorOpen,
  ExternalLink,
  Radio,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  Catalog,
  Session,
} from "../contracts";
import {
  liveHref,
  recordedSessionHref,
  sessionsHref,
} from "../routes";
import type { LiveRouteIdentity } from "../routes";

export type ContextState =
  | "checking"
  | "running"
  | "draining"
  | "stopped"
  | "ended"
  | "reconnecting";

type Props = {
  catalog: Catalog | null;
  identity: LiveRouteIdentity;
  state: ContextState;
  onLeave: () => void;
  onNavigate: (href: string) => void;
  onRequestStop: () => void;
};

function shortSession(sessionId: string): string {
  return sessionId.length > 12 ? sessionId.slice(0, 8) : sessionId;
}

function sessionState(session: Session): ContextState {
  if (session.state === "draining") return "draining";
  if (session.state === "stopped") return "stopped";
  if (session.live) return "running";
  return "ended";
}

function when(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function ordered(sessions: Session[]): Session[] {
  return [...sessions].sort((left, right) => {
    if (left.live !== right.live) return left.live ? -1 : 1;
    return Date.parse(right.updated_at) - Date.parse(left.updated_at);
  });
}

function destination(session: Session): string {
  return session.live
    ? liveHref({
      playerId: session.player_id,
      sessionId: session.id,
    })
    : recordedSessionHref(session);
}

function SessionRow({
  session,
  onNavigate,
}: {
  session: Session;
  onNavigate: (href: string) => void;
}) {
  const state = sessionState(session);
  return (
    <button
      aria-label={[
        state,
        shortSession(session.id),
        when(session.updated_at),
        `${session.event_count.toLocaleString()} events`,
      ].join(", ")}
      className="live-context-row"
      data-context-item
      role="button"
      type="button"
      onClick={() => onNavigate(destination(session))}
    >
      <span className={`live-context-row-state is-${state}`}>
        {session.live ? <Radio size={12} aria-hidden="true" /> : null}
        {state}
      </span>
      <span className="live-context-row-main">
        <strong>{shortSession(session.id)}</strong>
        <small>{when(session.updated_at)}</small>
      </span>
      <span className="live-context-row-meta">
        {session.event_count.toLocaleString()} events
      </span>
    </button>
  );
}

export function LiveContextSwitcher({
  catalog,
  identity,
  state,
  onLeave,
  onNavigate,
  onRequestStop,
}: Props) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const typeahead = useRef("");
  const typeaheadTimer = useRef<number | null>(null);
  const [open, setOpen] = useState(false);

  const current = catalog?.sessions.find(
    (session) => session.id === identity.sessionId
      && session.player_id === identity.playerId,
  ) ?? null;
  const currentPlayerSessions = useMemo(
    () => ordered(
      (catalog?.sessions ?? []).filter(
        (session) => session.player_id === identity.playerId,
      ),
    ),
    [catalog, identity.playerId],
  );
  const recent = currentPlayerSessions
    .filter((session) => session.id !== identity.sessionId)
    .slice(0, 5);
  const otherPlayers = useMemo(() => {
    const rows = (catalog?.players ?? [])
      .filter((player) => player.id !== identity.playerId)
      .map((player) => ({
        player,
        session: ordered(
          (catalog?.sessions ?? []).filter(
            (session) => session.player_id === player.id,
          ),
        )[0] ?? null,
      }))
      .filter(
        (row): row is {
          player: { id: string; label: string };
          session: Session;
        } => row.session !== null,
      );
    return rows;
  }, [catalog, identity.playerId]);

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) {
      window.setTimeout(() => trigger.current?.focus(), 0);
    }
  };

  useEffect(() => {
    if (!open) return;
    window.setTimeout(() => {
      root.current
        ?.querySelector<HTMLButtonElement>("[data-context-item]")
        ?.focus();
    }, 0);
    const dismiss = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", dismiss);
    return () => window.removeEventListener("pointerdown", dismiss);
  }, [open]);

  useEffect(() => () => {
    if (typeaheadTimer.current !== null) {
      window.clearTimeout(typeaheadTimer.current);
    }
  }, []);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(
      root.current?.querySelectorAll<HTMLButtonElement>(
        "[data-context-item]",
      ) ?? [],
    );
    const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const offset = event.key === "ArrowDown" ? 1 : -1;
      const next = currentIndex < 0
        ? 0
        : (currentIndex + offset + items.length) % items.length;
      items[next]?.focus();
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      items[event.key === "Home" ? 0 : items.length - 1]?.focus();
      return;
    }
    if (
      event.key.length === 1
      && !event.altKey
      && !event.ctrlKey
      && !event.metaKey
    ) {
      typeahead.current += event.key.toLowerCase();
      if (typeaheadTimer.current !== null) {
        window.clearTimeout(typeaheadTimer.current);
      }
      typeaheadTimer.current = window.setTimeout(() => {
        typeahead.current = "";
      }, 600);
      const match = items.find((item) => (
        item.textContent?.trim().toLowerCase().startsWith(typeahead.current)
      ));
      if (match) {
        event.preventDefault();
        match.focus();
      }
    }
  };

  const contextPlayer = current?.character || identity.playerId;
  const canStop = state === "running";

  return (
    <div className="live-context-switcher" ref={root}>
      <button
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={[
          "View context",
          contextPlayer,
          state,
          shortSession(identity.sessionId),
        ].join(", ")}
        className="live-context live-context-trigger"
        ref={trigger}
        type="button"
        onClick={() => setOpen((value) => !value)}
      >
        <strong>{contextPlayer}</strong>
        <span aria-hidden="true">·</span>
        {state === "running" ? (
          <span className="live-connection-dot" aria-hidden="true" />
        ) : null}
        <span className={`live-context-state is-${state}`}>{state}</span>
        <span aria-hidden="true">·</span>
        <span className="live-context-id">{shortSession(identity.sessionId)}</span>
        <ChevronDown size={13} aria-hidden="true" />
      </button>

      {open ? (
        <div
          aria-label="View context"
          className="live-context-panel"
          role="dialog"
          onKeyDown={handleKeyDown}
        >
          <section className="live-context-current">
            <p className="live-context-heading">Current</p>
            <div className="live-context-current-id">
              <span>
                <strong>{contextPlayer}</strong>
                <small>{identity.sessionId}</small>
              </span>
              <span className={`live-context-state is-${state}`}>{state}</span>
            </div>
            <div className="live-context-current-actions">
              <button
                data-context-item
                type="button"
                onClick={() => {
                  close(false);
                  onLeave();
                }}
              >
                <DoorOpen size={14} aria-hidden="true" />
                Leave Live view
              </button>
              {canStop ? (
                <button
                  className="live-stop-action"
                  data-context-item
                  type="button"
                  onClick={() => {
                    close(false);
                    onRequestStop();
                  }}
                >
                  <CircleStop size={14} aria-hidden="true" />
                  Stop session…
                </button>
              ) : null}
              {current !== null && !current.live ? (
                <button
                  data-context-item
                  type="button"
                  onClick={() => onNavigate(recordedSessionHref(current))}
                >
                  <ExternalLink size={14} aria-hidden="true" />
                  View recording
                </button>
              ) : null}
            </div>
          </section>

          {recent.length > 0 ? (
            <section className="live-context-group">
              <p className="live-context-heading">
                Recent {contextPlayer} sessions
              </p>
              {recent.map((session) => (
                <SessionRow
                  key={session.id}
                  session={session}
                  onNavigate={onNavigate}
                />
              ))}
            </section>
          ) : null}

          {currentPlayerSessions.length > 0 ? (
            <button
              className="live-context-wide-link"
              data-context-item
              type="button"
              onClick={() => onNavigate(sessionsHref(identity.playerId))}
            >
              View all {contextPlayer} sessions ({currentPlayerSessions.length})
              <ExternalLink size={13} aria-hidden="true" />
            </button>
          ) : null}

          {otherPlayers.length > 0 ? (
            <section className="live-context-group">
              <p className="live-context-heading">Other players</p>
              {otherPlayers.map(({ player, session }) => (
                <button
                  aria-label={[
                    player.label,
                    session.live ? sessionState(session) : when(session.updated_at),
                    `${session.event_count.toLocaleString()} events`,
                  ].join(", ")}
                  className="live-context-player-row"
                  data-context-item
                  key={player.id}
                  type="button"
                  onClick={() => onNavigate(destination(session))}
                >
                  <span>
                    <strong>{player.label}</strong>
                    <small>
                      {session.live ? sessionState(session) : when(session.updated_at)}
                    </small>
                  </span>
                  <span>{session.event_count.toLocaleString()} events</span>
                </button>
              ))}
            </section>
          ) : null}

          <button
            className="live-context-footer"
            data-context-item
            type="button"
            onClick={() => onNavigate(sessionsHref())}
          >
            All sessions &amp; players
            <ExternalLink size={13} aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </div>
  );
}
