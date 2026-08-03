import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

declare global {
  interface Window {
    observatoryDevelopmentRouter?: {
      navigate: (options: {
        to: "/sessions/$sessionId"
        params: { sessionId: string }
      }) => Promise<void>
    }
    observatoryRoutePreparation?: {
      promise: Promise<void>
      resolve: () => void
    }
  }
}

test("typed internal navigation preserves the document and shell", async ({
  page,
}, testInfo) => {
  await page.goto("/live?view=activity")
  await expect(page.getByRole("heading", { name: "Live" })).toBeVisible()
  await expect(page.getByTestId("validated-route-state")).toHaveText(
    "view=activity"
  )

  const shell = await page.getByTestId("application-shell").elementHandle()
  const navigationEntries = await page.evaluate(
    () => performance.getEntriesByType("navigation").length
  )
  const transitionStarted = await page.evaluate(() => performance.now())

  await page.getByRole("link", { name: "Sessions" }).click()
  await expect(page).toHaveURL(/\/sessions\?page=1&state=all$/)
  await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible()
  await expect(page.getByTestId("route-content")).toBeFocused()

  const transitionMilliseconds = await page.evaluate(
    (started) => performance.now() - started,
    transitionStarted
  )
  const currentShell = await page
    .getByTestId("application-shell")
    .elementHandle()
  const sameShell = await page.evaluate(
    ([before, after]) => before === after,
    [shell, currentShell]
  )

  expect(sameShell).toBe(true)
  expect(
    await page.evaluate(() => performance.getEntriesByType("navigation").length)
  ).toBe(navigationEntries)
  await testInfo.attach("route-transition.json", {
    body: JSON.stringify(
      {
        documentReloads: 0,
        shellRemounts: 0,
        transitionMilliseconds,
      },
      null,
      2
    ),
    contentType: "application/json",
  })

  await page.getByRole("link", { name: "Knowledge" }).click()
  await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Knowledge" })).toHaveAttribute(
    "aria-current",
    "page"
  )
  await page.goBack()
  await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible()
  await page.goForward()
  await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible()

  await page.reload()
  await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible()
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("persistent-shell.png"),
  })

  const accessibility = await new AxeBuilder({ page }).analyze()
  expect(accessibility.violations).toEqual([])
})

test("deep links validate search, parameters, errors, and not-found state", async ({
  page,
}) => {
  await page.goto("/sessions?state=unknown&page=-2")
  await expect(page.getByTestId("validated-route-state")).toHaveText(
    "state=all;page=1"
  )

  await page.goto("/sessions/session-42")
  await expect(page.getByRole("heading", { name: "Session" })).toBeVisible()
  await expect(page.getByTestId("validated-route-state")).toHaveText(
    "sessionId=session-42"
  )
  await expect(page.getByRole("link", { name: "Sessions" })).toHaveAttribute(
    "aria-current",
    "page"
  )
  await expect(page.getByRole("link", { name: "Live" })).not.toHaveAttribute(
    "aria-current"
  )
  await expect(
    page.getByRole("link", { name: "Experiments" })
  ).not.toHaveAttribute("aria-current")
  await expect(
    page.getByRole("link", { name: "Knowledge" })
  ).not.toHaveAttribute("aria-current")

  await page.goto("/sessions/INVALID!")
  await expect(
    page.getByRole("heading", { name: "Route unavailable" })
  ).toBeVisible()

  await page.goto("/not-a-route")
  await expect(
    page.getByRole("heading", { name: "Route not found" })
  ).toBeVisible()
})

