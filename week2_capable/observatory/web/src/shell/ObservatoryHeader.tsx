import {
  Activity,
  BookOpen,
  FlaskConical,
  Moon,
  Sun,
  Telescope,
} from "lucide-react";
import type { ReactNode } from "react";
import type { Theme } from "../theme";

export type ObservatorySpace =
  | "live"
  | "sessions"
  | "experiments"
  | "knowledge";

type Destination = {
  href?: string;
  title?: string;
};

type Props = {
  activeSpace: ObservatorySpace;
  children?: ReactNode;
  destinations: Partial<Record<ObservatorySpace, Destination>>;
  theme: Theme;
  onNavigate: (href: string) => void;
  onThemeChange: (theme: Theme) => void;
};

const spaces = [
  { id: "live", label: "Live", icon: Activity },
  { id: "sessions", label: "Sessions", icon: Telescope },
  { id: "experiments", label: "Experiments", icon: FlaskConical },
  { id: "knowledge", label: "Knowledge", icon: BookOpen },
] satisfies Array<{
  id: ObservatorySpace;
  label: string;
  icon: typeof Activity;
}>;

export function ObservatoryHeader({
  activeSpace,
  children,
  destinations,
  theme,
  onNavigate,
  onThemeChange,
}: Props) {
  return (
    <header className="live-header">
      <a className="live-brand" href="/" aria-label="Boukensha Observatory launcher">
        <span className="live-brand-mark" aria-hidden="true">
          <Telescope size={19} />
        </span>
        <span className="live-brand-name">
          <strong>Boukensha</strong>
          <small>Observatory</small>
        </span>
      </a>

      <nav className="live-nav" aria-label="Observatory spaces">
        {spaces.map(({ id, icon: Icon, label }) => {
          const active = id === activeSpace;
          const destination = destinations[id];
          const available = active || destination?.href !== undefined;
          return (
            <button
              aria-current={active ? "page" : undefined}
              disabled={!available}
              className="live-nav-link"
              key={id}
              title={destination?.title}
              type="button"
              onClick={
                destination?.href === undefined
                  ? undefined
                  : () => onNavigate(destination.href!)
              }
            >
              <Icon size={15} aria-hidden="true" />
              <span>{label}</span>
            </button>
          );
        })}
      </nav>

      <div className="live-header-context">
        {children}
        <button
          aria-label={`Use ${theme === "dark" ? "light" : "dark"} theme`}
          className="live-icon-button"
          type="button"
          onClick={() => onThemeChange(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark"
            ? <Sun size={16} aria-hidden="true" />
            : <Moon size={16} aria-hidden="true" />}
        </button>
      </div>
    </header>
  );
}
