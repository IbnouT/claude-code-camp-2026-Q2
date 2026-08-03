import { createReadStream } from "node:fs"
import { mkdir, readFile, stat } from "node:fs/promises"
import { createServer } from "node:http"
import path from "node:path"
import { fileURLToPath } from "node:url"

import AxeBuilder from "@axe-core/playwright"
import { chromium } from "@playwright/test"

const packageRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  ".."
)
const staticRoot = path.join(packageRoot, "storybook-static")
const screenshotRoot = path.join(packageRoot, "test-results", "storybook")
const port = 6007
const baseURL = `http://127.0.0.1:${port}`

const contentTypes = new Map([
  [".css", "text/css"],
  [".html", "text/html"],
  [".js", "text/javascript"],
  [".json", "application/json"],
  [".svg", "image/svg+xml"],
  [".woff2", "font/woff2"],
])

function staticPath(requestPath) {
  const pathname = decodeURIComponent(new URL(requestPath, baseURL).pathname)
  const requestedPath = pathname === "/" ? "/index.html" : pathname
  const resolved = path.resolve(staticRoot, `.${requestedPath}`)

  if (
    resolved !== staticRoot &&
    !resolved.startsWith(`${staticRoot}${path.sep}`)
  ) {
    return undefined
  }
  return resolved
}

const server = createServer(async (request, response) => {
  const resolved = staticPath(request.url ?? "/")
  if (resolved === undefined) {
    response.writeHead(403).end()
    return
  }

  try {
    const metadata = await stat(resolved)
    if (!metadata.isFile()) {
      response.writeHead(404).end()
      return
    }
    response.writeHead(200, {
      "Content-Type":
        contentTypes.get(path.extname(resolved)) ?? "application/octet-stream",
    })
    createReadStream(resolved).pipe(response)
  } catch (error) {
    if (error instanceof Error && "code" in error && error.code === "ENOENT") {
      response.writeHead(404).end()
      return
    }
    response.writeHead(500).end()
  }
})

await new Promise((resolve, reject) => {
  server.once("error", reject)
  server.listen(port, "127.0.0.1", resolve)
})

const browser = await chromium.launch()

try {
  await mkdir(screenshotRoot, { recursive: true })
  const index = JSON.parse(
    await readFile(path.join(staticRoot, "index.json"), "utf8")
  )
  const stories = Object.values(index.entries).filter(
    (entry) => entry.type === "story"
  )

  if (stories.length === 0) {
    throw new Error(
      "The Storybook build contains no directly selectable stories"
    )
  }

  const reviewModes = [
    { density: "normal", theme: "dark" },
    { density: "dense", theme: "light" },
  ]

  await Promise.all(
    stories.flatMap((story) =>
      reviewModes.map(async ({ density, theme }) => {
        const context = await browser.newContext({
          viewport: { width: 1280, height: 800 },
        })
        const page = await context.newPage()
        await page.goto(
          `${baseURL}/iframe.html?id=${story.id}&viewMode=story&globals=theme:${theme};density:${density}`,
          {
            waitUntil: "networkidle",
          }
        )
        await page.locator("#storybook-root").waitFor()
        await page.waitForFunction(
          ({ expectedDensity, expectedTheme }) =>
            document.documentElement.dataset.theme === expectedTheme &&
            document.documentElement.dataset.density === expectedDensity,
          { expectedDensity: density, expectedTheme: theme }
        )
        const controlHeight = await page.evaluate(() =>
          getComputedStyle(document.documentElement)
            .getPropertyValue("--control-height")
            .trim()
        )
        const expectedControlHeight = density === "dense" ? "34px" : "38px"
        if (controlHeight !== expectedControlHeight) {
          throw new Error(
            `${story.title} / ${story.name}: ${density} resolved --control-height ${controlHeight}, expected ${expectedControlHeight}`
          )
        }
        if (theme === "dark" && density === "normal") {
          await page.screenshot({
            fullPage: true,
            path: path.join(screenshotRoot, `${story.id}-dark-normal.png`),
          })
        }
        if (story.name === "Button States" && theme === "light") {
          await page.locator("#storybook-root").screenshot({
            path: path.join(screenshotRoot, "controls-light-dense.png"),
          })
        }

        const accessibility = await new AxeBuilder({ page })
          .disableRules(["landmark-one-main", "page-has-heading-one", "region"])
          .analyze()
        if (accessibility.violations.length > 0) {
          const affectedMarkup = await Promise.all(
            accessibility.violations.flatMap((violation) =>
              violation.nodes.map((node) =>
                page
                  .locator(node.target[0])
                  .evaluate((element) => element.innerHTML)
              )
            )
          )
          const summary = accessibility.violations
            .map(
              (violation) =>
                `${violation.id}: ${violation.nodes.length} affected node(s) at ${violation.nodes
                  .flatMap((node) => node.target)
                  .join(
                    ", "
                  )} (${violation.nodes.map((node) => node.html).join(" | ")})`
            )
            .join(", ")
          throw new Error(
            `${story.title} / ${story.name} / ${theme} / ${density}: ${summary}; children: ${affectedMarkup.join(" | ")}`
          )
        }
        await context.close()
      })
    )
  )

  console.log(
    `Storybook accessibility passed (${stories.length} selectable stories across ${reviewModes.length} theme and density modes).`
  )
} finally {
  await browser.close()
  await new Promise((resolve) => server.close(resolve))
}
