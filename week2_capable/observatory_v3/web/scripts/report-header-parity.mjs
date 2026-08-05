/**
 * Walk every element of the reference header and the v3 header, closed and
 * with the context panel open, dump every relevant computed property, and
 * write the inventory document. The reference walk is the authority; nothing
 * is hand-picked.
 */
import { chromium } from "@playwright/test"
import { writeFile } from "node:fs/promises"

const REFERENCE = "http://127.0.0.1:8791"
const V3 = "http://localhost:5173"
const FROZEN_THEME_KEY = "boukensha-observatory-theme"
const OUT = new URL(
  "../../../../docs/plans/week2_observ/observatory/launcher/header_element_inventory.md",
  import.meta.url
)

const WALK = `(root) => {
  const PROPS = [
    "display","position","flexDirection","alignItems","justifyContent",
    "gridTemplateColumns","gap","flex","order",
    "width","height","minWidth","maxWidth","padding","margin",
    "borderTopWidth","borderTopColor","borderRadius","boxShadow",
    "backgroundColor","backgroundImage","opacity","overflow",
    "fontSize","fontWeight","fontFamily","letterSpacing","lineHeight",
    "textTransform","textOverflow","whiteSpace","color","textAlign",
    "cursor","outlineWidth","textDecorationLine"
  ]
  const short = (value) => {
    if (value.includes("Inter")) return "ui-font"
    if (value.includes("Menlo") || value.includes("mono")) return "mono-font"
    return value
  }
  const rows = []
  const visit = (el, path) => {
    if (el.nodeType !== 1) return
    const cs = getComputedStyle(el)
    if (cs.display === "none") return
    const record = {}
    for (const p of PROPS) {
      let v = cs[p]
      if (p === "fontFamily") v = short(v)
      if (p === "boxShadow") v = v.replace(/rgba\\(0, 0, 0, 0\\) 0px 0px 0px 0px(, )?/g, "").replace(/^, /, "") || "none"
      if (p === "outlineWidth" && cs.outlineStyle === "none") v = "0px"
      record[p] = v
    }
    const rect = el.getBoundingClientRect()
    rows.push({
      path,
      tag: el.tagName.toLowerCase(),
      classes: (el.getAttribute("class") || "").slice(0, 60),
      text: (el.childNodes.length && el.childNodes[0].nodeType === 3 ? el.childNodes[0].textContent.trim() : "").slice(0, 40),
      aria: el.getAttribute("aria-label") || el.getAttribute("aria-current") || el.getAttribute("aria-disabled") || "",
      box: Math.round(rect.width) + "x" + Math.round(rect.height),
      props: record,
    })
    let index = 0
    for (const child of el.children) {
      visit(child, path + ">" + child.tagName.toLowerCase() + "[" + index + "]")
      index += 1
    }
  }
  visit(root, root.tagName.toLowerCase())
  return rows
}`

async function pinTheme(page, origin, key) {
  await page.goto(origin)
  await page.evaluate((k) => window.localStorage.setItem(k, "dark"), key)
}

async function capture(page, url, rootSelector, openTrigger) {
  await page.goto(url)
  await page.waitForSelector(rootSelector, { timeout: 15000 })
  await page.waitForTimeout(1200)
  const closed = await page.$eval(rootSelector, WALK)
  let panel = []
  let switcher = []
  if (openTrigger) {
    // The reference fills its catalog on a poll; give both pages time to
    // settle before opening, then wait for list rows when the data allows.
    await page.waitForTimeout(3000)
    const trigger = await page.$(openTrigger.trigger)
    if (trigger) {
      // The reference wraps its switcher in a positioning div that v3 does
      // not need; an aligned walk from each trigger root pairs the subtree.
      switcher = await page.$eval(openTrigger.trigger, WALK)
      await trigger.click()
      await page.waitForTimeout(1200)
      const panelHandle = await page.$(openTrigger.panel)
      if (panelHandle) {
        panel = await page.$eval(openTrigger.panel, WALK)
      }
    }
  }
  return { closed, panel, switcher }
}

function table(rows) {
  const interesting = (row) => row.props
  const lines = []
  for (const row of rows) {
    lines.push(
      `#### \`${row.path}\`${row.text ? ` "${row.text}"` : ""}${row.aria ? ` (aria: ${row.aria})` : ""}`
    )
    lines.push("")
    lines.push(`box ${row.box}`)
    lines.push("")
    lines.push("| property | value |")
    lines.push("|---|---|")
    const props = interesting(row)
    for (const [key, value] of Object.entries(props)) {
      lines.push(`| ${key} | \`${value}\` |`)
    }
    lines.push("")
  }
  return lines.join("\n")
}

const browser = await chromium.launch()
const page = await browser.newPage()

await page.goto(`${REFERENCE}/`)
const identity = await page.evaluate(async () => {
  const d = await (await fetch("/api/sessions")).json()
  const s = d.sessions.find((x) => x.live) ?? d.sessions[0]
  return s ? { p: s.player_id, s: s.id } : null
})
if (identity === null) {
  console.error("reference has no sessions")
  process.exit(1)
}

await pinTheme(page, `${REFERENCE}/`, FROZEN_THEME_KEY)
await pinTheme(page, `${V3}/`, "boukensha-observatory-theme")

