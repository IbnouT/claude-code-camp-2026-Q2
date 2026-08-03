import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

const frozenURL = "http://127.0.0.1:8787/"

test("primitive interactions preserve keyboard, focus, and dismissal behavior", async ({
  page,
}, testInfo) => {
  await page.goto("/")

  const review = page.getByTestId("primitive-review")
  await expect(
    review.getByRole("heading", { name: "Observatory UI primitives" })
  ).toBeVisible()

  const search = review.getByRole("searchbox", { name: "Search sessions" })
  await review.getByRole("button", { name: "Clear search" }).click()
  await expect(search).toHaveValue("")

  const sessionsTab = review.getByRole("tab", { name: "Sessions" })
  await review.getByRole("tab", { name: "Live" }).focus()
  await page.keyboard.press("ArrowRight")
  await page.keyboard.press("Enter")
  await expect(sessionsTab).toHaveAttribute("aria-selected", "true")
  await expect(
    review.getByRole("tabpanel", { name: "Sessions" })
  ).toContainText("Sessions partition selected")

  const collapsible = review.getByRole("button", { name: "Resource detail" })
  await expect(collapsible).toHaveAttribute("aria-expanded", "false")
  await collapsible.click()
  await expect(collapsible).toHaveAttribute("aria-expanded", "true")
  await expect(review.getByText("Bounded resource detail")).toBeVisible()

  const select = review.getByRole("combobox", { name: "Lifecycle state" })
  await select.click()
  await page.getByRole("option", { name: "Succeeded" }).click()
  await expect(select).toContainText("succeeded")

  const popoverTrigger = review.getByRole("button", { name: "Open popover" })
  await popoverTrigger.click()
  await expect(
    page.getByText("The cursor covers every governed partition.")
  ).toBeVisible()
  await review
    .getByRole("heading", { name: "Observatory UI primitives" })
    .click()
  await expect(
    page.getByText("The cursor covers every governed partition.")
  ).not.toBeVisible()

  const menuTrigger = review.getByRole("button", {
    name: "Primitive actions",
  })
  await menuTrigger.click()
  await expect(
    page.getByRole("menuitem", { name: "Inspect resource" })
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Unavailable action" })
  ).toHaveAttribute("aria-disabled", "true")
  await page.keyboard.press("Escape")
  await expect(menuTrigger).toBeFocused()

  const tooltipTrigger = review.getByRole("button", { name: "Focus tooltip" })
  await tooltipTrigger.focus()
  await page.keyboard.press("Shift+Tab")
  await page.keyboard.press("Tab")
  await expect(tooltipTrigger).toBeFocused()
  await expect(page.getByRole("tooltip")).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page.getByRole("tooltip")).not.toBeVisible()

  const dialogTrigger = review.getByRole("button", { name: "Open dialog" })
  await dialogTrigger.click()
  await expect(page.getByRole("dialog")).toBeVisible()
  const dialogAccessibility = await new AxeBuilder({ page }).analyze()
  expect(dialogAccessibility.violations).toEqual([])

  await page.keyboard.press("Escape")
  await expect(page.getByRole("dialog")).not.toBeVisible()
  await expect(dialogTrigger).toBeFocused()

  await review.screenshot({
    path: testInfo.outputPath("primitive-review.png"),
  })
})

