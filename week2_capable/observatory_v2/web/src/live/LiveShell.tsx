import {
  useEffect,
  useState,
} from "react";
import type { Catalog } from "../contracts";
import type { LiveRouteIdentity } from "../routes";
import type { Theme } from "../theme";
import { LiveAskDialog } from "./LiveAskDialog";
import type { ContextState } from "./LiveContextSwitcher";
import { LiveHeader } from "./LiveHeader";
import { LiveMap } from "./LiveMap";
import { SessionStopDialog } from "./SessionStopDialog";

type Props = {
  identity: LiveRouteIdentity | null;
  theme?: Theme;
  navigate?: (href: string) => void;
  onThemeChange?: (theme: Theme) => void;
};

const defaultNavigate = (href: string) => window.location.assign(href);
const defaultThemeChange = () => undefined;

export function LiveShell({
  identity,
  theme = "dark",
  navigate = defaultNavigate,
  onThemeChange = defaultThemeChange,
}: Props) {
  const [askOpen, setAskOpen] = useState(false);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [stopOpen, setStopOpen] = useState(false);
  const [contextState, setContextState] = useState<ContextState>("checking");

  useEffect(() => {
    if (identity === null) {
      navigate("/");
      return;
    }
    const controller = new AbortController();
    let timer = 0;
    let terminal = false;
    if (catalog === null) {
      setContextState("checking");
    }
    const loadCatalog = () => {
      fetch("/api/sessions", {
        cache: "no-store",
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Sessions unavailable (${response.status})`);
          }
          return response.json() as Promise<Catalog>;
        })
        .then((nextCatalog) => {
          setCatalog(nextCatalog);
          const session = nextCatalog.sessions.find(
            (candidate) => candidate.id === identity.sessionId
              && candidate.player_id === identity.playerId,
          );
          if (session === undefined) {
            terminal = true;
            navigate("/");
            return;
          }
          if (session.state === "draining") {
            setContextState("draining");
          } else if (session.state === "stopped") {
            setContextState("stopped");
          } else if (session.live) {
            setContextState("running");
          } else {
            setContextState("ended");
          }
        })
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") {
            return;
          }
          setContextState("reconnecting");
        })
        .finally(() => {
          if (!controller.signal.aborted && !terminal) {
            timer = window.setTimeout(loadCatalog, 2_000);
          }
        });
    };
    loadCatalog();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [catalogRevision, identity, navigate]);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (
        identity !== null
        && (event.metaKey || event.ctrlKey)
        && event.key.toLowerCase() === "k"
      ) {
        event.preventDefault();
        setAskOpen(true);
      }
      if (event.key === "Escape") {
        setAskOpen(false);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [identity]);

  return (
    <div className="live-shell">
      <LiveHeader
        catalog={catalog}
        contextState={contextState}
        identity={identity}
        theme={theme}
        onAsk={() => setAskOpen(true)}
        onLeave={() => navigate("/")}
        onNavigate={navigate}
        onRequestStop={() => setStopOpen(true)}
        onThemeChange={onThemeChange}
      />
      <main className="live-workspace" aria-label="Live workspace">
        {identity !== null ? <LiveMap identity={identity} /> : null}
        <aside
          aria-label="Live evidence rail"
          className="live-layout-reserve live-evidence-rail"
        >
          <span>Evidence rail</span>
        </aside>
        <section
          aria-label="Causal timeline"
          className="live-layout-reserve live-causal-timeline"
        >
          <span>Causal timeline</span>
        </section>
      </main>
      {askOpen && identity !== null ? (
        <LiveAskDialog
          identity={identity}
          open
          onClose={() => setAskOpen(false)}
        />
      ) : null}
      {stopOpen && identity !== null ? (
        <SessionStopDialog
          identity={identity}
          onCancel={() => setStopOpen(false)}
          onStopFailed={() => setContextState("running")}
          onStopping={() => setContextState("draining")}
          onStopped={() => {
            setStopOpen(false);
            setCatalogRevision((revision) => revision + 1);
          }}
        />
      ) : null}
    </div>
  );
}
