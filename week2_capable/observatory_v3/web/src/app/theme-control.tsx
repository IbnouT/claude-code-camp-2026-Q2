import { MoonIcon, SunIcon } from "lucide-react"
import { useEffect, useState } from "react"

type Theme = "dark" | "light"

const themeStorageKey = "boukensha-observatory-theme"

function initialTheme(): Theme {
  const saved = window.localStorage.getItem(themeStorageKey)
  if (saved === "dark" || saved === "light") return saved
  return window.matchMedia?.("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark"
}

function ThemeControl() {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem(themeStorageKey, theme)
  }, [theme])

  const nextTheme = theme === "dark" ? "light" : "dark"

  return (
    <button
      type="button"
      aria-label={`Use ${nextTheme} theme`}
      className="grid size-[34px] flex-none place-items-center rounded-[11px] border border-line bg-surface-raised text-accent outline-none hover:border-line-strong hover:bg-surface-soft focus-visible:border-accent focus-visible:[box-shadow:var(--focus-ring)]"
      onClick={() => setTheme(nextTheme)}
    >
      {theme === "dark" ? (
        <SunIcon aria-hidden="true" className="size-4" />
      ) : (
        <MoonIcon aria-hidden="true" className="size-4" />
      )}
    </button>
  )
}

export { ThemeControl, type Theme }
