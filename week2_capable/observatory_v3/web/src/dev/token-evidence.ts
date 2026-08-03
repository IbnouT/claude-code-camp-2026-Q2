type EvidenceOrigin = Readonly<{
  file: string
  selector: string
  property: `--${string}` | string
}>

export type TokenEvidence = Readonly<{
  token: `--${string}`
  dark: EvidenceOrigin
  light?: EvidenceOrigin
  aliases?: `--${string}`
  overrides?: readonly EvidenceOrigin[]
}>

const v1Tokens = "observatory/web/src/styles/tokens.css"
const v1Base = "observatory/web/src/styles/base.css"
const v1Header = "observatory/web/src/styles/header.css"
const v1Dialogs = "observatory/web/src/styles/dialogs.css"
const v1Experiments = "observatory/web/src/styles/experiments.css"
const v2Tokens = ["observatory", "v2/web/src/tokens.css"].join("_")

function themes(
  token: `--${string}`,
  property: `--${string}`,
  file = v1Tokens
): TokenEvidence {
  return {
    token,
    dark: { file, selector: ":root", property },
    light: { file, selector: ':root[data-theme="light"]', property },
  }
}

function root(
  token: `--${string}`,
  property: string,
  file = v1Tokens
): TokenEvidence {
  return { token, dark: { file, selector: ":root", property } }
}

function alias(
  token: `--${string}`,
  aliases: `--${string}`,
  property: `--${string}`
): TokenEvidence {
  return {
    token,
    aliases,
    dark: { file: v1Tokens, selector: ":root", property },
    light: {
      file: v1Tokens,
      selector: ':root[data-theme="light"]',
      property,
    },
  }
}

function selector(
  token: `--${string}`,
  file: string,
  sourceSelector: string,
  property: string
): TokenEvidence {
  return {
    token,
    dark: { file, selector: sourceSelector, property },
  }
}

const foundationPairs = [
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
  ["--accent", "--color-cyan"],
  ["--accent-soft", "--color-cyan-soft"],
  ["--success", "--color-green"],
  ["--success-soft", "--color-green-soft"],
  ["--warning", "--color-amber"],
  ["--warning-soft", "--color-amber-soft"],
  ["--danger", "--color-coral"],
  ["--danger-soft", "--color-coral-soft"],
  ["--belief-soft", "--color-violet-soft"],
  ["--map-grid", "--color-map-grid"],
  ["--map-glow", "--color-map-glow"],
  ["--elevation-raised", "--shadow-raised"],
  ["--elevation-popover", "--shadow-popover"],
  ["--focus-ring", "--focus-ring"],
] as const

const mapPairs = [
  ["--map-link", "--color-map-link"],
  ["--map-frontier", "--color-map-frontier"],
  ["--map-vertical", "--color-map-vertical"],
  ["--map-room", "--color-map-room"],
  ["--map-room-line", "--color-map-room-line"],
  ["--map-current", "--color-map-current"],
  ["--map-current-line", "--color-map-current-line"],
  ["--map-temple", "--color-map-temple"],
  ["--map-temple-line", "--color-map-temple-line"],
  ["--map-shop", "--color-map-shop"],
  ["--map-shop-line", "--color-map-shop-line"],
  ["--map-dark", "--color-map-dark"],
  ["--map-dark-line", "--color-map-dark-line"],
  ["--map-route", "--color-map-route"],
  ["--map-route-line", "--color-map-route-line"],
  ["--map-interior", "--color-map-interior"],
  ["--map-interior-line", "--color-map-interior-line"],
  ["--map-underground", "--color-map-underground"],
  ["--map-underground-line", "--color-map-underground-line"],
  ["--map-urban", "--color-map-urban"],
  ["--map-urban-line", "--color-map-urban-line"],
  ["--map-open-land", "--color-map-open-land"],
  ["--map-open-land-line", "--color-map-open-land-line"],
  ["--map-water", "--color-map-water"],
  ["--map-water-line", "--color-map-water-line"],
  ["--map-highland", "--color-map-highland"],
  ["--map-highland-line", "--color-map-highland-line"],
  ["--map-woodland", "--color-map-woodland"],
  ["--map-woodland-line", "--color-map-woodland-line"],
  ["--map-commerce", "--color-map-commerce"],
  ["--map-commerce-line", "--color-map-commerce-line"],
  ["--map-civic", "--color-map-civic"],
  ["--map-civic-line", "--color-map-civic-line"],
  ["--map-sacred", "--color-map-sacred"],
  ["--map-sacred-line", "--color-map-sacred-line"],
  ["--map-special", "--color-map-special"],
  ["--map-special-line", "--color-map-special-line"],
] as const

