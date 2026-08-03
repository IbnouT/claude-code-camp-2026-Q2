import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

const frozenURL = "http://127.0.0.1:8787/"

function session(id: string, playerId: string, index: number, live = false) {
  return {
    capture_status: "complete",
    character: playerId === "player-alpha" ? "Player Alpha" : "Player Beta",
    control_available: live,
    control_state: live ? "ready" : null,
    created_at: "2026-08-03T10:00:00Z",
    ended_at: live ? null : "2026-08-03T10:30:00Z",
    event_count: 20 + index,
    gateway_session_id: `gateway-${id}`,
    goal_count: 2,
    id,
    latest_seq: 20 + index,
    legacy: false,
    live,
    nudge_count: 1,
    objective:
      index === 2 ? "Recover the crystal" : `Objective for session ${index}`,
    player_id: playerId,
    projection_gaps: [],
    projection_status: "available",
    state: live ? "running" : "stopped",
    stop_mode: live ? null : "graceful",
    updated_at: `2026-08-03T10:${String(index).padStart(2, "0")}:00Z`,
  }
}

const alphaSessions = Array.from({ length: 7 }, (_, index) => ({
  ...session(`alpha-session-${index}`, "player-alpha", index, index === 6),
  ...(index === 4 ? { state: "complete" } : {}),
}))
const betaSession = session("beta-session", "player-beta", 8, true)
const sessions = [...alphaSessions, betaSession]

function catalogPage(
  pageSessions = sessions,
  continuationCursor: string | null = null
) {
  const players = [
    { id: "player-alpha", label: "Player Alpha" },
    { id: "player-beta", label: "Player Beta" },
  ]
  return {
    capture_gaps: [],
    completeness: "complete",
    continuation_cursor: continuationCursor,
    players,
    resource_id: "session-catalog",
    resource_version: 1,
    sessions: pageSessions,
    source_cursor: "catalog-cursor-1",
    source_refs: ["gateway"],
  }
}

const catalog = catalogPage()

async function installCatalog(
  page: Page,
  resolve = (url: URL) => {
    const playerId = url.searchParams.get("player_id")
    return playerId === null
      ? catalog
      : catalogPage(sessions.filter((item) => item.player_id === playerId))
  }
) {
  const requests: string[] = []
  await page.route("**/api/v1/sessions?*", async (route) => {
    const url = new URL(route.request().url())
    requests.push(url.toString())
    await route.fulfill({ json: resolve(url), status: 200 })
  })
  return () => [...requests]
}

test("one selected context survives every product space without reloads", async ({
  page,
}, testInfo) => {
  const requests = await installCatalog(page)
  await page.goto(
    "/live?view=activity&player=player-alpha&session=alpha-session-6"
  )

  const shell = await page.getByTestId("application-shell").elementHandle()
  const navigationEntries = await page.evaluate(
    () => performance.getEntriesByType("navigation").length
  )
  const selected = page.getByRole("button", {
    name: /selected context, player alpha, running, alpha-session-6/i,
  })
  await expect(selected).toBeVisible()
  await expect(page.getByText("Live context")).toBeVisible()
  const requestsAfterLoad = requests().length

  // oxlint-disable no-await-in-loop
  for (const space of ["Sessions", "Experiments", "Knowledge"] as const) {
    await page.getByRole("link", { name: space }).click()
    await expect(page).toHaveURL(/player=player-alpha/)
    await expect(page).toHaveURL(/session=alpha-session-6/)
    await expect(selected).toBeVisible()
  }
  // oxlint-enable no-await-in-loop

  const currentShell = await page
    .getByTestId("application-shell")
    .elementHandle()
  expect(
    await page.evaluate(
      ([before, after]) => before === after,
      [shell, currentShell]
    )
  ).toBe(true)
  expect(
    await page.evaluate(() => performance.getEntriesByType("navigation").length)
  ).toBe(navigationEntries)
  expect(requests()).toHaveLength(requestsAfterLoad)

  await page.getByRole("link", { name: "Sessions" }).click()
  await expect(page.getByText("Open Live")).toBeVisible()
  await selected.click()
  await expect(page.getByText("Control available: ready")).toBeVisible()
  await expect(page.getByText("Latest five")).toBeVisible()
  await expect(
    page.getByRole("button", {
      name: /player alpha, stopped.*alpha-session-5/i,
    })
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: /player beta/i })
  ).not.toBeVisible()

  await page.getByRole("button", { name: "Show all sessions" }).click()
  const search = page.getByRole("searchbox", { name: "Search all sessions" })
  await search.fill("crystal")
  await page
    .getByRole("button", {
      name: /player alpha, stopped, recover the crystal.*alpha-session-2/i,
    })
    .click()

  await expect(page).toHaveURL(/player=player-alpha/)
  await expect(page).toHaveURL(/session=alpha-session-2/)
  await expect(
    page.getByRole("button", {
      name: /selected context, player alpha, stopped, alpha-session-2/i,
    })
  ).toBeVisible()
  await expect(page.getByText("View recording")).toBeVisible()

  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("shared-header-context.png"),
  })
  const accessibility = await new AxeBuilder({ page }).analyze()
  expect(accessibility.violations).toEqual([])
})

