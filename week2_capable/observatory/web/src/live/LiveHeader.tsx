import {
  MessageSquareText,
  Search,
} from "lucide-react";
import type { Catalog } from "../contracts";
import {
  sessionsHref,
  type LiveRouteIdentity,
} from "../routes";
import { ObservatoryHeader } from "../shell/ObservatoryHeader";
import type { Theme } from "../theme";
import {
  type ContextState,
  LiveContextSwitcher,
} from "./LiveContextSwitcher";

type Props = {
  identity: LiveRouteIdentity | null;
  catalog: Catalog | null;
  contextState: ContextState;
  theme: Theme;
  onAsk: () => void;
  onLeave: () => void;
  onMessage: () => void;
  messageAvailable: boolean;
  onNavigate: (href: string) => void;
  onRequestStop: () => void;
  onThemeChange: (theme: Theme) => void;
};

export function LiveHeader({
  identity,
  catalog,
  contextState,
  theme,
  onAsk,
  onLeave,
  onMessage,
  messageAvailable,
  onNavigate,
  onRequestStop,
  onThemeChange,
}: Props) {
  return (
    <ObservatoryHeader
      activeSpace="live"
      destinations={{
        sessions: { href: sessionsHref(identity?.playerId) },
        experiments: { title: "Experiments will be rebuilt after Live" },
        knowledge: { title: "Knowledge will be rebuilt after Live" },
      }}
      theme={theme}
      onNavigate={onNavigate}
      onThemeChange={onThemeChange}
    >
        {identity !== null ? (
          <LiveContextSwitcher
            catalog={catalog}
            identity={identity}
            state={contextState}
            onLeave={onLeave}
            onNavigate={onNavigate}
            onRequestStop={onRequestStop}
          />
        ) : null}

        <button
          aria-label="Message agent"
          className="live-header-action live-message-action"
          disabled={!messageAvailable}
          title={messageAvailable
            ? "Guide the running agent"
            : "Messaging requires a running, controllable session"}
          type="button"
          onClick={onMessage}
        >
          <MessageSquareText size={14} aria-hidden="true" />
          <span>Message agent</span>
        </button>

        <button
          className="live-header-action live-ask-action"
          disabled={identity === null}
          type="button"
          onClick={onAsk}
        >
          <Search size={14} aria-hidden="true" />
          <span>Ask about this session</span>
          <kbd>⌘K</kbd>
        </button>
    </ObservatoryHeader>
  );
}
