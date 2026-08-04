import { expect, test } from "@playwright/test"

const REFERENCE = "http://127.0.0.1:8791"

/**
 * Structural style parity for the Live screen: element pairs that hold
 * regardless of session data, measured on both running stacks. Data
 * bearing regions (landmark counts, rail values) are excluded, their
 * behavior is covered by unit tests over the shared view resource.
 */
const FROZEN_PAIRS: [string, string][] = [
  ["objective", ".live-objective-strip"],
  ["objectiveLabel", ".live-objective-strip > span"],
  ["objectiveTitle", ".live-objective-strip strong"],
  ["rail", ".live-evidence-rail"],
  ["railHeading", ".live-rail-block h2"],
  ["timeline", ".live-causal-timeline"],
  ["timelineHeading", ".live-timeline-heading > small"],
  ["transport", ".live-timeline-transport button"],
  ["jump", ".live-timeline-return"],
  ["scrubTrack", ".live-timeline-track"],
  ["railBlock", ".live-rail-block"],
  ["econCell", ".live-economics-grid > div"],
  ["vitalRow", ".live-vital"],
  ["spendValue", ".live-spend strong"],
  ["roomRect", ".live-map-room rect"],
]

const V3_PAIRS: [string, string][] = [
  ["objective", '[aria-label="Current objective"]'],
  ["objectiveLabel", '[aria-label="Current objective"] > span'],
  ["objectiveTitle", '[aria-label="Current objective"] strong'],
  ["rail", '[aria-label="Live evidence rail"]'],
  ["railHeading", '[aria-label="Live evidence rail"] h2'],
  ["timeline", '[aria-label="Causal timeline"]'],
  [
    "timelineHeading",
    '[aria-label="Causal timeline"] > div:first-child > small',
  ],
  ["transport", '[aria-label="Timeline transport"] button'],
  ["jump", '[aria-label="Jump to live"]'],
  ["scrubTrack", '[aria-label="Causal timeline"] .group'],
  ["railBlock", '[aria-label="Live evidence rail"] section'],
  [
    "econCell",
    '[aria-label="Live evidence rail"] .grid-cols-2 > div',
  ],
  ["vitalRow", '[aria-label="Live evidence rail"] .grid-cols-\\[44px_minmax\\(0\\,1fr\\)_72px\\]'],
  ["spendValue", '[aria-label="Live evidence rail"] section:nth-of-type(3) strong'],
  ["roomRect", "[data-room-id] rect"],
]

/** Values that never depend on retained session data. */
const PROPERTIES: Record<string, string[]> = {
  objective: ["minHeight", "paddingLeft", "paddingRight", "borderBottomWidth"],
  objectiveLabel: ["fontSize", "fontWeight", "letterSpacing", "textTransform"],
  objectiveTitle: ["fontSize", "fontWeight"],
  rail: ["width", "borderLeftWidth", "overflowY"],
  railHeading: ["fontSize", "fontWeight", "letterSpacing", "textTransform"],
  timeline: ["height", "borderTopWidth", "paddingLeft", "paddingTop"],
  timelineHeading: ["fontSize", "fontWeight", "letterSpacing"],
  transport: ["minHeight", "borderRadius", "fontSize", "fontWeight"],
  jump: ["fontSize", "whiteSpace"],
  scrubTrack: ["height", "marginTop", "cursor"],
  railBlock: ["paddingTop", "paddingLeft", "borderBottomWidth", "rowGap"],
  econCell: ["paddingTop", "paddingLeft", "borderRadius", "borderTopWidth"],
  vitalRow: ["gridTemplateColumns", "columnGap", "fontSize"],
  spendValue: ["fontSize", "fontWeight"],
  roomRect: ["WIDTH"],
}

async function measure(
  page: import("@playwright/test").Page,
  url: string,
  pairs: [string, string][]
): Promise<Record<string, string>> {
  await page.goto(url)
  // The rail hydrates last on both stacks, wait for it before measuring.
  const railHeading = pairs.find(([key]) => key === "railHeading")?.[1]
  if (railHeading !== undefined) {
    await page
      .waitForSelector(railHeading, { timeout: 20000 })
      .catch(() => undefined)
  }
  await page.waitForTimeout(800)
  return page.evaluate(
    ({ spec, properties }) => {
      const out: Record<string, string> = {}
      for (const [key, selector] of spec) {
        const el = document.querySelector(selector)
        if (el === null) {
          out[key] = "MISSING"
          continue
        }
        const cs = getComputedStyle(el)
        out[key] = properties[key]
          .map((name) =>
            name === "WIDTH"
              ? `w:${Math.round(el.getBoundingClientRect().width)}`
              : `${name}:${cs[name as keyof CSSStyleDeclaration]}`
          )
          .join(" ")
      }
      return out
    },
    { spec: pairs, properties: PROPERTIES }
  )
}

test("live screen structure matches the reference measurements", async ({
  page,
}) => {
  await page.goto(`${REFERENCE}/`)
  const identity = await page.evaluate(async () => {
    const response = await fetch("/api/sessions")
    const data = (await response.json()) as {
      sessions: { id: string; player_id: string; live: boolean }[]
    }
    const session = data.sessions.find((entry) => entry.live) ?? data.sessions[0]
    return session ? { player: session.player_id, session: session.id } : null
  })
  test.skip(identity === null, "reference has no sessions")
  const frozen = await measure(
    page,
    `${REFERENCE}/live?player=${identity!.player}&session=${identity!.session}`,
    FROZEN_PAIRS
  )
  const v3 = await measure(
    page,
    `/live?player=${identity!.player}&session=${identity!.session}`,
    V3_PAIRS
  )
  for (const [key] of FROZEN_PAIRS) {
    expect(v3[key], key).toBe(frozen[key])
  }
})