test("show all consumes every selected-player page beyond fifty", async ({
  page,
}) => {
  const manySessions = Array.from({ length: 55 }, (_, index) =>
    session(
      `alpha-long-session-${String(index).padStart(2, "0")}`,
      "player-alpha",
      index,
      index === 54
    )
  )
  const requests = await installCatalog(page, (url) => {
    const playerId = url.searchParams.get("player_id")
    if (playerId === null) {
      return catalogPage([...manySessions.slice(0, 49), betaSession])
    }
    if (playerId === "player-beta") return catalogPage([betaSession])
    return url.searchParams.get("cursor") === "alpha-page-2"
      ? catalogPage(manySessions.slice(50))
      : catalogPage(manySessions.slice(0, 50), "alpha-page-2")
  })

  await page.goto("/live?player=player-alpha&session=alpha-long-session-54")
  await expect(
    page.getByRole("button", {
      name: /selected context, player alpha, running, alpha-long-session-54/i,
    })
  ).toBeVisible()
  await page
    .getByRole("button", { name: /selected context, player alpha/i })
    .click()
  await page.getByRole("button", { name: "Show all sessions" }).click()
  await expect(page.getByText("Loading remaining sessions…")).toBeHidden()

  const search = page.getByRole("searchbox", { name: "Search all sessions" })
  await search.fill("alpha-long-session-54")
  await expect(
    page.getByRole("button", { name: /alpha-long-session-54/i })
  ).toBeVisible()
  expect(
    requests().some(
      (url) =>
        url.includes("player_id=player-alpha") &&
        url.includes("cursor=alpha-page-2")
    )
  ).toBe(true)
})

test("identity recovery, player choice, detail precedence, and brand retain context", async ({
  page,
}) => {
  await installCatalog(page)

  await page.goto("/live?player=player-alpha")
  await expect(page).toHaveURL(/session=alpha-session-6/)

  await page.goto("/live?player=player-alpha&session=missing-session")
  await expect(page).toHaveURL(/session=alpha-session-6/)

  await page.goto("/live?session=missing-session")
  await expect(page).toHaveURL(/player=player-beta/)
  await expect(page).toHaveURL(/session=beta-session/)

  await page.goto("/live?player=player-alpha&session=beta-session")
  await expect(page).toHaveURL(/session=alpha-session-6/)

  await page.goto(
    "/sessions/beta-session?player=player-alpha&session=alpha-session-2"
  )
  await expect(page).toHaveURL(/player=player-beta/)
  await expect(page).toHaveURL(/session=beta-session/)
  await expect(
    page.getByRole("button", { name: /selected context, player beta/i })
  ).toBeVisible()

  await page.getByRole("link", { name: "Boukensha Observatory" }).click()
  await expect(page).toHaveURL(/\/live/)
  await expect(page).toHaveURL(/player=player-beta/)
  await expect(page).toHaveURL(/session=beta-session/)

  await page
    .getByRole("button", { name: /selected context, player beta/i })
    .click()
  await page
    .getByRole("combobox", { name: "Selected player" })
    .selectOption("player-alpha")
  await expect(page).toHaveURL(/player=player-alpha/)
  await expect(page).toHaveURL(/session=alpha-session-6/)
})

test("narrow product navigation keeps names and passes accessibility", async ({
  page,
}) => {
  await page.setViewportSize({ width: 430, height: 811 })
  await installCatalog(page)
  await page.goto("/live?player=player-alpha&session=alpha-session-6")

  // oxlint-disable no-await-in-loop
  for (const name of ["Live", "Sessions", "Experiments", "Knowledge"]) {
    await expect(page.getByRole("link", { name, exact: true })).toBeVisible()
  }
  // oxlint-enable no-await-in-loop
  const accessibility = await new AxeBuilder({ page }).analyze()
  expect(accessibility.violations).toEqual([])
})

test("all-session search includes derived lifecycle and displayed date", async ({
  page,
}) => {
  await installCatalog(page)
  await page.goto("/sessions?player=player-alpha&session=alpha-session-6")
  await page
    .getByRole("button", { name: /selected context, player alpha/i })
    .click()
  await page.getByRole("button", { name: "Show all sessions" }).click()
  const search = page.getByRole("searchbox", { name: "Search all sessions" })

  await search.fill("succeeded")
  await expect(
    page.getByRole("button", { name: /alpha-session-4/i })
  ).toBeVisible()
  await search.fill("Aug 3")
  await expect(
    page.getByRole("button", { name: /alpha-session-5/i })
  ).toBeVisible()
})

