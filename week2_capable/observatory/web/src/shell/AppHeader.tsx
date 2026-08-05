import {
  MessageSquareText,
  Search,
} from "lucide-react";
import type {
  Catalog,
  Session,
} from "../contracts";
import type { LiveRouteIdentity } from "../routes";
import type { Theme } from "../theme";
import {
  ContextSwitcher,
  type ContextState,
} from "./ContextSwitcher";
import {
  ObservatoryHeader,
  type ObservatorySpace,
} from "./ObservatoryHeader";

type Destination = {
  href?: string;
  title?: string;
};

type Props = {
  activeSpace: ObservatorySpace;
  askDisabled?: boolean;
  catalog: Catalog | null;
  contextState: ContextState;
  destinations: Partial<Record<ObservatorySpace, Destination>>;
  identity: LiveRouteIdentity | null;
  messageAvailable?: boolean;
  theme: Theme;
  onAsk: () => void;
  onLeave?: () => void;
  onMessage?: () => void;
  onNavigate: (href: string) => void;
  onOpenSession?: (session: Session) => void;
  onRequestStop?: () => void;
  onThemeChange: (theme: Theme) => void;
  onViewAll: () => void;
};

export function AppHeader({
  activeSpace,
  askDisabled = false,
  catalog,
  contextState,
  destinations,
  identity,
  messageAvailable = false,
  theme,
  onAsk,
  onLeave,
  onMessage,
  onNavigate,
  onOpenSession,
  onRequestStop,
  onThemeChange,
  onViewAll,
}: Props) {
  return (
    <ObservatoryHeader
      activeSpace={activeSpace}
      destinations={destinations}
      theme={theme}
      onNavigate={onNavigate}
      onThemeChange={onThemeChange}
    >
        {identity !== null ? (
          <ContextSwitcher
            catalog={catalog}
            identity={identity}
            state={contextState}
            onLeave={onLeave}
            onNavigate={onNavigate}
            onOpenSession={onOpenSession}
            onRequestStop={onRequestStop}
            onViewAll={onViewAll}
          />
        ) : null}

        {onMessage === undefined ? null : (
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
        )}

        <button
          className="live-header-action live-ask-action"
          disabled={askDisabled}
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
