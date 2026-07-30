import { useEffect, useState } from "react";
import type { Density, Theme } from "./shellTypes";

const THEME_KEY = "boukensha-observatory-theme";
const DENSITY_KEY = "boukensha-observatory-density";

function storedTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function storedDensity(): Density {
  return window.localStorage.getItem(DENSITY_KEY) === "dense"
    ? "dense"
    : "comfortable";
}

export function usePreferences() {
  const [theme, setTheme] = useState<Theme>(storedTheme);
  const [density, setDensity] = useState<Density>(storedDensity);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.density = density;
    window.localStorage.setItem(DENSITY_KEY, density);
  }, [density]);

  return { theme, setTheme, density, setDensity };
}
