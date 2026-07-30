import { useEffect, useState } from "react";
import type { Space } from "./shellTypes";
import { shellFixture } from "./shellFixture";
import { useCapabilities } from "./useCapabilities";
import { usePreferences } from "./usePreferences";
import { CanonicalHeader } from "../components/shell/CanonicalHeader";
import { AgentControlDialog } from "../components/shell/AgentControlDialog";
import { InvestigationShell } from "../components/shell/InvestigationShell";
import { SearchDialog } from "../components/shell/SearchDialog";

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
  const [space, setSpace] = useState<Space>(spaceFromUrl);
  const [player, setPlayer] = useState(shellFixture.players[0].id);
  const [session, setSession] = useState(shellFixture.sessions[0].id);
  const [searchOpen, setSearchOpen] = useState(false);
  const [controlOpen, setControlOpen] = useState(false);

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
        players={shellFixture.players}
        selectedPlayer={player}
        selectedSession={session}
        sessions={shellFixture.sessions}
        theme={preferences.theme}
        onPlayerChange={setPlayer}
        onSessionChange={setSession}
        onSpaceChange={setSpace}
        onThemeChange={preferences.setTheme}
      />
      <main className="app-main">
        <InvestigationShell
          activeSpace={space}
          capabilities={capabilities}
          fixture={shellFixture}
          onOpenControl={() => setControlOpen(true)}
          onOpenSearch={() => setSearchOpen(true)}
        />
      </main>
      <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
      <AgentControlDialog
        fixture={shellFixture}
        open={controlOpen}
        selectedPlayer={player}
        selectedSession={session}
        onClose={() => setControlOpen(false)}
      />
    </div>
  );
}
