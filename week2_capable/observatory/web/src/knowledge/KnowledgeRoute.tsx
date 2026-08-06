import {
  useEffect,
  useMemo,
  useState,
} from "react";
import type {
  Catalog,
  KnowledgeAssertion,
  PlayerKnowledge,
} from "../contracts";
import { sessionsHref } from "../routes";
import { AppHeader } from "../shell/AppHeader";
import type { Theme } from "../theme";
import styles from "./Knowledge.module.css";

type Props = {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
};

const LAYERS = ["all", "learned", "parsed", "belief", "observer_truth"];

export function KnowledgeRoute({ theme, onThemeChange }: Props) {
  const query = new URLSearchParams(window.location.search);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [playerId, setPlayerId] = useState(query.get("player")?.trim() ?? "");
  const [knowledge, setKnowledge] = useState<PlayerKnowledge | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [layer, setLayer] = useState("all");
  const [includeSuperseded, setIncludeSuperseded] = useState(false);

  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/sessions", { cache: "no-store", signal: abort.signal })
      .then((response) => response.json() as Promise<Catalog>)
      .then((payload) => {
        setCatalog(payload);
        if (!playerId && payload.players.length > 0) {
          setPlayerId(payload.players[0].id);
        }
      })
      .catch(() => undefined);
    return () => abort.abort();
  }, []);

  useEffect(() => {
    if (!playerId) return;
    const url = new URL(window.location.href);
    url.pathname = "/knowledge";
    url.searchParams.set("player", playerId);
    window.history.replaceState(null, "", url);
    const abort = new AbortController();
    fetch(
      `/api/players/${encodeURIComponent(playerId)}/knowledge`,
      { cache: "no-store", signal: abort.signal },
    )
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json() as { detail?: string };
          throw new Error(
            payload.detail ?? `Knowledge unavailable (${response.status})`,
          );
        }
        return await response.json() as PlayerKnowledge;
      })
      .then((payload) => {
        setKnowledge(payload);
        setError("");
      })
      .catch((reason: unknown) => {
        if (abort.signal.aborted) return;
        setKnowledge(null);
        setError(
          reason instanceof Error ? reason.message : "Knowledge unavailable",
        );
      });
    return () => abort.abort();
  }, [playerId]);

  const rows = useMemo(() => {
    if (knowledge === null) return [];
    const wanted = search.trim().toLowerCase();
    return knowledge.assertions.filter((assertion) => {
      if (!includeSuperseded && !assertion.current) return false;
      if (layer !== "all" && assertion.layer !== layer) return false;
      if (!wanted) return true;
      return [
        assertion.subject,
        assertion.predicate,
        JSON.stringify(assertion.value ?? ""),
        assertion.layer,
        assertion.confidence,
      ].join(" ").toLowerCase().includes(wanted);
    });
  }, [knowledge, search, layer, includeSuperseded]);

  return (
    <>
      <AppHeader
        activeSpace="knowledge"
        askDisabled
        catalog={catalog}
        contextState="checking"
        destinations={{
          live: { title: "Live is available for a running session" },
          sessions: { href: sessionsHref(playerId || undefined) },
          experiments: { href: "/experiments" },
        }}
        identity={null}
        theme={theme}
        onAsk={() => undefined}
        onNavigate={(href) => window.location.assign(href)}
        onThemeChange={onThemeChange}
        onViewAll={() => undefined}
      />
      <main className={styles.page}>
        <section className={styles.headerRow}>
          <div>
            <h1>Player knowledge</h1>
            <p className={styles.subtitle}>
              Everything this player has earned or asserted, with its layer,
              confidence, and the session evidence behind it.
            </p>
          </div>
          <label className={styles.playerField}>
            <span>Player</span>
            <select
              value={playerId}
              onChange={(event) => setPlayerId(event.target.value)}
            >
              {(catalog?.players ?? []).map((player) => (
                <option key={player.id} value={player.id}>
                  {player.label}
                </option>
              ))}
            </select>
          </label>
        </section>

        {knowledge !== null ? (
          <section className={styles.metrics} aria-label="Knowledge metrics">
            {knowledge.metrics.map((metric) => (
              <div className={styles.metric} key={metric.id} title={metric.detail}>
                <dt>{metric.label}</dt>
                <dd>{metric.value.toLocaleString()}</dd>
              </div>
            ))}
          </section>
        ) : null}

        <section className={styles.controls}>
          <input
            aria-label="Search facts"
            placeholder="Search subject, predicate, value…"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <nav aria-label="Layer filter" className={styles.layers}>
            {LAYERS.map((name) => (
              <button
                aria-current={layer === name ? "true" : undefined}
                key={name}
                type="button"
                onClick={() => setLayer(name)}
              >
                {name === "observer_truth" ? "truth" : name}
              </button>
            ))}
          </nav>
          <label className={styles.superseded}>
            <input
              checked={includeSuperseded}
              type="checkbox"
              onChange={(event) => setIncludeSuperseded(event.target.checked)}
            />
            include superseded
          </label>
          <span className={styles.count}>
            {rows.length.toLocaleString()} facts
          </span>
        </section>

        {error !== "" ? (
          <p className={styles.error} role="alert">{error}</p>
        ) : null}
        {knowledge !== null && knowledge.state !== "ready" ? (
          <p className={styles.error} role="alert">
            Knowledge is {knowledge.state} for this player.
          </p>
        ) : null}

        <section aria-label="Facts" className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Subject</th>
                <th>Predicate</th>
                <th>Value</th>
                <th>Layer</th>
                <th>Confidence</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 500).map((assertion) => (
                <FactRow assertion={assertion} key={assertion.assertion_id} />
              ))}
            </tbody>
          </table>
          {rows.length > 500 ? (
            <p className={styles.truncated}>
              Showing the first 500 of {rows.length.toLocaleString()} matching
              facts. Narrow the search to see the rest.
            </p>
          ) : null}
        </section>
      </main>
    </>
  );
}

function FactRow({ assertion }: { assertion: KnowledgeAssertion }) {
  const evidence = assertion.evidence[0];
  return (
    <tr className={assertion.current ? undefined : styles.superRow}>
      <td className={styles.mono} title={assertion.subject}>
        {shorten(assertion.subject)}
      </td>
      <td className={styles.mono}>{assertion.predicate}</td>
      <td title={renderValue(assertion.value)}>
        {shortenValue(assertion.value)}
      </td>
      <td>
        <span className={`${styles.layer} ${styles[assertion.layer] ?? ""}`}>
          {assertion.layer === "observer_truth" ? "truth" : assertion.layer}
        </span>
      </td>
      <td>{assertion.confidence}</td>
      <td className={styles.mono}>
        {evidence ? (
          <a
            href={`/sessions?session=${encodeURIComponent(evidence.session_id)}`}
            title={`${evidence.method} · seq ${evidence.source_seq}`}
          >
            {evidence.session_id.slice(0, 8)}·{evidence.source_seq}
          </a>
        ) : (
          "none"
        )}
      </td>
    </tr>
  );
}

function shorten(subject: string): string {
  if (subject.length <= 34) return subject;
  const parts = subject.split(":");
  if (parts.length >= 3) {
    return `${parts[0]}:…:${parts.slice(-2).join(":")}`;
  }
  return `${subject.slice(0, 31)}…`;
}

function renderValue(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value) ?? "";
}

function shortenValue(value: unknown): string {
  const text = renderValue(value);
  return text.length <= 60 ? text : `${text.slice(0, 57)}…`;
}
