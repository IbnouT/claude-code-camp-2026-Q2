import { once } from "node:events"
import { readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import { spawn } from "node:child_process"
import { fileURLToPath } from "node:url"

import { chromium, expect } from "@playwright/test"

const packageRoot = fileURLToPath(new URL("..", import.meta.url))
const sourcePath = path.join(packageRoot, "src", "dev", "foundation-review.tsx")
const port = 4175
const baseURL = `http://127.0.0.1:${port}`
const originalMarker = "V3_FOUNDATION_REVIEW_HMR_CHECK"
const refreshedMarker = "V3_FOUNDATION_REVIEW_HMR_REFRESHED"
const probeValue = "preserve-across-hmr"

const delay = (milliseconds) =>
  new Promise((resolve) => {
    setTimeout(resolve, milliseconds)
  })

async function waitForServer(attempt = 0) {
  try {
    const response = await fetch(baseURL)
    if (response.ok) {
      return
    }
  } catch {
    // The development server has not started listening yet.
  }

  if (attempt >= 50) {
    throw new Error(`Vite did not become ready at ${baseURL}`)
  }

  await delay(100)
  await waitForServer(attempt + 1)
}

const viteExecutable = path.join(
  packageRoot,
  "node_modules",
  "vite",
  "bin",
  "vite.js"
)
const server = spawn(
  process.execPath,
  [
    viteExecutable,
    "--host",
    "127.0.0.1",
    "--port",
    String(port),
    "--strictPort",
  ],
  {
    cwd: packageRoot,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  }
)

let browser
let originalSource

try {
  await waitForServer()
  browser = await chromium.launch()
  const page = await browser.newPage()
  await page.goto(`${baseURL}/review`)

  const probe = page.getByRole("textbox", { name: "HMR state probe" })
  await probe.fill(probeValue)
  await page.evaluate(() => {
    window.observatoryHmrProof = {
      documentNode: document,
      rootNode: document.getElementById("root"),
    }
  })

  originalSource = await readFile(sourcePath, "utf8")
  if (!originalSource.includes(originalMarker)) {
    throw new Error(`Expected marker missing from ${sourcePath}`)
  }

  const refreshedSource = originalSource.replace(
    originalMarker,
    refreshedMarker
  )
  await writeFile(sourcePath, refreshedSource)

  await expect(page.getByTestId("foundation-marker")).toHaveText(
    refreshedMarker
  )
  await expect(probe).toHaveValue(probeValue)

  const identity = await page.evaluate(() => ({
    sameDocument: window.observatoryHmrProof?.documentNode === document,
    sameRoot:
      window.observatoryHmrProof?.rootNode === document.getElementById("root"),
  }))

  if (!identity.sameDocument || !identity.sameRoot) {
    throw new Error(
      `Fast Refresh replaced document=${!identity.sameDocument} root=${!identity.sameRoot}`
    )
  }

  console.log(
    "Fast Refresh preserved input state, document identity, and root identity."
  )
} finally {
  if (originalSource !== undefined) {
    await writeFile(sourcePath, originalSource)
  }

  if (browser !== undefined) {
    await browser.close()
  }

  server.kill("SIGTERM")
  if (server.exitCode === null) {
    await Promise.race([once(server, "exit"), delay(2_000)])
  }
}
