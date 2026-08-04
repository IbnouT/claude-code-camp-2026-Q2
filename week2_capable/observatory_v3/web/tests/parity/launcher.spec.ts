import { expect, test } from "@playwright/test"

const REFERENCE = "http://127.0.0.1:8791"

const FROZEN_PAIRS: [string, string][] = [
  ["title", ".brand h1"],
  ["tagline", ".brand p"],
  ["card", ".menu > section.menu-item:not(.watch)"],
  ["h2", ".menu-item h2"],
  ["chip", ".chip"],
  ["textarea", ".initial-goal textarea"],
  ["go", ".go"],
  ["load", ".menu > section.menu-item:nth-of-type(2)"],
  ["count", ".menu > section.menu-item:nth-of-type(2) h2 > span"],
  ["sigil", ".sigil"],
]

// State-robust: the start and load cards are located by their headings so
// live watch tiles cannot shift the selection.
const V3_PAIRS: [string, string][] = [
  ["title", "main h1"],
  ["tagline", "main header p"],
  ["card", "@start-card"],
  ["h2", "@start-card h2"],
  ["chip", "@start-card h2 span"],
  ["textarea", "main textarea"],
  ["go", "button[type=submit]"],
  ["load", "@load-card"],
  ["count", "@load-card h2 > span"],
  ["sigil", "main button[aria-pressed] > span > span:first-child"],
]

async function measure(
  page: import("@playwright/test").Page,
  url: string,
  pairs: [string, string][]
): Promise<Record<string, string>> {
  await page.goto(url)
  await page.waitForTimeout(1500)
  return page.evaluate((spec) => {
    const bySection = (label: string) =>
      [...document.querySelectorAll("main section")].find((section) =>
        section.querySelector("h2")?.textContent?.includes(label)
      ) ?? null
    const resolve = (selector: string): Element | null => {
      if (selector.startsWith("@start-card")) {
        const card = bySection("START A NEW SESSION")
        const rest = selector.slice("@start-card".length).trim()
        return rest === "" ? card : (card?.querySelector(rest) ?? null)
      }
      if (selector.startsWith("@load-card")) {
        const card = bySection("LOAD A SESSION")
        const rest = selector.slice("@load-card".length).trim()
        return rest === "" ? card : (card?.querySelector(rest) ?? null)
      }
      return document.querySelector(selector)
    }
    const out: Record<string, string> = {}
    for (const [key, selector] of spec) {
      const el = resolve(selector)
      if (el === null) {
        out[key] = "MISSING"
        continue
      }
      const cs = getComputedStyle(el)
      // Text-bearing controls size to their data; width is asserted only on
      // fixed-width structure.
      const fixedWidth = ["title", "card", "load", "textarea", "sigil"]
      const width = fixedWidth.includes(key)
        ? ` w:${Math.round(el.getBoundingClientRect().width)}`
        : ""
      out[key] =
        `${cs.fontSize}/${cs.fontWeight} r:${cs.borderRadius}` +
        ` p:${cs.padding}${width}`
    }
    return out
  }, pairs)
}

test("launcher elements match the reference measurements", async ({ page }) => {
  const frozen = await measure(page, `${REFERENCE}/`, FROZEN_PAIRS)
  const v3 = await measure(page, "/", V3_PAIRS)
  for (const [key] of FROZEN_PAIRS) {
    // The start card may render in a different live state than the reference
    // only if the same session data diverged between reads; both read the
    // same runtime, so measured pairs must agree.
    expect(v3[key], key).toBe(frozen[key])
  }
})
