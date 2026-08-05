import { expect, test } from "@playwright/test"

const REFERENCE = "http://127.0.0.1:8791"

/** Every compared computed property. Width and height are data-driven. */
const PROPS = [
  "fontSize",
  "fontWeight",
  "letterSpacing",
  "textTransform",
  "color",
  "backgroundColor",
  "borderRadius",
  "borderTopWidth",
  "borderTopColor",
  "padding",
  "gap",
  "boxShadow",
] as const

const FROZEN_PAIRS: [string, string][] = [
  ["header", "header.live-header"],
  ["brand", ".live-brand"],
  ["brandMark", ".live-brand-mark"],
  ["brandStrong", ".live-brand-name strong"],
  ["brandSmall", ".live-brand-name small"],
  ["navActive", '.live-nav-link[aria-current="page"]'],
  ["navIdle", ".live-nav-link:not([aria-current])"],
  ["ctxTrigger", ".live-context-trigger"],
  ["ctxStrong", ".live-context-trigger strong"],
  ["ctxId", ".live-context-id"],
  ["msgBtn", ".live-message-action"],
  ["askBtn", ".live-ask-action"],
  ["askKbd", ".live-ask-action kbd"],
  ["themeBtn", ".live-icon-button"],
]

const V3_PAIRS: [string, string][] = [
  ["header", '[data-testid="application-header"]'],
  ["brand", '[data-testid="application-header"] > a'],
  ["brandMark", '[data-testid="brand-mark"]'],
  ["brandStrong", '[data-testid="application-header"] > a strong'],
  ["brandSmall", '[data-testid="application-header"] > a small'],
  ["navActive", 'nav a[aria-current="page"]'],
  ["navIdle", "nav a:not([aria-current])"],
  ["ctxTrigger", '[data-testid="application-header"] [aria-haspopup]'],
  ["ctxStrong", '[data-testid="application-header"] [aria-haspopup] strong'],
  ["ctxId", "[data-context-id]"],
  ["msgBtn", '[data-header-action="message"]'],
  ["askBtn", '[data-header-action="ask"]'],
  ["askKbd", '[data-header-action="ask"] kbd'],
  [
    "themeBtn",
    '[data-testid="application-header"] button[aria-label*="theme"]',
  ],
]

/**
 * Declared differences. Each entry carries its reason; anything not listed
 * must be identical.
 */
const DECLARED: Record<string, string> = {
  "askBtn.opacity": "ask is honestly disabled until the Live experience lands",
  "msgBtn.opacity": "message disable state follows control availability",
}

function normalize(prop: string, value: string): string {
  if (prop === "boxShadow") {
    return value
      .replace(/rgba\(0, 0, 0, 0\) 0px 0px 0px 0px(, )?/g, "")
      .replace(/^, /, "")
  }
  return value
}

async function extract(
  page: import("@playwright/test").Page,
  url: string,
  rootSelector: string,
  pairs: [string, string][]
): Promise<Record<string, Record<string, string> | "MISSING">> {
  await page.goto(url)
  await page.waitForSelector(rootSelector, { timeout: 10_000 })
  await page.waitForTimeout(1200)
  return page.evaluate(
    ({ selectorPairs, props }) => {
      const out: Record<string, Record<string, string> | "MISSING"> = {}
      for (const [key, selector] of selectorPairs) {
        const el = document.querySelector(selector)
        if (el === null) {
          out[key] = "MISSING"
          continue
        }
        const cs = getComputedStyle(el)
        const record: Record<string, string> = {}
        for (const prop of props) {
          record[prop] = cs[prop as keyof CSSStyleDeclaration] as string
        }
        out[key] = record
      }
      return out
    },
    { selectorPairs: pairs, props: [...PROPS] }
  )
}

test("application header matches the reference, every element and property", async ({
  page,
}) => {
  await page.goto(`${REFERENCE}/`)
  const identity = await page.evaluate(async () => {
    const response = await fetch("/api/sessions")
    const catalog = await response.json()
    const session =
      catalog.sessions.find((item: { live: boolean }) => item.live) ??
      catalog.sessions[0]
    return session === undefined
      ? null
      : { player: session.player_id, session: session.id }
  })
  test.fail(identity === null, "reference catalog has no sessions to measure")
  if (identity === null) return

  const frozen = await extract(
    page,
    `${REFERENCE}/live?player=${identity.player}&session=${identity.session}`,
    "header.live-header",
    FROZEN_PAIRS
  )
  const v3 = await extract(
    page,
    "/live",
    '[data-testid="application-header"]',
    V3_PAIRS
  )

  const diffs: string[] = []
  for (const [key] of FROZEN_PAIRS) {
    const f = frozen[key]
    const v = v3[key]
    if (f === "MISSING" || v === "MISSING") {
      diffs.push(
        `${key}: frozen=${f === "MISSING" ? "MISSING" : "ok"} v3=${v === "MISSING" ? "MISSING" : "ok"}`
      )
      continue
    }
    for (const prop of PROPS) {
      if (prop === "borderTopColor" && f.borderTopWidth === "0px") continue
      if (DECLARED[`${key}.${prop}`] !== undefined) continue
      const expected = normalize(prop, f[prop])
      const actual = normalize(prop, v[prop])
      if (expected !== actual) {
        diffs.push(`${key}.${prop}: frozen[${expected}] v3[${actual}]`)
      }
    }
  }
  expect(diffs, diffs.join("\n")).toEqual([])
})
