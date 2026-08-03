import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

const frozenURL = "http://127.0.0.1:8787/"

const frozenGroups = {
  foundation: [
    ["--canvas", "--color-bg"],
    ["--surface", "--color-surface"],
    ["--surface-raised", "--color-raised"],
    ["--surface-soft", "--color-soft"],
    ["--overlay", "--color-overlay"],
    ["--content-primary", "--color-text"],
    ["--content-muted", "--color-muted"],
    ["--content-quiet", "--color-quiet"],
    ["--line", "--color-line"],
    ["--line-strong", "--color-line-strong"],
  ],
  intent: [
    ["--accent", "--color-cyan"],
    ["--accent-soft", "--color-cyan-soft"],
    ["--success", "--color-green"],
    ["--success-soft", "--color-green-soft"],
    ["--warning", "--color-amber"],
    ["--warning-soft", "--color-amber-soft"],
    ["--danger", "--color-coral"],
    ["--danger-soft", "--color-coral-soft"],
    ["--belief", "--color-violet"],
    ["--cost", "--color-amber"],
    ["--cost-soft", "--color-amber-soft"],
  ],
  mapNavigation: [
    ["--map-link", "--color-map-link"],
    ["--map-frontier", "--color-map-frontier"],
    ["--map-vertical", "--color-map-vertical"],
  ],
  mapFills: [
    ["--map-room", "--color-map-room"],
    ["--map-current", "--color-map-current"],
    ["--map-route", "--color-map-route"],
    ["--map-water", "--color-map-water"],
    ["--map-special", "--color-map-special"],
  ],
  mapLines: [
    ["--map-room-line", "--color-map-room-line"],
    ["--map-current-line", "--color-map-current-line"],
    ["--map-route-line", "--color-map-route-line"],
    ["--map-water-line", "--color-map-water-line"],
    ["--map-special-line", "--color-map-special-line"],
  ],
  typographyAndElevation: [
    ["--font-data", "--font-mono"],
    ["--elevation-popover", "--shadow-popover"],
  ],
} as const

const expected = {
  dark: {
    lifecycle: ["#596775", "#eac06a", "#68e1dc", "#8bdfa9", "#ff8178"],
    typeSizes: ["10px", "12px", "13.5px", "15px", "15px"],
    spacing: ["4px", "8px", "12px", "16px", "20px"],
    radii: ["6px", "8px", "10px", "12px", "16px"],
    geometry: ["62px", "14px", "16px", "38px"],
    focus: "rgba(104, 225, 220, 0.22) 0px 0px 0px 3px",
    accent: "rgb(104, 225, 220)",
  },
  light: {
    lifecycle: ["#8394a2", "#9a6f00", "#0c8f88", "#1f9256", "#d3454f"],
    typeSizes: ["10px", "12px", "13.5px", "15px", "15px"],
    spacing: ["4px", "8px", "12px", "16px", "20px"],
    radii: ["6px", "8px", "10px", "12px", "16px"],
    geometry: ["62px", "14px", "16px", "38px"],
    focus: "rgba(12, 143, 136, 0.2) 0px 0px 0px 3px",
    accent: "rgb(12, 143, 136)",
  },
} as const

async function customProperties(page: Page, properties: readonly string[]) {
  return page.evaluate((names) => {
    const styles = getComputedStyle(document.documentElement)
    return Object.fromEntries(
      names.map((name) => [name, styles.getPropertyValue(name).trim()])
    )
  }, properties)
}

async function computedStyle(
  page: Page,
  selector: string,
  property: keyof CSSStyleDeclaration
) {
  return page
    .locator(selector)
    .first()
    .evaluate(
      (element, selectedProperty) =>
        getComputedStyle(element)[selectedProperty] as string,
      property
    )
}