const rootPairs = [
  ["--terminal-canvas", "--color-terminal-bg"],
  ["--terminal-content", "--color-terminal-text"],
  ["--font-ui", "--font-ui"],
  ["--font-data", "--font-mono"],
  ["--corner-xs", "--radius-xs"],
  ["--corner-sm", "--radius-sm"],
  ["--corner-md", "--radius-md"],
  ["--corner-lg", "--radius-lg"],
  ["--corner-xl", "--radius-xl"],
  ["--space-1", "--space-1"],
  ["--space-2", "--space-2"],
  ["--space-3", "--space-3"],
  ["--space-4", "--space-4"],
  ["--space-5", "--space-5"],
  ["--space-6", "--space-6"],
  ["--space-8", "--space-8"],
] as const

const geometryPairs = [
  ["--header-height", "--header-height"],
  ["--content-gap", "--content-gap"],
  ["--card-padding", "--card-padding"],
  ["--control-height", "--control-height"],
] as const

export const tokenEvidence: readonly TokenEvidence[] = [
  ...foundationPairs.map(([token, property]) => themes(token, property)),
  {
    token: "--belief",
    dark: { file: v1Tokens, selector: ":root", property: "--color-violet" },
    light: {
      file: v2Tokens,
      selector: ':root[data-theme="light"]',
      property: "--color-violet",
    },
  },
  ...mapPairs.map(([token, property]) => themes(token, property, v2Tokens)),
  ...rootPairs.map(([token, property]) => root(token, property)),
  {
    ...themes("--cost", "--color-amber"),
    aliases: "--warning",
  },
  {
    ...themes("--cost-soft", "--color-amber-soft"),
    aliases: "--warning-soft",
  },
  alias("--lifecycle-idle", "--content-quiet", "--color-quiet"),
  alias("--lifecycle-checking", "--warning", "--color-amber"),
  alias("--lifecycle-running", "--accent", "--color-cyan"),
  alias("--lifecycle-succeeded", "--success", "--color-green"),
  alias("--lifecycle-stopped", "--content-muted", "--color-muted"),
  alias("--lifecycle-failed", "--danger", "--color-coral"),
  selector("--type-ui-xs", v1Base, ".eyebrow", "font-size"),
  selector(
    "--type-ui-sm",
    v1Base,
    ".primary-button, .secondary-button",
    "font-size"
  ),
  selector("--type-ui-md", v1Header, ".space-link", "font-size"),
  selector("--type-ui-lg", v1Header, ".brand", "font-size"),
  selector("--type-ui-title", v1Header, ".brand-name strong", "font-size"),
  selector("--type-data-xs", v1Base, ".state-badge", "font-size"),
  selector("--type-data-sm", v1Base, ".eyebrow", "font-size"),
  selector("--type-data-md", v1Base, ".primary-button", "font-size"),
  selector("--type-data-lg", v1Dialogs, ".search-dialog input", "font-size"),
  {
    ...root("--motion-fast", "--motion-fast"),
    overrides: [
      {
        file: v1Tokens,
        selector: "@media (prefers-reduced-motion: reduce) :root",
        property: "--motion-fast",
      },
    ],
  },
  {
    ...root("--motion-normal", "--motion-normal"),
    overrides: [
      {
        file: v1Tokens,
        selector: "@media (prefers-reduced-motion: reduce) :root",
        property: "--motion-normal",
      },
    ],
  },
  ...geometryPairs.map(([token, property]) => ({
    ...root(token, property),
    overrides: [
      {
        file: v1Tokens,
        selector: ':root[data-density="dense"]',
        property,
      },
    ],
  })),
  {
    token: "--layer-base",
    dark: {
      file: v1Experiments,
      selector: ".experiment-lifecycle li::after",
      property: "z-index",
    },
  },
  {
    token: "--layer-raised",
    dark: {
      file: v1Experiments,
      selector: ".experiment-lifecycle li > span",
      property: "z-index",
    },
  },
  {
    token: "--layer-header",
    dark: {
      file: v1Header,
      selector: ".canonical-header",
      property: "z-index",
    },
  },
  {
    token: "--layer-popover",
    dark: {
      file: v1Header,
      selector: ".session-menu",
      property: "z-index",
    },
  },
  {
    token: "--layer-modal",
    dark: {
      file: v1Dialogs,
      selector: ".dialog-backdrop",
      property: "z-index",
    },
  },
]
