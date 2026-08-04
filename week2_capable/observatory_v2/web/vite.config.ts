import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const proxy = {
  "/api/v1": "http://127.0.0.1:8793",
  "/api/sessions/start": "http://127.0.0.1:8792",
  "^/api/sessions/[^/]+/stop$": "http://127.0.0.1:8792",
  "/api": "http://127.0.0.1:8787",
};

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
  server: {
    host: "127.0.0.1",
    port: 8791,
    strictPort: true,
    proxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 8791,
    strictPort: true,
    proxy,
  },
});
