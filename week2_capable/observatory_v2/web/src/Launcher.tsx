import { useEffect, useMemo, useState } from "react";
import {
  decodeSnapshot,
  type Catalog,
  type Observed,
  type Player,
  type Session,
  type Snapshot,
} from "./contracts";
import { lifecycleApiUrl } from "./lifecycleApi";
import { liveHref } from "./routes";

type PlayerRow = Player & { sessions: Session[]; latest: Session | null };
type BackdropNode = { id: string; x: number; y: number; emphasis?: boolean };
type StartResponse = {
  session_id: string;
  player_id: string;
  reset: "none" | "temple" | "baseline";
  state: "running";
};
type StartError = {
  error?: string;
  detail?: string;
};

const backdropNodes: BackdropNode[] = [
  { id: "a", x: 110, y: 105 },
  { id: "b", x: 235, y: 72 },
  { id: "c", x: 355, y: 125, emphasis: true },
  { id: "d", x: 485, y: 80 },
  { id: "e", x: 615, y: 130 },
  { id: "f", x: 755, y: 68 },
  { id: "g", x: 900, y: 115, emphasis: true },
  { id: "h", x: 1065, y: 82 },
  { id: "i", x: 175, y: 235 },
  { id: "j", x: 305, y: 265 },
  { id: "k", x: 435, y: 210 },
  { id: "l", x: 565, y: 270, emphasis: true },
  { id: "m", x: 705, y: 215 },
  { id: "n", x: 850, y: 270 },
  { id: "o", x: 995, y: 220 },
  { id: "p", x: 1120, y: 285 },
  { id: "q", x: 105, y: 395 },
  { id: "r", x: 255, y: 365 },
  { id: "s", x: 395, y: 425 },
  { id: "t", x: 535, y: 365 },
  { id: "u", x: 675, y: 430 },
  { id: "v", x: 825, y: 375, emphasis: true },
  { id: "w", x: 985, y: 425 },
  { id: "x", x: 170, y: 565 },
  { id: "y", x: 325, y: 520 },
  { id: "z", x: 475, y: 590 },
  { id: "aa", x: 630, y: 535 },
  { id: "ab", x: 785, y: 605 },
  { id: "ac", x: 945, y: 545 },
  { id: "ad", x: 1090, y: 635 },
  { id: "ae", x: 370, y: 715 },
  { id: "af", x: 545, y: 680 },
  { id: "ag", x: 720, y: 730 },
  { id: "ah", x: 900, y: 680 },
];

const backdropEdges: Array<readonly [string, string]> = [
  ["a", "b"], ["b", "c"], ["c", "d"], ["d", "e"], ["e", "f"], ["f", "g"], ["g", "h"],
  ["a", "i"], ["b", "i"], ["c", "j"], ["c", "k"], ["d", "k"], ["e", "l"], ["e", "m"],
  ["f", "m"], ["g", "n"], ["g", "o"], ["h", "o"], ["i", "j"], ["j", "k"], ["k", "l"],
  ["l", "m"], ["m", "n"], ["n", "o"], ["o", "p"], ["i", "q"], ["j", "r"], ["k", "s"],
  ["l", "t"], ["m", "u"], ["n", "v"], ["o", "w"], ["q", "r"], ["r", "s"], ["s", "t"],
  ["t", "u"], ["u", "v"], ["v", "w"], ["q", "x"], ["r", "x"], ["r", "y"], ["s", "y"],
  ["s", "z"], ["t", "z"], ["t", "aa"], ["u", "aa"], ["u", "ab"], ["v", "ab"], ["v", "ac"],
  ["w", "ac"], ["w", "ad"], ["x", "y"], ["y", "z"], ["z", "aa"], ["aa", "ab"], ["ab", "ac"],
  ["ac", "ad"], ["y", "ae"], ["z", "af"], ["aa", "af"], ["ab", "ag"], ["ac", "ah"],
  ["ae", "af"], ["af", "ag"], ["ag", "ah"],
];

const backdropById = new Map(backdropNodes.map((node) => [node.id, node]));