test("selector refresh, keyboard focus, themes, density, and narrow layout remain direct", async ({
  page,
}) => {
  const requests = await installCatalog(page)
  await page.goto("/sessions?player=player-alpha&session=alpha-session-6")
  await expect(
    page.getByRole("button", { name: /selected context, player alpha/i })
  ).toBeVisible()
  const requestsAfterLoad = requests().length

  const selected = page.getByRole("button", {
    name: /selected context, player alpha/i,
  })
  await selected.focus()
  await page.keyboard.press("Enter")
  await expect(
    page.getByRole("dialog", { name: "Player and session context" })
  ).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(selected).toBeFocused()

  await selected.click()
  await page.getByRole("button", { name: "Refresh session catalog" }).click()
  await expect.poll(() => requests().length).toBe(requestsAfterLoad + 2)
  await page.keyboard.press("Escape")

  const themeControl = page.getByRole("button", {
    name: /use (dark|light) theme/i,
  })
  const currentTheme = await page.locator("html").getAttribute("data-theme")
  await themeControl.click()
  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    currentTheme === "dark" ? "light" : "dark"
  )
  await page.evaluate(() => {
    document.documentElement.dataset.density = "dense"
  })
  await expect(page.locator("html")).toHaveAttribute("data-density", "dense")

  await page.setViewportSize({ width: 430, height: 811 })
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth
      )
    )
    .toBe(true)

  await page.evaluate(() => {
    document.body.style.zoom = "2"
  })
  await expect(page.getByTestId("application-header")).toBeVisible()
  await expect(
    page.getByRole("button", { name: /selected context, player alpha/i })
  ).toBeVisible()
})

test("shared header retains the frozen header geometry", async ({
  browser,
  page,
}) => {
  await installCatalog(page)
  const frozenPage = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  })
  await frozenPage.route("**/api/sessions", async (route) => {
    await route.fulfill({
      json: {
        players: [{ id: "parity-player", label: "Parity Player" }],
        sessions: [
          {
            capture_status: "complete",
            character: "Parity Player",
            control_available: true,
            control_state: "running",
            created_at: "2026-08-03T10:00:00Z",
            ended_at: null,
            event_count: 1,
            gateway_session_id: "gateway-parity-session",
            id: "parity-session",
            latest_seq: 1,
            legacy: false,
            live: true,
            player_id: "parity-player",
            state: "running",
            updated_at: "2026-08-03T10:01:00Z",
          },
        ],
        version: 1,
      },
      status: 200,
    })
  })
  await frozenPage.goto(frozenURL, { waitUntil: "networkidle" })
  await frozenPage.locator(".menu-item.watch").click()

  await page.goto("/live?player=player-alpha&session=alpha-session-6")
  const currentHeader = page.getByTestId("application-header")
  const frozenHeader = frozenPage.locator(".live-header")
  const properties = [
    "minHeight",
    "padding",
    "gap",
    "borderBottomWidth",
    "borderBottomStyle",
    "borderBottomColor",
    "zIndex",
  ] as const
  const computed = async (
    locator: typeof currentHeader,
    selected: readonly (typeof properties)[number][]
  ) =>
    locator.evaluate((element, names) => {
      const styles = getComputedStyle(element)
      return Object.fromEntries(names.map((name) => [name, styles[name]]))
    }, selected)

  const [currentValues, frozenValues] = await Promise.all([
    computed(currentHeader, properties),
    computed(frozenHeader, properties),
  ])
  expect(currentValues).toEqual(frozenValues)
  const [currentMark, frozenMark] = await Promise.all([
    page.getByTestId("brand-mark").screenshot(),
    frozenPage.locator(".live-brand-mark").screenshot(),
  ])
  const markPixelDiff = await page.evaluate(
    async ({ current, frozen }) => {
      const decode = async (encoded: string) => {
        const image = new Image()
        image.src = `data:image/png;base64,${encoded}`
        await image.decode()
        const canvas = document.createElement("canvas")
        canvas.width = image.naturalWidth
        canvas.height = image.naturalHeight
        const context = canvas.getContext("2d")
        if (context === null) throw new Error("Canvas context unavailable")
        context.drawImage(image, 0, 0)
        return {
          data: context.getImageData(0, 0, canvas.width, canvas.height).data,
          height: canvas.height,
          width: canvas.width,
        }
      }
      const [currentPixels, frozenPixels] = await Promise.all([
        decode(current),
        decode(frozen),
      ])
      if (
        currentPixels.width !== frozenPixels.width ||
        currentPixels.height !== frozenPixels.height
      ) {
        return {
          differingPixels: Number.POSITIVE_INFINITY,
          height: currentPixels.height,
          width: currentPixels.width,
        }
      }
      let differingPixels = 0
      for (let index = 0; index < currentPixels.data.length; index += 4) {
        const different = [0, 1, 2, 3].some(
          (offset) =>
            Math.abs(
              (currentPixels.data[index + offset] ?? 0) -
                (frozenPixels.data[index + offset] ?? 0)
            ) > 2
        )
        if (different) differingPixels += 1
      }
      return {
        differingPixels,
        height: currentPixels.height,
        width: currentPixels.width,
      }
    },
    {
      current: currentMark.toString("base64"),
      frozen: frozenMark.toString("base64"),
    }
  )
  expect(markPixelDiff).toEqual({
    differingPixels: 0,
    height: 33,
    width: 32,
  })
  await frozenPage.close()
})
