import {
  useEffect,
  useState,
} from "react";
import type { Catalog } from "../contracts";
import type { LiveRouteIdentity } from "../routes";
import type { Theme } from "../theme";
import { LiveAskDialog } from "./LiveAskDialog";
import { LiveCausalTimeline } from "./LiveCausalTimeline";
import type { ContextState } from "./LiveContextSwitcher";
import { LiveHeader } from "./LiveHeader";
import { LiveMap } from "./LiveMap";
import { LiveEvidenceRail } from "./LiveEvidenceRail";
import { LiveObjectiveStrip } from "./LiveObjectiveStrip";
import { MessageAgentDialog } from "./MessageAgentDialog";
import { SessionStopDialog } from "./SessionStopDialog";
import { useLiveSnapshot } from "./useLiveSnapshot";

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
  const [messageOpen, setMessageOpen] = useState(false);
  const [throughSequence, setThroughSequence] = useState<number | null>(() => {
    const value = Number(new URL(window.location.href).searchParams.get("through"));
    return Number.isInteger(value) && value > 0 ? value : null;
  });
  const [railOpen, setRailOpen] = useState(() => window.innerWidth > 700);
  const [contextState, setContextState] = useState<ContextState>("checking");
  const {
    latestSnapshot,
    snapshot,
    state: snapshotState,
  } = useLiveSnapshot(identity, throughSequence);
  const selectedSession = identity === null ? undefined : catalog?.sessions.find(
    (session) => session.id === identity.sessionId
      && session.player_id === identity.playerId,
  );
  useEffect(() => {
    const url = new URL(window.location.href);
    if (throughSequence === null) {
      url.searchParams.delete("through");
    } else {
      url.searchParams.set("through", String(throughSequence));
    }
    window.history.replaceState(null, "", url);
  }, [throughSequence]);

  useEffect(() => {
    const value = Number(
      new URL(window.location.href).searchParams.get("through"),
    );
    setThroughSequence(Number.isInteger(value) && value > 0 ? value : null);
  }, [identity?.playerId, identity?.sessionId]);

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
        onMessage={() => setMessageOpen(true)}
        messageAvailable={
          identity !== null && selectedSession?.control_available === true
        }
        onNavigate={navigate}
        onRequestStop={() => setStopOpen(true)}
        onThemeChange={onThemeChange}
      />
      <LiveObjectiveStrip objective={snapshot?.objective_context ?? null} />
      <main className="live-workspace" aria-label="Live workspace">
        {identity !== null ? (
          <LiveMap
            identity={identity}
            snapshot={snapshot}
            state={snapshotState}
          />
        ) : null}
        <aside
          aria-label="Live evidence rail"
          className={[
            "live-layout-reserve live-evidence-rail",
            railOpen ? "is-open" : "is-closed",
          ].join(" ")}
        >
          <button
            aria-expanded={railOpen}
            aria-label={railOpen ? "Close Live evidence" : "Open Live evidence"}
            className="live-rail-toggle"
            type="button"
            onClick={() => setRailOpen((current) => !current)}
          >
            Evidence
          </button>
          <LiveEvidenceRail
            captureStatus={selectedSession?.capture_status ?? null}
            connectionState={snapshotState}
            snapshot={snapshot}
          />
        </aside>
        <section
          aria-label="Causal timeline"
          className="live-layout-reserve live-causal-timeline"
        >
          <LiveCausalTimeline
            latestSnapshot={latestSnapshot}
            snapshot={snapshot}
            state={snapshotState}
            onSelectThrough={setThroughSequence}
          />
        </section>
      </main>
      {askOpen && identity !== null ? (
        <LiveAskDialog
          identity={identity}
          open
          onClose={() => setAskOpen(false)}
        />
      ) : null}
      {messageOpen && identity !== null && snapshot !== null ? (
        <MessageAgentDialog
          expectedSequence={snapshot.latest_sequence}
          followingLive={snapshot.following_live}
          identity={identity}
          messages={snapshot.operator_messages}
          objectiveAvailable={
            snapshot.objective_context !== null || snapshot.objective !== null
          }
          selectedSequence={snapshot.through_sequence}
          sessionRunning={contextState === "running"}
          controlAvailable={selectedSession?.control_available === true}
          onClose={() => setMessageOpen(false)}
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
