import { useEffect, useState } from "react";
import type { Space } from "./shellTypes";
import { shellFixture } from "./shellFixture";
import { useCapabilities } from "./useCapabilities";
import { usePreferences } from "./usePreferences";
import { useRuntimeCatalog } from "../data/useRuntimeCatalog";
import { useSessionStream } from "../data/useSessionStream";
import { CanonicalHeader } from "../components/shell/CanonicalHeader";
import { AgentControlDialog } from "../components/shell/AgentControlDialog";
import type {
  ControlDraft,
  ControlReceipt,
} from "../components/shell/AgentControlDialog";
import { InvestigationShell } from "../components/shell/InvestigationShell";
import { SearchDialog } from "../components/shell/SearchDialog";
import { LiveCockpit } from "../components/live/LiveCockpit";

function spaceFromUrl(): Space {
  const requested = new URL(window.location.href).searchParams.get("space");
  return requested === "sessions"
    || requested === "experiments"
    || requested === "knowledge"
    ? requested
    : "live";
}

export function App() {
  const capabilities = useCapabilities();
  const preferences = usePreferences();
  const runtime = useRuntimeCatalog();
  const [space, setSpace] = useState<Space>(spaceFromUrl);
  const [player, setPlayer] = useState(
    () => new URL(window.location.href).searchParams.get("player") ?? "",
  );
  const [session, setSession] = useState(
    () => new URL(window.location.href).searchParams.get("session") ?? "",
  );
  const [searchOpen, setSearchOpen] = useState(false);
  const [controlOpen, setControlOpen] = useState(false);
  const sessionsForPlayer = runtime.catalog.sessions.filter(
    (candidate) => candidate.player_id === player,
  );
  const selectedSession = runtime.catalog.sessions.find(
    (candidate) => candidate.id === session,
  ) ?? null;
  const live = useSessionStream(selectedSession);
  const playerOptions = runtime.catalog.players.length > 0
    ? runtime.catalog.players.map((candidate) => ({
      id: candidate.id,
      label: candidate.label,
      detail: "Registered player",
    }))
    : [{
      id: "",
      label: runtime.loading ? "Discovering…" : "No registered players",
      detail: runtime.error ?? "Start an agent to create a session",
    }];
  const sessionOptions = sessionsForPlayer.length > 0
    ? sessionsForPlayer.map((candidate) => ({
      id: candidate.id,
      label: `${candidate.live ? "●" : "○"} ${candidate.state} · ${candidate.event_count} events`,
      detail: candidate.id,
    }))
    : [{
      id: "",
      label: "No sessions",
      detail: "Start an agent for this player",
    }];

  useEffect(() => {
    if (runtime.catalog.players.length === 0) {
      return;
    }
    const selectedPlayerExists = runtime.catalog.players.some(
      (candidate) => candidate.id === player,
    );
    const nextPlayer = selectedPlayerExists
      ? player
      : (
        runtime.catalog.sessions.find((candidate) => candidate.live)?.player_id
        ?? runtime.catalog.players[0]?.id
        ?? ""
      );
    if (nextPlayer !== player) {
      setPlayer(nextPlayer);
      return;
    }
    const available = runtime.catalog.sessions.filter(
      (candidate) => candidate.player_id === nextPlayer,
    );
    if (!available.some((candidate) => candidate.id === session)) {
      setSession(
        available.find((candidate) => candidate.live)?.id
        ?? available[0]?.id
        ?? "",
      );
    }
  }, [player, runtime.catalog, session]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("space", space);
    window.history.replaceState(null, "", url);
  }, [space]);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k"
        || event.key === "/"
      ) {
        event.preventDefault();
        setSearchOpen(true);
      }
      if (event.key === "Escape") {
        setSearchOpen(false);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  return (
    <div className="app-shell">
      <CanonicalHeader
        activeSpace={space}
        players={playerOptions}
        selectedPlayer={player}
        selectedSession={session}
        sessions={sessionOptions}
        theme={preferences.theme}
        onPlayerChange={(nextPlayer) => {
          setPlayer(nextPlayer);
          const nextSession = runtime.catalog.sessions.find(
            (candidate) => candidate.player_id === nextPlayer && candidate.live,
          ) ?? runtime.catalog.sessions.find(
            (candidate) => candidate.player_id === nextPlayer,
          );
          setSession(nextSession?.id ?? "");
        }}
        onSessionChange={setSession}
        onSpaceChange={setSpace}
        onThemeChange={preferences.setTheme}
      />
      <main className="app-main">
        {space === "live" ? (
          <LiveCockpit
            capabilities={capabilities}
            live={live}
            session={selectedSession}
            onOpenControl={() => setControlOpen(true)}
            onOpenSearch={() => setSearchOpen(true)}
          />
        ) : (
          <InvestigationShell
            activeSpace={space}
            capabilities={capabilities}
            fixture={shellFixture}
            onOpenControl={() => setControlOpen(true)}
            onOpenSearch={() => setSearchOpen(true)}
          />
        )}
      </main>
      <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
      <AgentControlDialog
        open={controlOpen}
        selectedPlayer={player}
        selectedSession={session}
        sequence={live.latestSequence}
        objective={live.snapshot?.objective ?? null}
        model={live.snapshot?.model ?? null}
        tools={live.snapshot?.tools ?? []}
        onClose={() => setControlOpen(false)}
        onSubmit={(draft) => submitControl(session, draft)}
      />
    </div>
  );
}

async function submitControl(
  session: string,
  draft: ControlDraft,
): Promise<ControlReceipt> {
  const response = await fetch(
    `/api/sessions/${encodeURIComponent(session)}/control`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(draft),
    },
  );
  const payload = await response.json() as {
    detail?: string;
  } & Partial<ControlReceipt>;
  if (
    !response.ok
    || typeof payload.request_id !== "string"
    || typeof payload.action !== "string"
    || typeof payload.state !== "string"
    || typeof payload.insertion !== "string"
  ) {
    throw new Error(payload.detail ?? `control returned ${response.status}`);
  }
  return payload as ControlReceipt;
}