const frozen = await capture(
  page,
  `${REFERENCE}/live?player=${identity.p}&session=${identity.s}`,
  "header.live-header",
  { trigger: ".live-context-trigger", panel: ".live-context-panel" }
)
const v3 = await capture(
  page,
  `${V3}/live`,
  '[data-testid="application-header"]',
  {
    trigger: '[data-testid="application-header"] [aria-haspopup]',
    panel: '[role="dialog"], [data-testid="application-header"] ~ * [role]',
  }
)
const frozenSessions = await capture(
  page,
  `${REFERENCE}/sessions?player=${identity.p}`,
  "header.live-header",
  null
).catch(() => ({ closed: [], panel: [] }))
const v3Sessions = await capture(
  page,
  `${V3}/sessions`,
  '[data-testid="application-header"]',
  null
)
await browser.close()

function conformance(label, a, b) {
  const lines = [`## ${label}`, ""]
  if (a.length !== b.length) {
    lines.push(
      `Structural note: reference ${a.length} elements, v3 ${b.length}. Rows`,
      "pair in walk order until the shorter side ends; unpaired paths follow.",
      ""
    )
  }
  const size = Math.min(a.length, b.length)
  let same = 0
  let diff = 0
  for (let i = 0; i < size; i += 1) {
    const f = a[i]
    const v = b[i]
    lines.push(
      `### \`${f.path}\`${f.text ? ` "${f.text}"` : ""} ↔ \`${v.path}\`${v.text ? ` "${v.text}"` : ""}`,
      "",
      "| property | frozen | v3 | same |",
      "|---|---|---|---|"
    )
    for (const key of Object.keys(f.props)) {
      if (key === "borderTopColor" && f.props.borderTopWidth === "0px") continue
      const equal = f.props[key] === v.props[key]
      if (equal) same += 1
      else diff += 1
      lines.push(
        `| ${key} | \`${f.props[key]}\` | \`${v.props[key]}\` | ${equal ? "yes" : "NO"} |`
      )
    }
    lines.push("")
  }
  for (let i = size; i < a.length; i += 1) {
    lines.push(
      `- reference only: \`${a[i].path}\`${a[i].text ? ` "${a[i].text}"` : ""}`
    )
  }
  for (let i = size; i < b.length; i += 1) {
    lines.push(
      `- v3 only: \`${b[i].path}\`${b[i].text ? ` "${b[i].text}"` : ""}`
    )
  }
  lines.splice(1, 0, `Properties same: ${same}. Different: ${diff}.`, "")
  lines.push("")
  return lines.join("\n")
}

function diffSection(label, a, b) {
  const lines = [`## Diff, ${label}`, ""]
  if (a.length !== b.length) {
    lines.push(
      `Structural mismatch: reference ${a.length} elements, v3 ${b.length}.`
    )
    lines.push("")
    lines.push("Reference paths:")
    for (const row of a)
      lines.push(`- ${row.path}${row.text ? ` "${row.text}"` : ""}`)
    lines.push("")
    lines.push("v3 paths:")
    for (const row of b)
      lines.push(`- ${row.path}${row.text ? ` "${row.text}"` : ""}`)
    lines.push("")
    return lines.join("\n")
  }
  let count = 0
  for (let i = 0; i < a.length; i += 1) {
    const f = a[i]
    const v = b[i]
    const diffs = []
    for (const key of Object.keys(f.props)) {
      if (key === "borderTopColor" && f.props.borderTopWidth === "0px") continue
      if (["width", "minWidth", "maxWidth"].includes(key)) continue
      if (f.props[key] !== v.props[key])
        diffs.push(`${key}: ref[${f.props[key]}] v3[${v.props[key]}]`)
    }
    if (diffs.length > 0) {
      count += diffs.length
      lines.push(`- \`${f.path}\`${f.text ? ` "${f.text}"` : ""}`)
      for (const d of diffs) lines.push(`  - ${d}`)
    }
  }
  lines.unshift("")
  lines.unshift(`Total property differences: ${count}.`)
  lines.push("")
  return lines.join("\n")
}

const doc = [
  "# Header element inventory",
  "",
  "Generated by `scripts/report-header-parity.mjs`. The reference walk is the",
  "authority: every visible element in the header and the open context panel,",
  "every compared computed property. Regenerate after any header change.",
  "",
  `Reference header elements: ${frozen.closed.length}. Panel elements: ${frozen.panel.length}.`,
  `v3 header elements: ${v3.closed.length}. Panel elements: ${v3.panel.length}.`,
  "",
  diffSection("header closed", frozen.closed, v3.closed),
  diffSection("context panel open", frozen.panel, v3.panel),
  conformance(
    "Conformance, switcher trigger aligned",
    frozen.switcher,
    v3.switcher
  ),
  conformance("Conformance, header on Live", frozen.closed, v3.closed),
  conformance("Conformance, context panel open", frozen.panel, v3.panel),
  conformance(
    "Conformance, header on Sessions",
    frozenSessions.closed,
    v3Sessions.closed
  ),
  "## Reference header, closed",
  "",
  table(frozen.closed),
  "## Reference context panel, open",
  "",
  table(frozen.panel),
  "## v3 header, closed",
  "",
  table(v3.closed),
  "## v3 context panel, open",
  "",
  table(v3.panel),
].join("\n")

await writeFile(OUT, doc)
console.log(
  `written: ${frozen.closed.length}+${frozen.panel.length} reference, ${v3.closed.length}+${v3.panel.length} v3 elements`
)
