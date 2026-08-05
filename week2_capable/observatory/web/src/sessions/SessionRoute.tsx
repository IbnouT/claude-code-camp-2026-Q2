import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  Catalog,
  Session,
  SessionInvestigation,
} from "../contracts";
import { liveHref } from "../routes";
import { AppHeader } from "../shell/AppHeader";
import {
  sessionContextState,
  type ContextState,
} from "../shell/ContextSwitcher";
import { SessionFinderDialog } from "../shell/SessionFinderDialog";
import type { Theme } from "../theme";
import { LiveAskDialog } from "../live/LiveAskDialog";
import { SessionsWorkspace } from "./SessionWorkspace";
import styles from "./SessionShell.module.css";

type Props = {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
};

export function SessionRoute({ theme, onThemeChange }: Props) {
  const query = new URLSearchParams(window.location.search);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [playerId, setPlayerId] = useState(query.get("player")?.trim() ?? "");
  const [sessionId, setSessionId] = useState(query.get("session")?.trim() ?? "");
  const [runId, setRunId] = useState(query.get("run")?.trim() ?? "");
  const [investigation, setInvestigation] =
    useState<SessionInvestigation | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [investigationError, setInvestigationError] = useState("");
  const [loading, setLoading] = useState(true);
  const [askOpen, setAskOpen] = useState(false);
  const [finderOpen, setFinderOpen] = useState(false);
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const loadedInvestigation = useRef("");
  const refresh = useCallback(() => {
    setRefreshRevision((current) => current + 1);
  }, []);

  useEffect(() => {
    document.body.classList.add("sessions-document");
    return () => document.body.classList.remove("sessions-document");
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/sessions", { cache: "no-store", signal: abort.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Sessions unavailable (${response.status})`);
        }
        return response.json() as Promise<Catalog>;
      })
      .then((payload) => {
        setCatalog(payload);
        setCatalogError("");
        if (!runId) {
          const preferred = chooseSession(payload, playerId, sessionId);
          if (preferred !== null) {
            setPlayerId(preferred.player_id);
            setSessionId(preferred.id);
          }
        }
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) {
          setCatalogError(
            reason instanceof Error ? reason.message : "Sessions unavailable",
          );
        }
      });
    return () => abort.abort();
  }, [refreshRevision]);

  useEffect(() => {
    if (!sessionId && !runId) {
      setInvestigation(null);
      setLoading(false);
      return;
    }
    const abort = new AbortController();
    const investigationKey = runId ? `run:${runId}` : `session:${sessionId}`;
    setLoading(loadedInvestigation.current !== investigationKey);
    setInvestigationError("");
    fetch(
      runId
        ? `/api/recorded-sessions/${encodeURIComponent(runId)}`
        : `/api/sessions/${encodeURIComponent(sessionId)}/investigation`,
      { cache: "no-store", signal: abort.signal },
    )
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json() as { detail?: string };
          throw new Error(
            payload.detail ?? `Session unavailable (${response.status})`,
          );
        }
        return await response.json() as SessionInvestigation;
      })
      .then((payload) => {
        setInvestigation(payload);
        loadedInvestigation.current = investigationKey;
        setInvestigationError("");
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) {
          setInvestigation(null);
          setInvestigationError(
            reason instanceof Error ? reason.message : "Session unavailable",
          );
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [refreshRevision, runId, sessionId]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.pathname = "/sessions";
    if (runId) {
      url.searchParams.set("run", runId);
      url.searchParams.delete("session");
      url.searchParams.delete("player");
    } else {
      url.searchParams.delete("run");
      if (playerId) url.searchParams.set("player", playerId);
      if (sessionId) url.searchParams.set("session", sessionId);
    }
    window.history.replaceState(null, "", url);
  }, [playerId, runId, sessionId]);

  const playerSessions = useMemo(
    () => (
      catalog?.sessions.filter((session) => session.player_id === playerId)
        .sort((left, right) => (
          Date.parse(right.updated_at) - Date.parse(left.updated_at)
        ))
      ?? []
    ),
    [catalog, playerId],
  );
  const selected = catalog?.sessions.find((session) => session.id === sessionId)
    ?? null;

  useEffect(() => {
    if (runId || selected?.live !== true) return undefined;
    const timer = window.setInterval(refresh, 2_000);
    return () => window.clearInterval(timer);
  }, [refresh, runId, selected?.live]);

  const identity = runId
    ? (investigation === null
      ? null
      : { playerId: investigation.player_id, sessionId: runId })
    : (sessionId === "" ? null : { playerId, sessionId });
  const contextState: ContextState = runId
    ? "ended"
    : (selected === null ? "checking" : sessionContextState(selected));
  const openSession = (session: Session): void => {
    setFinderOpen(false);
    if (session.live) {
      window.location.assign(liveHref({
        playerId: session.player_id,
        sessionId: session.id,
      }));
      return;
    }
    setRunId("");
    setPlayerId(session.player_id);
    setSessionId(session.id);
  };

  return (
    <>
      <AppHeader
        activeSpace="sessions"
        catalog={catalog}
        contextState={contextState}
        destinations={{
          live: selected?.live
            ? {
              href: liveHref({
                playerId: selected.player_id,
                sessionId: selected.id,
              }),
            }
            : { title: "Live is available for the running session" },
          experiments: { href: "/experiments" },
          knowledge: { title: "Knowledge is not available yet" },
        }}
        identity={identity}
        theme={theme}
        onAsk={() => setAskOpen(true)}
        onNavigate={(href) => window.location.assign(href)}
        onOpenSession={openSession}
        onThemeChange={onThemeChange}
        onViewAll={() => setFinderOpen(true)}
      />
      <SessionFinderDialog
        open={finderOpen}
        selectedId={sessionId}
        sessions={playerSessions}
        onClose={() => setFinderOpen(false)}
        onSelect={openSession}
      />
      <div className={styles.shell}>
        <SessionsWorkspace
          error={catalogError || investigationError || null}
          incident={{
            annotations: [],
            sourceVersions: {},
            redactionPolicy: null,
            history: null,
          }}
          investigation={investigation}
          loading={loading}
          sourceState="recorded"
          onOpenRun={(next) => {
            setRunId("");
            setSessionId(next);
          }}
          onOpenSearch={() => setAskOpen(true)}
          onSelectionChange={setSelectedRecordId}
        />
        {selected !== null || (runId && investigation !== null) ? (
          <LiveAskDialog
            identity={{
              playerId: selected?.player_id ?? investigation?.player_id ?? "recorded",
              sessionId: runId || selected?.id || investigation?.agent_session_id || "",
            }}
            open={askOpen}
            selectedRecordId={selectedRecordId}
            space="sessions"
            onClose={() => setAskOpen(false)}
          />
        ) : null}
      </div>
    </>
  );
}

function chooseSession(
  catalog: Catalog,
  playerId: string,
  sessionId: string,
): Session | null {
  const exact = catalog.sessions.find((session) => session.id === sessionId);
  if (exact) return exact;
  const candidates = catalog.sessions
    .filter((session) => !playerId || session.player_id === playerId)
    .sort((left, right) => (
      Date.parse(right.updated_at) - Date.parse(left.updated_at)
    ));
  return candidates[0] ?? null;
}