test("retained action primitive matches the live frozen action across themes and densities", async ({
  browser,
  page,
}) => {
  test.setTimeout(60_000)
  const frozenContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  })
  const frozenPage = await frozenContext.newPage()
  await frozenPage.addInitScript(() => {
    window.localStorage.setItem("boukensha-observatory-theme", "light")
  })
  await frozenPage.goto(frozenURL, { waitUntil: "networkidle" })
  await page.goto("/")
  const themeControls = page.getByTestId("token-gallery")
  await themeControls.getByRole("button", { name: "Light" }).click()
  await expect(page.getByTestId("primitive-review")).toBeVisible()
  await page.mouse.move(0, 0)

  const frozenButton = frozenPage.locator(".go")
  const currentButton = page.getByTestId("retained-action-specimen")
  await frozenButton.evaluate((element) => {
    if (element instanceof HTMLButtonElement) {
      element.disabled = false
    }
    const container = element.closest(".menu-item")
    container?.classList.remove("disabled")
    if (container instanceof HTMLElement) {
      container.style.backgroundColor = "white"
    }
  })
  await currentButton.evaluate((element) => {
    const container = element.closest('[data-slot="card"]')
    if (container instanceof HTMLElement) {
      container.style.backgroundColor = "white"
    }
  })
  const retainedProperties = [
    "width",
    "height",
    "padding",
    "borderRadius",
    "fontFamily",
    "fontSize",
    "fontWeight",
    "lineHeight",
    "backgroundColor",
    "boxShadow",
    "opacity",
    "transitionProperty",
    "transitionDuration",
    "transitionTimingFunction",
    "gap",
    "letterSpacing",
    "textTransform",
  ] as const
  const computedValues = async (
    locator: typeof frozenButton,
    properties: readonly (typeof retainedProperties)[number][]
  ) =>
    locator.evaluate((element, selectedProperties) => {
      const style = getComputedStyle(element)
      return Object.fromEntries(
        selectedProperties.map((property) => [property, style[property]])
      )
    }, properties)

  const [frozenValues, currentValues] = await Promise.all([
    computedValues(frozenButton, retainedProperties),
    computedValues(currentButton, retainedProperties),
  ])
  expect(currentValues).toEqual(frozenValues)

  const [frozenBorder, currentBorder] = await Promise.all([
    frozenButton.evaluate((element) => {
      const style = getComputedStyle(element)
      return {
        color: style.borderColor,
        style: style.borderStyle,
        width: style.borderWidth,
      }
    }),
    currentButton.evaluate((element) => {
      const style = getComputedStyle(element)
      return {
        color: style.borderColor,
        style: style.borderStyle,
        width: style.borderWidth,
      }
    }),
  ])
  expect(frozenBorder).toEqual({
    color: "rgba(104, 225, 220, 0.3)",
    style: "solid",
    width: "1px",
  })
  expect(currentBorder).toEqual({
    color: "rgba(104, 225, 220, 0.3)",
    style: "solid",
    width: "1px",
  })

  for (const theme of ["Dark", "Light"] as const) {
    await frozenPage.evaluate((selectedTheme) => {
      window.localStorage.setItem(
        "boukensha-observatory-theme",
        selectedTheme.toLowerCase()
      )
    }, theme)
    await frozenPage.reload({ waitUntil: "networkidle" })
    await themeControls.getByRole("button", { name: theme }).click()

    for (const density of ["normal", "dense"] as const) {
      await page.evaluate((selectedDensity) => {
        document.documentElement.dataset.density = selectedDensity
      }, density)
      await frozenButton.evaluate((element) => {
        if (element instanceof HTMLButtonElement) {
          element.disabled = false
        }
        const container = element.closest(".menu-item")
        container?.classList.remove("disabled")
        if (container instanceof HTMLElement) {
          container.style.backgroundColor = "white"
        }
      })
      await currentButton.evaluate((element) => {
        const container = element.closest('[data-slot="card"]')
        if (container instanceof HTMLElement) {
          container.style.backgroundColor = "white"
        }
      })

      const [frozenMatrixValues, currentMatrixValues, actionBorderToken] =
        await Promise.all([
          computedValues(frozenButton, retainedProperties),
          computedValues(currentButton, retainedProperties),
          page.evaluate(() =>
            getComputedStyle(document.documentElement)
              .getPropertyValue("--action-border")
              .trim()
          ),
        ])
      expect(currentMatrixValues).toEqual(frozenMatrixValues)
      expect(actionBorderToken).toBe("rgb(104 225 220 / 30%)")
      expect(
        await currentButton.evaluate((element) => {
          const style = getComputedStyle(element)
          return {
            color: style.borderColor,
            style: style.borderStyle,
            width: style.borderWidth,
          }
        })
      ).toEqual(frozenBorder)

      await Promise.all([
        frozenButton.evaluate((element) => {
          element.style.color = "transparent"
        }),
        currentButton.evaluate((element) => {
          element.style.color = "transparent"
        }),
      ])
      const [frozenScreenshot, currentScreenshot] = await Promise.all([
        frozenButton.screenshot(),
        currentButton.screenshot(),
      ])
      expect(currentScreenshot).toEqual(frozenScreenshot)
      await Promise.all([
        frozenButton.evaluate((element) => {
          element.style.removeProperty("color")
        }),
        currentButton.evaluate((element) => {
          element.style.removeProperty("color")
        }),
      ])
    }
  }

  await page.evaluate(() => {
    document.documentElement.dataset.density = "normal"
  })
  await themeControls.getByRole("button", { name: "Light" }).click()

  const safeForeground = await currentButton.evaluate(
    (element) => getComputedStyle(element).color
  )
  expect(safeForeground).toBe("rgb(5, 8, 11)")

  await currentButton.hover()
  await expect(currentButton).toHaveAttribute("data-hovered", "")
  await currentButton.focus()
  await expect(currentButton).toBeFocused()
  await page.keyboard.down("Space")
  await expect(currentButton).toHaveAttribute("data-pressed", "")
  await page.keyboard.up("Space")
  const buttonAccessibility = await new AxeBuilder({ page })
    .include('[data-testid="retained-action-specimen"]')
    .analyze()
  expect(buttonAccessibility.violations).toEqual([])

  await currentButton.evaluate((element) => {
    element.style.color = "transparent"
  })
  await expect(currentButton).toHaveScreenshot(
    "retained-action-button-frozen.png",
    { maxDiffPixels: 30 }
  )

  await currentButton.evaluate((element) => {
    element.style.removeProperty("color")
  })

  const frozenLivePage = await frozenContext.newPage()
  await frozenLivePage.addInitScript(() => {
    window.localStorage.setItem("boukensha-observatory-theme", "light")
  })
  await frozenLivePage.goto(frozenURL, { waitUntil: "networkidle" })
  await frozenLivePage.locator(".menu-item.watch").click()
  await expect(frozenLivePage.locator(".live-icon-button")).toBeVisible()

  const parityPairs = [
    {
      current: page.getByTestId("retained-icon-button-specimen"),
      frozen: frozenLivePage.locator(".live-icon-button").first(),
      name: "retained-icon-button.png",
      properties: retainedProperties,
    },
    {
      current: page.getByTestId("retained-status-badge-specimen"),
      frozen: frozenLivePage.locator(".live-posture-pill").first(),
      name: "retained-status-badge.png",
      properties: retainedProperties,
    },
    {
      current: page.getByTestId("retained-disclosure-specimen"),
      frozen: frozenLivePage.locator(".live-map-dock-toggle").first(),
      name: "retained-disclosure.png",
      properties: retainedProperties,
    },
  ] as const

  // oxlint-disable no-await-in-loop
  for (const pair of parityPairs) {
    const [frozenStyle, currentStyle] = await Promise.all([
      computedValues(pair.frozen, pair.properties),
      computedValues(pair.current, pair.properties),
    ])
    expect(currentStyle, pair.name).toEqual(frozenStyle)
    if (pair.name === "retained-status-badge.png") {
      expect(
        await pair.current.evaluate(
          (element) => getComputedStyle(element).color
        )
      ).toBe("rgb(18, 32, 43)")
    }
    await Promise.all(
      [pair.frozen, pair.current].map((locator) =>
        locator.evaluate((element, dimensions) => {
          element.style.position = "fixed"
          element.style.inset = "0 auto auto 0"
          element.style.zIndex = "2147483647"
          element.style.width = dimensions.width
          element.style.height = dimensions.height
          document.body.append(element)
        }, frozenStyle)
      )
    )
    if (pair.name === "retained-disclosure.png") {
      await Promise.all([
        pair.frozen.evaluate((element) => {
          element.style.backgroundColor = "white"
          element.style.color = "transparent"
        }),
        pair.current.evaluate((element) => {
          element.style.backgroundColor = "white"
          element.style.color = "transparent"
        }),
      ])
    }
    if (pair.name === "retained-status-badge.png") {
      await Promise.all([
        pair.frozen.evaluate((element) => {
          element.style.borderRadius = "0"
          element.style.color = "transparent"
        }),
        pair.current.evaluate((element) => {
          element.style.borderRadius = "0"
          element.style.color = "transparent"
        }),
      ])
    }
    if (pair.name === "retained-icon-button.png") {
      await Promise.all([
        pair.frozen.evaluate((element) => {
          element.style.borderRadius = "0"
          for (const child of element.children) {
            if (child instanceof HTMLElement || child instanceof SVGElement) {
              child.style.visibility = "hidden"
            }
          }
        }),
        pair.current.evaluate((element) => {
          element.style.borderRadius = "0"
          for (const child of element.children) {
            if (child instanceof HTMLElement || child instanceof SVGElement) {
              child.style.visibility = "hidden"
            }
          }
        }),
      ])
    }
    await expect(pair.current).toHaveScreenshot(pair.name)
  }
  // oxlint-enable no-await-in-loop

  await frozenLivePage.locator(".live-ask-action").click()
  const frozenInput = frozenLivePage.locator(".live-ask-query input")
  const currentInput = page.getByTestId("retained-input-specimen")
  await Promise.all([frozenInput.focus(), currentInput.focus()])
  const [frozenInputStyle, currentInputStyle] = await Promise.all([
    computedValues(frozenInput, retainedProperties),
    computedValues(currentInput, retainedProperties),
  ])
  expect(currentInputStyle).toEqual(frozenInputStyle)
  await Promise.all([
    frozenInput.evaluate((element) => {
      element.style.position = "fixed"
      element.style.inset = "0 auto auto 0"
      element.style.width = "586.766px"
      element.style.height = "39px"
      element.style.zIndex = "2147483647"
      element.style.caretColor = "transparent"
      element.style.borderRadius = "0"
      element.style.borderColor = "var(--accent)"
      element.removeAttribute("placeholder")
    }),
    currentInput.evaluate((element) => {
      element.style.position = "fixed"
      element.style.inset = "0 auto auto 0"
      element.style.width = "586.766px"
      element.style.height = "39px"
      element.style.zIndex = "2147483647"
      element.style.caretColor = "transparent"
      element.style.borderRadius = "0"
      element.style.borderColor = "var(--accent)"
      element.removeAttribute("placeholder")
      for (
        let ancestor = element.parentElement;
        ancestor !== null;
        ancestor = ancestor.parentElement
      ) {
        ancestor.style.overflow = "visible"
      }
      document.body.append(element)
    }),
  ])
  await expect(currentInput).toHaveScreenshot("retained-input.png")

  await page.getByRole("button", { name: "Open retained dialog" }).click()
  const frozenDialog = frozenLivePage.locator(".live-ask-dialog")
  const currentDialog = page.getByTestId("retained-dialog-specimen")
  const dialogProperties = retainedProperties.filter(
    (property) => property !== "height"
  )
  const [frozenDialogStyle, currentDialogStyle] = await Promise.all([
    computedValues(frozenDialog, dialogProperties),
    computedValues(currentDialog, dialogProperties),
  ])
  expect(currentDialogStyle).toEqual(frozenDialogStyle)
  await Promise.all([
    frozenDialog.evaluate((element) => {
      if (element.parentElement instanceof HTMLElement) {
        element.parentElement.style.backgroundColor = "white"
      }
      element.style.height = "172px"
      for (const child of element.children) {
        if (child instanceof HTMLElement) child.style.visibility = "hidden"
      }
    }),
    currentDialog.evaluate((element) => {
      if (element.parentElement instanceof HTMLElement) {
        element.parentElement.style.backgroundColor = "white"
      }
      element.style.height = "172px"
      for (const child of element.children) {
        if (child instanceof HTMLElement) child.style.visibility = "hidden"
      }
    }),
  ])
  await expect(currentDialog).toHaveScreenshot("retained-dialog.png")

  const frozenExperimentPage = await frozenContext.newPage()
  await frozenExperimentPage.addInitScript(() => {
    window.localStorage.setItem("boukensha-observatory-theme", "light")
  })
  await frozenExperimentPage.goto(`${frozenURL}experiments`, {
    waitUntil: "networkidle",
  })
  const frozenTab = frozenExperimentPage
    .locator('.experiment-tabs button[aria-current="page"]')
    .first()
  const currentTab = page.getByTestId("retained-tab-specimen")
  const [frozenTabStyle, currentTabStyle] = await Promise.all([
    computedValues(frozenTab, retainedProperties),
    computedValues(currentTab, retainedProperties),
  ])
  expect(currentTabStyle).toEqual(frozenTabStyle)
  expect(
    await currentTab.evaluate((element) => getComputedStyle(element).color)
  ).toBe("rgb(5, 8, 11)")
  await Promise.all([
    frozenTab.evaluate((element) => {
      element.style.position = "fixed"
      element.style.inset = "0 auto auto 0"
      element.style.width = "93.5px"
      element.style.height = "46px"
      element.style.zIndex = "2147483647"
      element.style.color = "transparent"
      element.style.fontSize = "0"
      element.style.border = "0"
      element.style.borderBottom = "2px solid var(--color-cyan)"
      element.style.backgroundColor = "white"
      element.style.borderRadius = "0"
      for (const child of element.children) {
        if (child instanceof HTMLElement || child instanceof SVGElement) {
          child.style.visibility = "hidden"
        }
      }
      document.body.append(element)
    }),
    currentTab.evaluate((element) => {
      element.style.position = "fixed"
      element.style.inset = "0 auto auto 0"
      element.style.width = "93.5px"
      element.style.height = "46px"
      element.style.zIndex = "2147483647"
      element.style.color = "transparent"
      element.style.fontSize = "0"
      element.style.border = "0"
      element.style.borderBottom = "2px solid var(--accent)"
      element.style.backgroundColor = "white"
      element.style.borderRadius = "0"
      for (const child of element.children) {
        if (child instanceof HTMLElement || child instanceof SVGElement) {
          child.style.visibility = "hidden"
        }
      }
      document.body.append(element)
    }),
  ])
  await expect(currentTab).toHaveScreenshot("retained-tab.png")

  await frozenContext.close()
})
