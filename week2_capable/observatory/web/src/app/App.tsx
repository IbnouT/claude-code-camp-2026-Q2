import { useEffect, useMemo, useState } from "react";
import type { Space } from "./shellTypes";
import { shellFixture } from "./shellFixture";
import { useCapabilities } from "./useCapabilities";
import { usePreferences } from "./usePreferences";
import { useRuntimeCatalog } from "../data/useRuntimeCatalog";
import { useRecordedSessions } from "../data/useRecordedSessions";
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
import { SessionsWorkspace } from "../components/sessions/SessionsWorkspace";
import { ExperimentsWorkspace } from "../components/experiments/ExperimentsWorkspace";

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
  const [liveSession, setLiveSession] = useState(
    () => (
      new URL(window.location.href).searchParams.get("liveSession")
      ?? new URL(window.location.href).searchParams.get("session")
      ?? ""
    ),
  );
  const [recordedRun, setRecordedRun] = useState(
    () => new URL(window.location.href).searchParams.get("run") ?? "",
  );
  const recorded = useRecordedSessions(recordedRun);
  const [searchOpen, setSearchOpen] = useState(false);
  const [controlOpen, setControlOpen] = useState(false);
  const liveSessionsForPlayer = runtime.catalog.sessions.filter(
    (candidate) => candidate.player_id === player,
  );
  const selectedSession = runtime.catalog.sessions.find(
    (candidate) => candidate.id === liveSession,
  ) ?? null;
  const live = useSessionStream(selectedSession);
  const playerOptions = useMemo(() => {
    const options = new Map(
      runtime.catalog.players.map((candidate) => [
        candidate.id,
        {
          id: candidate.id,
          label: candidate.label,
          detail: "Registered player",
        },
      ]),
    );
    for (const candidate of recorded.catalog) {
      if (!options.has(candidate.player_id)) {
        options.set(candidate.player_id, {
          id: candidate.player_id,
          label: `${candidate.player_id} · recorded`,
          detail: "Recorded evidence",
        });
      }
    }
    return [...options.values()];
  }, [recorded.catalog, runtime.catalog.players]);
  const availablePlayerOptions = playerOptions.length > 0
    ? playerOptions
    : [{
      id: "",
      label: (
        runtime.loading || recorded.loadingCatalog
          ? "Discovering…"
          : "No players"
      ),
      detail: runtime.error ?? recorded.error ?? "Start an agent or load evidence",
    }];
  const liveSessionOptions = liveSessionsForPlayer.length > 0
    ? liveSessionsForPlayer.map((candidate) => ({
      id: candidate.id,
      label: `${candidate.live ? "●" : "○"} ${candidate.state} · ${candidate.event_count} events`,
      detail: candidate.id,
    }))
    : [{
      id: "",
      label: "No sessions",
      detail: "Start an agent for this player",
    }];
  const recordedSessionOptions = recorded.catalog
    .filter((candidate) => candidate.player_id === player)
    .map((candidate) => ({
      id: candidate.id,
      label: `${candidate.success ? "✓" : "!"} ${candidate.journey} · ${candidate.result_mode} · ${candidate.iterations} turns`,
      detail: "Recorded experiment sample",
    }));
  const sessionOptions = space === "sessions"
    ? (
      recordedSessionOptions.length > 0
        ? recordedSessionOptions
        : [{
          id: "",
          label: "No recorded sessions",
          detail: "Configure or load recorded evidence",
        }]
    )
    : liveSessionOptions;
  const headerSession = space === "sessions" ? recordedRun : liveSession;

  useEffect(() => {
    if (playerOptions.length === 0) {
      return;
    }
    const preferredLive = runtime.catalog.sessions.find(
      (candidate) => candidate.live,
    );
    if (
      space === "live"
      && preferredLive
      && !runtime.catalog.sessions.some(
        (candidate) => candidate.player_id === player,
      )
      && preferredLive.player_id !== player
    ) {
      setPlayer(preferredLive.player_id);
      setLiveSession(preferredLive.id);
      return;
    }
    const selectedPlayerExists = playerOptions.some(
      (candidate) => candidate.id === player,
    );
    if (runtime.loading && !selectedPlayerExists) {
      return;
    }
    const nextPlayer = selectedPlayerExists
      ? player
      : (
        runtime.catalog.sessions.find((candidate) => candidate.live)?.player_id
        ?? playerOptions[0]?.id
        ?? ""
      );
    if (nextPlayer !== player) {
      setPlayer(nextPlayer);
      return;
    }
    const available = runtime.catalog.sessions.filter(
      (candidate) => candidate.player_id === nextPlayer,
    );
    if (!available.some((candidate) => candidate.id === liveSession)) {
      setLiveSession(
        available.find((candidate) => candidate.live)?.id
        ?? available[0]?.id
        ?? "",
      );
    }
  }, [
    liveSession,
    player,
    playerOptions,
    runtime.catalog,
    runtime.loading,
    space,
  ]);

  useEffect(() => {
    if (
      space === "sessions"
      && recorded.catalog.length > 0
      && !recorded.catalog.some(
        (candidate) => candidate.player_id === player,
      )
    ) {
      setPlayer(
        recorded.catalog.find((candidate) => candidate.journey === "J2")
          ?.player_id
        ?? recorded.catalog[0]?.player_id
        ?? player,
      );
    }
  }, [player, recorded.catalog, space]);

  useEffect(() => {
    const available = recorded.catalog.filter(
      (candidate) => candidate.player_id === player,
    );
    const selected = recorded.catalog.find(
      (candidate) => candidate.id === recordedRun,
    );
    if (!recordedRun || (selected && selected.player_id !== player)) {
      setRecordedRun(
        available.find((candidate) => candidate.journey === "J2")?.id
        ?? available[0]?.id
        ?? "",
      );
    }
  }, [player, recorded.catalog, recordedRun]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("space", space);
    if (player) url.searchParams.set("player", player);
    else url.searchParams.delete("player");
    if (liveSession) url.searchParams.set("liveSession", liveSession);
    else url.searchParams.delete("liveSession");
    if (recordedRun) url.searchParams.set("run", recordedRun);
    else url.searchParams.delete("run");
    url.searchParams.delete("session");
    window.history.replaceState(null, "", url);
  }, [liveSession, player, recordedRun, space]);

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
        players={availablePlayerOptions}
        selectedPlayer={player}
        selectedSession={headerSession}
        sessions={sessionOptions}
        theme={preferences.theme}
        onPlayerChange={(nextPlayer) => {
          setPlayer(nextPlayer);
          const nextSession = runtime.catalog.sessions.find(
            (candidate) => candidate.player_id === nextPlayer && candidate.live,
          ) ?? runtime.catalog.sessions.find(
            (candidate) => candidate.player_id === nextPlayer,
          );
          setLiveSession(nextSession?.id ?? "");
          const nextRecorded = recorded.catalog.find(
            (candidate) => (
              candidate.player_id === nextPlayer
              && candidate.journey === "J2"
            ),
          ) ?? recorded.catalog.find(
            (candidate) => candidate.player_id === nextPlayer,
          );
          setRecordedRun(nextRecorded?.id ?? "");
        }}
        onSessionChange={
          space === "sessions" ? setRecordedRun : setLiveSession
        }
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
        ) : space === "sessions" ? (
          <SessionsWorkspace
            investigation={recorded.investigation}
            loading={
              recorded.loadingCatalog || recorded.loadingInvestigation
            }
            error={recorded.error}
            onOpenSearch={() => setSearchOpen(true)}
          />
        ) : space === "experiments" ? (
          <ExperimentsWorkspace
            playerProfile={player}
            onOpenRun={(runId) => {
              const run = recorded.catalog.find((candidate) => candidate.id === runId);
              if (run) {
                setPlayer(run.player_id);
              }
              setRecordedRun(runId);
              setSpace("sessions");
            }}
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
      <SearchDialog
        open={searchOpen}
        modelAvailable={capabilities.features.includes("copilot-model")}
        scope={{
          space,
          ...(player ? { player_id: player } : {}),
          ...(space === "live" && liveSession
            ? {
              live_session_id: liveSession,
              through_sequence: (
                live.snapshot?.through_sequence
                ?? live.selectedSequence
              ),
            }
            : {}),
          ...(space === "sessions" && recordedRun
            ? {
              run_id: recordedRun,
              selected_record_id: (
                new URL(window.location.href).searchParams.get("record")
                ?? undefined
              ),
            }
            : {}),
          ...(space === "experiments"
            ? {
              comparison_id: (
                new URL(window.location.href).searchParams.get("comparison")
                ?? undefined
              ),
              subject_id: (
                new URL(window.location.href).searchParams.get("subject")
                ?? undefined
              ),
            }
            : {}),
          lens: (
            new URL(window.location.href).searchParams.get("lens")
            ?? undefined
          ),
        }}
        scopeLabel={
          space === "sessions" && recorded.investigation
            ? `${recorded.investigation.run.journey} · ${recorded.investigation.run.attempt}`
            : space === "live" && selectedSession
              ? `${selectedSession.character} · ${selectedSession.id}`
              : `${space} space`
        }
        onClose={() => setSearchOpen(false)}
        onOpenCitation={(citationId) => {
          const url = new URL(window.location.href);
          if (citationId.startsWith("runtime:")) {
            url.searchParams.set("space", "live");
            setSpace("live");
          } else if (citationId.startsWith("experiment:sample:")) {
            const runId = citationId.replace("experiment:sample:", "");
            const run = recorded.catalog.find(
              (candidate) => candidate.id === runId,
            );
            url.searchParams.set("space", "sessions");
            url.searchParams.set("run", runId);
            if (run) {
              url.searchParams.set("player", run.player_id);
              setPlayer(run.player_id);
            }
            setRecordedRun(runId);
            setSpace("sessions");
          } else if (citationId.startsWith("experiment:")) {
            url.searchParams.set("space", "experiments");
            url.searchParams.set("subject", citationId.split(":")[1] ?? "");
            setSpace("experiments");
          } else if (citationId.startsWith("knowledge:")) {
            url.searchParams.set("space", "knowledge");
            url.searchParams.set("subject", citationId);
            setSpace("knowledge");
          } else if (citationId.startsWith("gateway:place:")) {
            url.searchParams.set("space", "sessions");
            url.searchParams.set(
              "room",
              citationId.replace("gateway:place:", "place:"),
            );
            url.searchParams.set("lens", "story");
            setSpace("sessions");
          } else {
            url.searchParams.set("space", "sessions");
            url.searchParams.set("record", citationId);
            url.searchParams.set("lens", "evidence");
            setSpace("sessions");
          }
          window.history.pushState(null, "", url);
          window.dispatchEvent(new PopStateEvent("popstate"));
          setSearchOpen(false);
        }}
      />
      <AgentControlDialog
        open={controlOpen}
        selectedPlayer={player}
        selectedSession={liveSession}
        sequence={live.latestSequence}
        objective={live.snapshot?.objective ?? null}
        model={live.snapshot?.model ?? null}
        tools={live.snapshot?.tools ?? []}
        onClose={() => setControlOpen(false)}
        onSubmit={(draft) => submitControl(liveSession, draft)}
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