for (const theme of ["dark", "light"] as const) {
  test(`${theme} values preserve frozen source and rendered semantics`, async ({
    browser,
    page,
  }) => {
    const frozenPage = await browser.newPage({
      viewport: { width: 1440, height: 900 },
    })
    await frozenPage.goto(frozenURL, { waitUntil: "domcontentloaded" })
    await frozenPage.evaluate((selectedTheme) => {
      document.documentElement.dataset.theme = selectedTheme
    }, theme)

    await page.goto("/")
    if (theme === "light") {
      await page.getByRole("button", { name: "Light" }).click()
    }

    await Promise.all(
      Object.entries(frozenGroups).map(async ([category, pairs]) => {
        const [current, frozen] = await Promise.all([
          customProperties(
            page,
            pairs.map(([currentName]) => currentName)
          ),
          customProperties(
            frozenPage,
            pairs.map(([, frozenName]) => frozenName)
          ),
        ])
        for (const [currentName, frozenName] of pairs) {
          expect(
            current[currentName],
            `${category}: ${currentName} from ${frozenName}`
          ).toBe(frozen[frozenName])
        }
      })
    )

    const lifecycle = await customProperties(page, [
      "--lifecycle-idle",
      "--lifecycle-checking",
      "--lifecycle-running",
      "--lifecycle-succeeded",
      "--lifecycle-failed",
    ])
    expect(Object.values(lifecycle)).toEqual(expected[theme].lifecycle)

    const typeSizes = await Promise.all(
      [
        "--type-ui-xs",
        "--type-ui-sm",
        "--type-ui-md",
        "--type-ui-lg",
        "--type-ui-title",
      ].map((token) =>
        computedStyle(page, `[data-token="${token}"]`, "fontSize")
      )
    )
    expect(typeSizes).toEqual(expected[theme].typeSizes)

    const spacing = await Promise.all(
      ["--space-1", "--space-2", "--space-3", "--space-4", "--space-5"].map(
        (token) =>
          computedStyle(page, `[data-specimen-for="${token}"]`, "width")
      )
    )
    expect(spacing).toEqual(expected[theme].spacing)

    const radii = await Promise.all(
      [
        "--corner-xs",
        "--corner-sm",
        "--corner-md",
        "--corner-lg",
        "--corner-xl",
      ].map((token) =>
        computedStyle(page, `[data-token="${token}"]`, "borderRadius")
      )
    )
    expect(radii).toEqual(expected[theme].radii)

    const geometry = await Promise.all(
      [
        ["--header-height", "height"],
        ["--content-gap", "width"],
        ["--card-padding", "width"],
        ["--control-height", "height"],
      ].map(([token, property]) =>
        computedStyle(
          page,
          `[data-specimen-for="${token}"]`,
          property as keyof CSSStyleDeclaration
        )
      )
    )
    expect(geometry).toEqual(expected[theme].geometry)

    expect(
      await computedStyle(
        page,
        '[data-token="--motion-fast"]',
        "transitionDuration"
      )
    ).toBe("0.12s")
    expect(
      await computedStyle(
        page,
        '[data-token="--motion-normal"]',
        "transitionDuration"
      )
    ).toBe("0.18s")

    await Promise.all(
      (
        [
          ["--layer-base", "0"],
          ["--layer-raised", "1"],
          ["--layer-header", "30"],
          ["--layer-popover", "80"],
          ["--layer-modal", "100"],
        ] as const
      ).map(async ([token, value]) => {
        expect(
          await computedStyle(page, `[data-token="${token}"]`, "zIndex")
        ).toBe(value)
      })
    )

    const focus = page.getByTestId("focus-specimen")
    await focus.focus()
    await page.keyboard.press("Tab")
    await page.keyboard.press("Shift+Tab")
    await expect(focus).toBeFocused()
    await expect
      .poll(() =>
        focus.evaluate((element) => element.matches(":focus-visible"))
      )
      .toBe(true)
    await page.waitForTimeout(200)
    const focusStyles = await focus.evaluate((element) => {
      const styles = getComputedStyle(element)
      return { borderColor: styles.borderColor, boxShadow: styles.boxShadow }
    })
    expect(focusStyles).toEqual({
      borderColor: expected[theme].accent,
      boxShadow: expected[theme].focus,
    })

    const currentBody = await page.locator("body").evaluate((element) => {
      const styles = getComputedStyle(element)
      return { color: styles.color, fontFamily: styles.fontFamily }
    })
    const frozenBody = await frozenPage.locator("body").evaluate((element) => {
      const styles = getComputedStyle(element)
      return { color: styles.color, fontFamily: styles.fontFamily }
    })
    expect(currentBody).toEqual(frozenBody)
    await frozenPage.close()
  })

  test(`${theme} token gallery has no unexpected visual change`, async ({
    page,
  }) => {
    await page.goto("/")
    if (theme === "light") {
      await page.getByRole("button", { name: "Light" }).click()
    }

    const gallery = page.getByTestId("token-gallery")
    await expect(gallery).toHaveScreenshot(`token-gallery-${theme}.png`, {
      animations: "disabled",
    })

    const accessibility = await new AxeBuilder({ page })
      .include('[data-testid="token-gallery"]')
      .analyze()
    expect(accessibility.violations).toEqual([])
  })
}
