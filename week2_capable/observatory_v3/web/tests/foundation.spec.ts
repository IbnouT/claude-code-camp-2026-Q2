import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

test("development foundation renders and passes axe", async ({
  page,
}, testInfo) => {
  await page.goto("/review")

  await expect(
    page.getByRole("heading", { name: "Observatory architecture" })
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Backend contract baseline" })
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "B9 bounded browser-ready path" })
  ).toBeVisible()
  await expect(page.getByText("65 unrelated sessions")).toBeVisible()
  await expect(page.getByTestId("browser-ready")).toHaveAttribute(
    "data-browser-ready-ms",
    /\d+\.\d+/
  )

  const probe = page.getByRole("textbox", { name: "HMR state probe" })
  await probe.fill("browser state")
  await expect(probe).toHaveValue("browser state")

  const accessibility = await new AxeBuilder({ page }).analyze()
  expect(accessibility.violations).toEqual([])

  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("foundation-desktop.png"),
  })

  await page.setViewportSize({ width: 430, height: 811 })
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth
      )
    )
    .toBe(true)
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("foundation-narrow.png"),
  })
})
