import {
  ChevronDown,
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
import styles from "./SessionShell.module.css";

type Props = {
  selectedId: string;
  sessions: Session[];
  onSelect: (sessionId: string) => void;
};

export function SessionPicker({
  selectedId,
  sessions,
  onSelect,
}: Props) {
  const root = useRef<HTMLDivElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [allOpen, setAllOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selected = sessions.find((session) => session.id === selectedId)
    ?? null;
  const recent = sessions.slice(0, 5);
  const results = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return sessions;
    return sessions.filter((session) => (
      [
        session.id,
        session.state,
        session.objective ?? "",
        session.created_at,
        session.updated_at,
      ].join(" ").toLowerCase().includes(query)
    ));
  }, [search, sessions]);

  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("pointerdown", dismiss);
    return () => window.removeEventListener("pointerdown", dismiss);
  }, [open]);

  useEffect(() => {
    if (!allOpen) return;
    window.setTimeout(() => searchInput.current?.focus(), 0);
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAllOpen(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [allOpen]);

  const choose = (sessionId: string): void => {
    onSelect(sessionId);
    setOpen(false);
    setAllOpen(false);
    setSearch("");
  };

  return (
    <>
      <div className={styles.sessionPicker} ref={root}>
        <button
          aria-expanded={open}
          aria-haspopup="menu"
          aria-label="Session"
          className={styles.sessionPickerTrigger}
          type="button"
          onClick={() => setOpen((current) => !current)}
        >
          <span className={styles.sessionPickerIdentity}>
            <span
              aria-hidden="true"
              className={`${styles.sessionStateDot} ${
                selected?.live ? styles.isLive : ""
              }`}
            />
            <strong>
              {selected?.state ?? "Select session"} ·{" "}
              {selected ? shortId(selected.id) : "none"}
            </strong>
            <small>{goalLabel(selected)}</small>
          </span>
          <ChevronDown aria-hidden="true" size={16} />
        </button>

        {open ? (
          <div className={styles.sessionPickerMenu} role="menu">
            <header>
              <strong>Recent sessions</strong>
              <small>Latest five for this player</small>
            </header>
            {recent.map((session) => (
              <SessionOption
                current={session.id === selectedId}
                key={session.id}
                session={session}
                onSelect={choose}
              />
            ))}
            <button
              className={styles.showAllSessions}
              role="menuitem"
              type="button"
              onClick={() => {
                setOpen(false);
                setAllOpen(true);
              }}
            >
              <Search aria-hidden="true" size={15} />
              Show all sessions
            </button>
          </div>
        ) : null}
      </div>

      {allOpen ? createPortal(
        <div
          className={styles.sessionDialogBackdrop}
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setAllOpen(false);
          }}
        >
          <section
            aria-label="Find a session"
            aria-modal="true"
            className={styles.sessionDialog}
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
                onClick={() => setAllOpen(false)}
              >
                <X aria-hidden="true" size={18} />
              </button>
            </header>
            <label className={styles.sessionDialogSearch}>
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
            <div className={styles.sessionDialogResults}>
              {results.map((session) => (
                <SessionOption
                  current={session.id === selectedId}
                  key={session.id}
                  session={session}
                  onSelect={choose}
                />
              ))}
              {results.length === 0 ? (
                <p>No session matches “{search}”.</p>
              ) : null}
            </div>
          </section>
        </div>,
        document.body,
      ) : null}
    </>
  );
}

function SessionOption({
  current,
  session,
  onSelect,
}: {
  current: boolean;
  session: Session;
  onSelect: (sessionId: string) => void;
}) {
  return (
    <button
      aria-current={current ? "true" : undefined}
      className={styles.sessionOption}
      role="menuitem"
      type="button"
      onClick={() => onSelect(session.id)}
    >
      <span
        aria-hidden="true"
        className={`${styles.sessionStateDot} ${
          session.live ? styles.isLive : ""
        }`}
      />
      <span>
        <strong>{goalLabel(session)}</strong>
        <small>
          {session.state} · {shortId(session.id)} · {when(session.updated_at)}
        </small>
      </span>
      <Clock3 aria-hidden="true" size={14} />
    </button>
  );
}

function goalLabel(session: Session | null): string {
  return session?.objective?.trim() || "Goal not retained";
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