test("routed pending, parameter error, and recovery preserve exact shell identity", async ({
  page,
}) => {
  await page.goto("/sessions/session-42")
  await expect(page.getByRole("heading", { name: "Session" })).toBeVisible()

  const shell = await page.getByTestId("application-shell").elementHandle()
  const routeContent = await page.getByTestId("route-content").elementHandle()

  await page.evaluate(async () => {
    await window.observatoryDevelopmentRouter?.navigate({
      to: "/sessions/$sessionId",
      params: { sessionId: "INVALID!" },
    })
  })
  await expect(
    page.getByRole("heading", { name: "Route unavailable" })
  ).toBeVisible()
  await expect(page.getByTestId("route-content")).toBeFocused()

  let currentShell = await page.getByTestId("application-shell").elementHandle()
  let currentRouteContent = await page
    .getByTestId("route-content")
    .elementHandle()
  expect(
    await page.evaluate(
      ([beforeShell, afterShell, beforeContent, afterContent]) =>
        beforeShell === afterShell && beforeContent === afterContent,
      [shell, currentShell, routeContent, currentRouteContent]
    )
  ).toBe(true)

  await page.evaluate(async () => {
    await window.observatoryDevelopmentRouter?.navigate({
      to: "/sessions/$sessionId",
      params: { sessionId: "session-84" },
    })
  })
  await expect(page.getByRole("heading", { name: "Session" })).toBeVisible()
  await expect(page.getByTestId("validated-route-state")).toHaveText(
    "sessionId=session-84"
  )
  await expect(page.getByTestId("route-content")).toBeFocused()

  currentShell = await page.getByTestId("application-shell").elementHandle()
  currentRouteContent = await page.getByTestId("route-content").elementHandle()
  expect(
    await page.evaluate(
      ([beforeShell, afterShell, beforeContent, afterContent]) =>
        beforeShell === afterShell && beforeContent === afterContent,
      [shell, currentShell, routeContent, currentRouteContent]
    )
  ).toBe(true)

  await page.getByRole("link", { name: "Live" }).click()
  await expect(page.getByRole("heading", { name: "Live" })).toBeVisible()
  await page.evaluate(() => {
    let resolvePreparation = () => {}
    const promise = new Promise<void>((resolve) => {
      resolvePreparation = resolve
    })
    window.observatoryRoutePreparation = {
      promise,
      resolve: resolvePreparation,
    }
  })
  await page.getByRole("link", { name: "Sessions" }).click()
  await expect(
    page.getByRole("heading", { name: "Loading route" })
  ).toBeVisible()

  currentShell = await page.getByTestId("application-shell").elementHandle()
  currentRouteContent = await page.getByTestId("route-content").elementHandle()
  expect(
    await page.evaluate(
      ([beforeShell, afterShell, beforeContent, afterContent]) =>
        beforeShell === afterShell && beforeContent === afterContent,
      [shell, currentShell, routeContent, currentRouteContent]
    )
  ).toBe(true)

  await page.evaluate(() => {
    window.observatoryRoutePreparation?.resolve()
    delete window.observatoryRoutePreparation
  })
  await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible()
  await page.evaluate(async () => {
    await window.observatoryDevelopmentRouter?.navigate({
      to: "/sessions/$sessionId",
      params: { sessionId: "session-42" },
    })
  })
  await expect(page.getByRole("heading", { name: "Session" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Sessions" })).toHaveAttribute(
    "aria-current",
    "page"
  )
  await expect(page.getByRole("link", { name: "Live" })).not.toHaveAttribute(
    "aria-current"
  )

  currentShell = await page.getByTestId("application-shell").elementHandle()
  currentRouteContent = await page.getByTestId("route-content").elementHandle()
  expect(
    await page.evaluate(
      ([beforeShell, afterShell, beforeContent, afterContent]) =>
        beforeShell === afterShell && beforeContent === afterContent,
      [shell, currentShell, routeContent, currentRouteContent]
    )
  ).toBe(true)
})

test("keyboard navigation moves focus into the selected route", async ({
  page,
}) => {
  await page.goto("/live")
  await page.getByRole("link", { name: "Live" }).focus()
  await expect(page.getByRole("link", { name: "Live" })).toBeFocused()
  await page.keyboard.press("Tab")
  await expect(page.getByRole("link", { name: "Sessions" })).toBeFocused()
  await page.keyboard.press("Enter")

  await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible()
  await expect(page.getByTestId("route-content")).toBeFocused()
})

test("development review is routed inside the persistent shell", async ({
  page,
}) => {
  await page.goto("/review")
  await expect(
    page.getByRole("heading", { name: "Observatory architecture" })
  ).toBeVisible()
  await expect(page.getByRole("link", { name: "Review" })).toHaveAttribute(
    "aria-current",
    "page"
  )
  await expect(page.getByTestId("application-shell")).toBeVisible()
  await expect(page.getByTestId("token-gallery")).toHaveJSProperty(
    "clientWidth",
    1184
  )

  const accessibility = await new AxeBuilder({ page }).analyze()
  expect(accessibility.violations).toEqual([])
})
