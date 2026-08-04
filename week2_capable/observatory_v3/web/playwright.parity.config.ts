import { defineConfig } from "@playwright/test"

/**
 * Measured parity gate against the running reference build. Requires the
 * reference on 8791 (with its API on 8787) and the v3 app on 5173 with its
 * backend on 8793. The spec fails, never silently skips, when a claim
 * cannot be measured.
 */
export default defineConfig({
  testDir: "./tests/parity",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
  },
})