function value(fields: Record<string, Observed>, ...names: string[]): number | null {
  for (const name of names) {
    const raw = fields[name]?.value;
    if (typeof raw === "number") return raw;
    if (typeof raw === "string" && raw.trim() !== "" && Number.isFinite(Number(raw))) return Number(raw);
  }
  return null;
}

function when(iso: string): string {
  const date = new Date(iso);
  const age = Date.now() - date.getTime();
  if (age < 86_400_000 && date.toDateString() === new Date().toDateString()) {
    return `today ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  }
  const days = Math.max(1, Math.round(age / 86_400_000));
  return days === 1 ? "yesterday" : `${days} days ago`;
}

function duration(session: Session): string {
  const end = new Date(session.ended_at ?? session.updated_at).getTime();
  const start = new Date(session.created_at).getTime();
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function sortSessions(sessions: Session[]): Session[] {
  return [...sessions].sort((a, b) => {
    if (a.live !== b.live) return a.live ? -1 : 1;
    return Date.parse(b.updated_at) - Date.parse(a.updated_at);
  });
}

function Constellation({ live }: { live: boolean }) {
  return (
    <div className="scene" aria-hidden="true">
      <svg viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice">
        {backdropEdges.map(([sourceId, targetId]) => {
          const source = backdropById.get(sourceId);
          const target = backdropById.get(targetId);
          if (!source || !target) return null;
          return <line className="link" key={`${sourceId}-${targetId}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y} />;
        })}
        {backdropNodes.map((node) => (
          <circle
            className={`node ${node.emphasis ? "current" : ""} ${live && node.id === "v" ? "agent" : ""}`}
            cx={node.x}
            cy={node.y}
            key={node.id}
            r={node.emphasis ? 5.5 : 3.5}
          />
        ))}
      </svg>
    </div>
  );
}

function StatusBars({ snapshot, compact = false }: { snapshot: Snapshot; compact?: boolean }) {
  const fields = snapshot.player_status.fields;
  const hp = value(fields, "hp", "hit", "hitpoints");
  const maxHp = value(fields, "max_hp", "max_hit", "maxhit");
  const mana = value(fields, "mana");
  const maxMana = value(fields, "max_mana", "maxmana");
  const level = value(fields, "level");
  const gold = value(fields, "gold");
  if (compact) {
    return (
      <>
        {level !== null && <div className="level">Level {level}</div>}
        {hp !== null && maxHp !== null && <div className="micro"><i style={{ width: `${Math.min(100, hp / maxHp * 100)}%` }} /></div>}
      </>
    );
  }
  return (
    <>
      {level !== null && <div className="level">Level {level} adventurer</div>}
      <div className="bars">
        {hp !== null && maxHp !== null && <Bar name="HP" current={hp} max={maxHp} tone="hp" />}
        {mana !== null && maxMana !== null && <Bar name="Mana" current={mana} max={maxMana} tone="mana" />}
      </div>
      {gold !== null && <div className="gold">◉ {gold.toLocaleString()} gold</div>}
      <div className="observed-note">stats as observed in the last session</div>
    </>
  );
}

function Bar({ name, current, max, tone }: { name: string; current: number; max: number; tone: string }) {
  return (
    <div className="bar">
      <span>{name}</span>
      <span className="track"><i className={tone} style={{ width: `${Math.min(100, current / max * 100)}%` }} /></span>
      <span className="bar-value">{current} / {max}</span>
    </div>
  );
}

