import type { Preview } from "@storybook/react-vite"
import { useEffect, type ReactNode } from "react"

import "../src/index.css"

function ThemeBoundary({
  children,
  density,
  theme,
}: {
  children: ReactNode
  density: "dense" | "normal"
  theme: "dark" | "light"
}) {
  useEffect(() => {
    const root = document.documentElement
    root.dataset.theme = theme
    root.dataset.density = density
    root.classList.toggle("dark", theme === "dark")

    return () => {
      delete root.dataset.theme
      delete root.dataset.density
      root.classList.remove("dark")
    }
  }, [density, theme])

  return (
    <div data-density={density}>
      <div className="min-h-80 bg-canvas p-6 text-content-primary">
        {children}
      </div>
    </div>
  )
}

const preview: Preview = {
  decorators: [
    (Story, context) => {
      const theme = context.globals.theme === "light" ? "light" : "dark"
      const density = context.globals.density === "dense" ? "dense" : "normal"

      return (
        <ThemeBoundary theme={theme} density={density}>
          <Story />
        </ThemeBoundary>
      )
    },
  ],
  globalTypes: {
    theme: {
      description: "Observatory color theme",
      defaultValue: "dark",
      toolbar: {
        icon: "paintbrush",
        items: ["dark", "light"],
      },
    },
    density: {
      description: "Observatory content density",
      defaultValue: "normal",
      toolbar: {
        icon: "zoom",
        items: ["normal", "dense"],
      },
    },
  },
  parameters: {
    a11y: {
      config: {
        rules: [
          { id: "landmark-one-main", enabled: false },
          { id: "page-has-heading-one", enabled: false },
          { id: "region", enabled: false },
        ],
      },
      test: "error",
    },
    controls: {
      expanded: true,
    },
    layout: "fullscreen",
  },
}

export default preview
