import {
  Clock3,
  Search,
  X,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import type { Session } from "../contracts";
import { sessionContextState } from "./ContextSwitcher";
import styles from "./SessionFinderDialog.module.css";

type Props = {
  open: boolean;
  selectedId: string;
  sessions: Session[];
  onClose: () => void;
  onSelect: (session: Session) => void;
};

export function SessionFinderDialog({
  open,
  selectedId,
  sessions,
  onClose,
  onSelect,
}: Props) {
  const searchInput = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");
  const results = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return sessions;
    return sessions.filter((session) => haystack(session).includes(query));
  }, [search, sessions]);

  useEffect(() => {
    if (!open) return;
    setSearch("");
    window.setTimeout(() => searchInput.current?.focus(), 0);
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className={styles.backdrop}
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        aria-label="Find a session"
        aria-modal="true"
        className={styles.dialog}
        role="dialog"
      >
        <header>
          <div>
            <strong>Find a session</strong>
            <small>{sessions.length} sessions for this player</small>
          </div>
          <button
            aria-label="Close session finder"
            type="button"
            onClick={onClose}
          >
            <X aria-hidden="true" size={18} />
          </button>
        </header>
        <label className={styles.search}>
          <Search aria-hidden="true" size={16} />
          <input
            aria-label="Search sessions"
            placeholder="Search by goal, state, date, or session id"
            ref={searchInput}
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <div className={styles.results}>
          {results.map((session) => (
            <SessionOption
              current={session.id === selectedId}
              key={session.id}
              session={session}
              onSelect={onSelect}
            />
          ))}
          {results.length === 0 ? (
            <p>No session matches “{search}”.</p>
          ) : null}
        </div>
      </section>
    </div>,
    document.body,
  );
}

function SessionOption({
  current,
  session,
  onSelect,
}: {
  current: boolean;
  session: Session;
  onSelect: (session: Session) => void;
}) {
  return (
    <button
      aria-current={current ? "true" : undefined}
      className={styles.option}
      role="menuitem"
      type="button"
      onClick={() => onSelect(session)}
    >
      <span
        aria-hidden="true"
        className={`${styles.stateDot} ${session.live ? styles.isLive : ""}`}
      />
      <span>
        <strong>{goalLabel(session)}</strong>
        <small>
          {sessionContextState(session)} · {shortId(session.id)} ·{" "}
          {when(session.updated_at)}
        </small>
      </span>
      <Clock3 aria-hidden="true" size={14} />
    </button>
  );
}

function haystack(session: Session): string {
  return [
    session.objective ?? "",
    session.state,
    sessionContextState(session),
    session.id,
    shortId(session.id),
    session.created_at,
    session.updated_at,
    when(session.created_at),
    when(session.updated_at),
  ].join(" ").toLowerCase();
}

function goalLabel(session: Session): string {
  return session.objective?.trim() || "Goal not retained";
}

function shortId(value: string): string {
  return value.length <= 8 ? value : value.slice(0, 8);
}

function when(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}
