import { fileURLToPath } from "node:url"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const sourceDirectory = fileURLToPath(new URL("./src", import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": sourceDirectory,
    },
  },
  server: {
    proxy: {
      "/api": {
        // Local review backend; started by the documented review command.
        target: "http://127.0.0.1:8793",
        changeOrigin: true,
      },
    },
  },
})