export function Launcher() {
  const launcherQuery = new URLSearchParams(window.location.search);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState(
    () => launcherQuery.get("player")?.trim() ?? "",
  );
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [startOpen, setStartOpen] = useState(true);
  const [loadOpen, setLoadOpen] = useState(
    () => launcherQuery.get("load") === "1",
  );
  const [allPlayers, setAllPlayers] = useState(false);
  const [temple, setTemple] = useState(false);
  const [baseline, setBaseline] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startMessage, setStartMessage] = useState("");

  const loadCatalog = () => {
    setError("");
    fetch("/api/sessions")
      .then((response) => {
        if (!response.ok) throw new Error(`Sessions unavailable (${response.status})`);
        return response.json() as Promise<Catalog>;
      })
      .then((next) => {
        setCatalog(next);
        const ordered = [...next.players].sort((a, b) => {
          const aa = sortSessions(next.sessions.filter((session) => session.player_id === a.id))[0];
          const bb = sortSessions(next.sessions.filter((session) => session.player_id === b.id))[0];
          if (Boolean(aa?.live) !== Boolean(bb?.live)) return aa?.live ? -1 : 1;
          return Date.parse(bb?.updated_at ?? "0") - Date.parse(aa?.updated_at ?? "0");
        });
        setSelected((current) => current || ordered[0]?.id || "");
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Sessions unavailable"));
  };

  useEffect(() => {
    loadCatalog();
    const timer = window.setInterval(loadCatalog, 2_000);
    return () => window.clearInterval(timer);
  }, []);

  const rows: PlayerRow[] = useMemo(() => (catalog?.players ?? []).map((player) => {
    const sessions = sortSessions((catalog?.sessions ?? []).filter((session) => session.player_id === player.id));
    return { ...player, sessions, latest: sessions[0] ?? null };
  }).sort((a, b) => {
    if (Boolean(a.latest?.live) !== Boolean(b.latest?.live)) return a.latest?.live ? -1 : 1;
    return Date.parse(b.latest?.updated_at ?? "0") - Date.parse(a.latest?.updated_at ?? "0");
  }), [catalog]);

  const selectedRow = rows.find((row) => row.id === selected) ?? null;

  useEffect(() => {
    const session = selectedRow?.latest;
    setSnapshot(null);
    if (!session) return;
    fetch(`/api/sessions/${encodeURIComponent(session.id)}/snapshot`)
      .then((response) => {
        if (!response.ok) throw new Error(`Snapshot unavailable (${response.status})`);
        return response.json() as Promise<unknown>;
      })
      .then((value) => setSnapshot(decodeSnapshot(value)))
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Snapshot unavailable"));
  }, [selectedRow?.latest?.id]);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setStartOpen(false);
        setLoadOpen(false);
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);

  const liveSessions = (catalog?.sessions ?? []).filter((session) => session.live);
  const ended = sortSessions((catalog?.sessions ?? []).filter((session) => !session.live && (allPlayers || session.player_id === selected)));
  const selectedEndedCount = (selectedRow?.sessions ?? []).filter((session) => !session.live).length;
  const allEndedCount = (catalog?.sessions ?? []).filter((session) => !session.live).length;

  const startSession = async () => {
    if (!selectedRow || selectedRow.latest?.live || starting) return;
    setStarting(true);
    setStartMessage("");
    const reset = baseline ? "baseline" : temple ? "temple" : "none";
    try {
      const response = await fetch(lifecycleApiUrl("/api/sessions/start"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          player_id: selectedRow.id,
          reset,
        }),
      });
      const payload = await response.json() as StartResponse | StartError;
      if (!response.ok) {
        const failure = payload as StartError;
        throw new Error(failure.detail || "The session could not be started.");
      }
      const started = payload as StartResponse;
      window.location.assign(liveHref({
        playerId: started.player_id,
        sessionId: started.session_id,
      }));
    } catch (cause: unknown) {
      setStartMessage(
        cause instanceof Error ? cause.message : "The session could not be started."
      );
      setStarting(false);
    }
  };

  return (
    <main>
      <Constellation live={liveSessions.length > 0} />
      <div className="wrap">
        <section className="left">
          <header className="brand">
            <h1>Boukensha<br /><b>Observatory</b></h1>
            <p>Watch an agent live inside the world of Arcane Loop.</p>
          </header>
          {error && <div className="error">{error} <button onClick={loadCatalog}>Retry</button></div>}
          {!catalog && !error && <div className="skeleton" aria-label="Loading adventurers" />}
          <div className="roster">
            {rows.map((row) => {
              const active = row.id === selected;
              return (
                <button className={`character ${active ? "selected expanded" : ""}`} key={row.id} onClick={() => setSelected(row.id)}>
                  <span className="character-main">
                    <span className="sigil">{row.latest?.live ? "⚔" : "◎"}</span>
                    <span className="identity">
                      <span className="name">{row.label}{row.latest?.live && <i className="live-dot" />}</span>
                      {active && snapshot ? <StatusBars snapshot={snapshot} /> : snapshot?.player_id === row.id ? <StatusBars snapshot={snapshot} compact /> : null}
                      {!row.latest && <span className="empty">no sessions yet</span>}
                    </span>
                    {row.latest && <span className="seen">{row.latest.live ? <>LIVE now<br />turn {row.latest.latest_seq}</> : <>last session<br />{when(row.latest.updated_at)}</>}</span>}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="menu">
          {liveSessions.map((session) => (
            <button className="menu-item watch" key={session.id} onClick={() => {
              window.location.href = liveHref({
                playerId: session.player_id,
                sessionId: session.id,
              });
            }}>
              <h2><i className="live-dot" /> WATCH LIVE <span>{session.character} · turn {session.latest_seq}</span></h2>
              <p>{session.character} is exploring right now. Join the run in progress.</p>
            </button>
          ))}

          <section className={`menu-item ${selectedRow?.latest?.live ? "disabled" : ""}`}>
            <button className="menu-heading" onClick={() => setStartOpen((open) => !open)}>
              <h2>⚔ START A NEW SESSION <span className="chip">as {selectedRow?.label ?? "player"}</span></h2>
              <p>{selectedRow?.latest?.live ? `${selectedRow.label} is live. Watch or wait.` : "Send the selected adventurer back into the world."}</p>
            </button>
            {startOpen && (
              <div className="form">
                <div className="checks">
                  <label title="Move the player to the Temple of Midgaard before the session starts. Stats and items are untouched.">
                    <input type="checkbox" checked={temple} disabled={starting || Boolean(selectedRow?.latest?.live)} onChange={(event) => {
                      setTemple(event.target.checked);
                      if (event.target.checked) setBaseline(false);
                    }} />
                    Reset to Temple
                  </label>
                  <label title="Restore the player to the versioned baseline start. Inventory is untouched.">
                    <input type="checkbox" checked={baseline} disabled={starting || Boolean(selectedRow?.latest?.live)} onChange={(event) => {
                      setBaseline(event.target.checked);
                      if (event.target.checked) setTemple(false);
                    }} />
                    Reset to baseline
                  </label>
                </div>
                <p className="hint">Unchecked resumes the game normally.</p>
                <button className="go" disabled={starting || !selectedRow || Boolean(selectedRow.latest?.live)} onClick={startSession}>
                  {starting ? "Starting…" : `Start session as ${selectedRow?.label ?? "player"} →`}
                </button>
                {startMessage && <p className="start-message" role="alert">{startMessage}</p>}
              </div>
            )}
          </section>

          <section className="menu-item">
            <button className="menu-heading" onClick={() => setLoadOpen((open) => !open)}>
              <h2>▤ LOAD A SESSION <span>{selectedRow?.label ?? "player"} · {selectedEndedCount} of {allEndedCount}</span></h2>
              <p>Replay any recorded run of the selected player, or all players.</p>
            </button>
            {loadOpen && (
              <div className="session-list">
                <label className="all-toggle"><input type="checkbox" checked={allPlayers} onChange={(event) => setAllPlayers(event.target.checked)} /> All players</label>
                {ended.length === 0 && <p className="empty-session">No recorded sessions yet.</p>}
                {ended.map((session) => (
                  <button className="session-row" key={session.id} onClick={() => {
                    window.location.href = `http://127.0.0.1:8787/?space=sessions&player=${encodeURIComponent(session.player_id)}&record=${encodeURIComponent(session.id)}&run=${encodeURIComponent(session.id)}`;
                  }}>
                    <span>{allPlayers ? `${session.character} · ` : ""}{when(session.updated_at)}</span>
                    <span>
                      {session.stop_mode === "forced_after_grace"
                        ? "stopped · forced after grace · "
                        : session.stop_mode === "cooperative"
                          ? "stopped · "
                          : ""}
                      {session.event_count} events · {duration(session)} · Load →
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>
        </section>
      </div>
    </main>
  );
}
