import { Moon, Sun } from "lucide-react";
import type { Theme } from "../theme";

/**
 * The single theme toggle. Used inside the Observatory header and, on its own,
 * on the launcher, which has no header.
 */
export function ThemeControl({
  theme,
  onThemeChange,
}: {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}) {
  return (
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
  );
}
