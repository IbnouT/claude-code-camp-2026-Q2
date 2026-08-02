import { defineConfig, devices } from "@playwright/test"

const browserPort = 4174
const baseURL = `http://127.0.0.1:${browserPort}`

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${browserPort} --strictPort`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
  },
})
