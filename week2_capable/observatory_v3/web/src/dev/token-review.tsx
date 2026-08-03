import { useState, type CSSProperties, type ReactNode } from "react"

import { tokenEvidence } from "./token-evidence"

type TokenName = `--${string}`
type ColorToken = Readonly<{ label: string; token: TokenName }>

const foundationColors = [
  ["Canvas", "--canvas"],
  ["Surface", "--surface"],
  ["Raised surface", "--surface-raised"],
  ["Soft surface", "--surface-soft"],
  ["Overlay", "--overlay"],
  ["Primary content", "--content-primary"],
  ["Muted content", "--content-muted"],
  ["Quiet content", "--content-quiet"],
  ["Line", "--line"],
  ["Strong line", "--line-strong"],
] as const

const intentColors = [
  ["Accent", "--accent"],
  ["Accent soft", "--accent-soft"],
  ["Success", "--success"],
  ["Success soft", "--success-soft"],
  ["Warning", "--warning"],
  ["Warning soft", "--warning-soft"],
  ["Danger", "--danger"],
  ["Danger soft", "--danger-soft"],
  ["Belief", "--belief"],
  ["Belief soft", "--belief-soft"],
  ["Cost", "--cost"],
  ["Cost soft", "--cost-soft"],
] as const

const lifecycleColors = [
  ["Idle", "--lifecycle-idle"],
  ["Checking", "--lifecycle-checking"],
  ["Running", "--lifecycle-running"],
  ["Succeeded", "--lifecycle-succeeded"],
  ["Stopped", "--lifecycle-stopped"],
  ["Failed", "--lifecycle-failed"],
] as const

const mapNavigationColors = [
  ["Grid", "--map-grid"],
  ["Glow", "--map-glow"],
  ["Link", "--map-link"],
  ["Frontier", "--map-frontier"],
  ["Vertical", "--map-vertical"],
] as const

const mapFillColors = [
  ["Room", "--map-room"],
  ["Current", "--map-current"],
  ["Temple", "--map-temple"],
  ["Shop", "--map-shop"],
  ["Dark", "--map-dark"],
  ["Route", "--map-route"],
  ["Interior", "--map-interior"],
  ["Underground", "--map-underground"],
  ["Urban", "--map-urban"],
  ["Open land", "--map-open-land"],
  ["Water", "--map-water"],
  ["Highland", "--map-highland"],
  ["Woodland", "--map-woodland"],
  ["Commerce", "--map-commerce"],
  ["Civic", "--map-civic"],
  ["Sacred", "--map-sacred"],
  ["Special", "--map-special"],
] as const

const mapLineColors = mapFillColors.map(
  ([label, token]) => [`${label} line`, `${token}-line` as TokenName] as const
)

const typeTokens = [
  ["UI extra small", "--type-ui-xs"],
  ["UI small", "--type-ui-sm"],
  ["UI medium", "--type-ui-md"],
  ["UI large", "--type-ui-lg"],
  ["UI title", "--type-ui-title"],
  ["Data extra small", "--type-data-xs"],
  ["Data small", "--type-data-sm"],
  ["Data medium", "--type-data-md"],
  ["Data large", "--type-data-lg"],
] as const

const spacingTokens = [
  "--space-1",
  "--space-2",
  "--space-3",
  "--space-4",
  "--space-5",
  "--space-6",
  "--space-8",
] as const

const radiusTokens = [
  "--corner-xs",
  "--corner-sm",
  "--corner-md",
  "--corner-lg",
  "--corner-xl",
] as const

const geometryTokens = [
  ["Header height", "--header-height", "height"],
  ["Content gap", "--content-gap", "width"],
  ["Card padding", "--card-padding", "width"],
  ["Control height", "--control-height", "height"],
] as const

const layerTokens = [
  ["Base", "--layer-base"],
  ["Raised", "--layer-raised"],
  ["Header", "--layer-header"],
  ["Popover", "--layer-popover"],
  ["Modal", "--layer-modal"],
] as const

function toColorTokens(
  entries: readonly (readonly [string, TokenName])[]
): readonly ColorToken[] {
  return entries.map(([label, token]) => ({ label, token }))
}

function ColorSwatches({
  colors,
  testId,
}: {
  colors: readonly ColorToken[]
  testId: string
}) {
  return (
    <div
      data-testid={testId}
      className="grid grid-cols-2 gap-ob-2 sm:grid-cols-3 lg:grid-cols-6"
    >
      {colors.map(({ label, token }) => (
        <div
          key={token}
          className="overflow-hidden rounded-md border border-line bg-surface"
          data-token={token}
        >
          <div
            aria-hidden="true"
            className="h-12 border-b border-line"
            style={{ background: `var(${token})` }}
          />
          <div className="px-ob-2 py-ob-2">
            <div className="text-(length:--type-ui-sm) font-semibold">
              {label}
            </div>
            <code className="mt-1 block font-mono text-(length:--type-data-xs) text-content-muted">
              {token}
            </code>
          </div>
        </div>
      ))}
    </div>
  )
}

function ReviewSection({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  const id = `token-${title.toLowerCase().replaceAll(" ", "-")}`
  return (
    <section
      aria-labelledby={id}
      className="rounded-lg border border-line bg-surface p-ob-4"
    >
      <h3 id={id} className="mb-ob-3 text-(length:--type-ui-md) font-semibold">
        {title}
      </h3>
      {children}
    </section>
  )
}

export function TokenReviewGallery() {
  const [theme, setTheme] = useState<"dark" | "light">(
    document.documentElement.dataset.theme === "light" ? "light" : "dark"
  )

  function selectTheme(nextTheme: "dark" | "light") {
    setTheme(nextTheme)
    if (nextTheme === "light") {
      document.documentElement.dataset.theme = "light"
    } else {
      delete document.documentElement.dataset.theme
    }
  }

  return (
    <section
      aria-labelledby="token-gallery-title"
      data-testid="token-gallery"
      data-theme-review={theme}
      className="border-b border-line py-ob-8"
    >
      <div className="flex flex-col gap-ob-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-(length:--type-ui-xs) font-bold tracking-[0.13em] text-content-primary uppercase">
            Frozen visual values
          </p>
          <h2
            id="token-gallery-title"
            className="mt-ob-1 text-(length:--type-ui-title) font-semibold"
          >
            Observatory semantic tokens
          </h2>
          <p className="mt-ob-2 max-w-3xl text-(length:--type-ui-sm) leading-5 text-content-muted">
            {tokenEvidence.length} mapped tokens preserve the exact dark, light,
            alias, and responsive override evidence from the frozen source.
          </p>
        </div>
        <fieldset className="flex w-fit rounded-md border border-line bg-surface-raised p-1">
          <legend className="sr-only">Review theme</legend>
          {(["dark", "light"] as const).map((option) => (
            <button
              key={option}
              aria-pressed={theme === option}
              className="rounded-sm px-ob-3 py-ob-2 text-(length:--type-ui-sm) font-semibold text-content-muted transition-colors duration-[var(--motion-fast)] hover:text-content-primary focus-visible:[box-shadow:var(--focus-ring)] focus-visible:outline-none aria-pressed:bg-accent-soft aria-pressed:text-content-primary"
              onClick={() => selectTheme(option)}
              type="button"
            >
              {option[0].toUpperCase() + option.slice(1)}
            </button>
          ))}
        </fieldset>
      </div>

      <div className="mt-ob-5 grid gap-ob-4">
        <ReviewSection title="Surfaces and content">
          <ColorSwatches
            colors={toColorTokens(foundationColors)}
            testId="foundation-colors"
          />
        </ReviewSection>

        <ReviewSection title="Intent and lifecycle">
          <div className="grid gap-ob-3">
            <ColorSwatches
              colors={toColorTokens(intentColors)}
              testId="intent-colors"
            />
            <ColorSwatches
              colors={toColorTokens(lifecycleColors)}
              testId="lifecycle-colors"
            />
          </div>
        </ReviewSection>

        <ReviewSection title="Map states">
          <div className="grid gap-ob-3">
            <ColorSwatches
              colors={toColorTokens(mapNavigationColors)}
              testId="map-navigation-colors"
            />
            <ColorSwatches
              colors={toColorTokens(mapFillColors)}
              testId="map-fill-colors"
            />
            <ColorSwatches
              colors={toColorTokens(mapLineColors)}
              testId="map-line-colors"
            />
          </div>
        </ReviewSection>

        <ReviewSection title="Typography">
          <div className="grid gap-ob-3 lg:grid-cols-2">
            <div
              className="rounded-md border border-line bg-surface-raised p-ob-4"
              data-token="--font-ui"
              style={{ fontFamily: "var(--font-ui)" }}
            >
              {typeTokens.slice(0, 5).map(([label, token]) => (
                <p
                  key={token}
                  className="mt-ob-1"
                  data-token={token}
                  style={{ fontSize: `var(${token})` }}
                >
                  {label} · {token}
                </p>
              ))}
            </div>
            <div
              className="rounded-md border border-line p-ob-4"
              data-token="--font-data"
              style={{
                background: "var(--terminal-canvas)",
                color: "var(--terminal-content)",
                fontFamily: "var(--font-data)",
              }}
            >
              {typeTokens.slice(5).map(([label, token]) => (
                <p
                  key={token}
                  className="mt-ob-1"
                  data-token={token}
                  style={{ fontSize: `var(${token})` }}
                >
                  {label} · {token}
                </p>
              ))}
            </div>
          </div>
        </ReviewSection>

        <ReviewSection title="Geometry and elevation">
          <div className="grid gap-ob-5 lg:grid-cols-2">
            <div className="grid gap-ob-2">
              {spacingTokens.map((token) => (
                <div
                  key={token}
                  className="flex items-center gap-ob-3"
                  data-token={token}
                >
                  <div
                    aria-hidden="true"
                    className="h-2 rounded-full bg-accent"
                    data-specimen-for={token}
                    style={{ width: `var(${token})` }}
                  />
                  <code className="font-mono text-(length:--type-data-xs) text-content-muted">
                    {token}
                  </code>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-ob-3">
              {radiusTokens.map((token) => (
                <div
                  key={token}
                  className="grid size-16 place-items-center border border-line-strong bg-surface-raised font-mono text-(length:--type-data-xs) text-content-muted"
                  data-token={token}
                  style={{ borderRadius: `var(${token})` }}
                >
                  {token}
                </div>
              ))}
            </div>
            {(["--elevation-raised", "--elevation-popover"] as const).map(
              (token) => (
                <div
                  key={token}
                  className="rounded-lg border border-line bg-surface-raised p-ob-4"
                  data-token={token}
                  style={{ boxShadow: `var(${token})` }}
                >
                  <code className="font-mono text-(length:--type-data-xs)">
                    {token}
                  </code>
                </div>
              )
            )}
            <div className="grid gap-ob-2 sm:col-span-2 sm:grid-cols-4">
              {geometryTokens.map(([label, token, dimension]) => (
                <div
                  key={token}
                  className="overflow-hidden rounded-md border border-line bg-surface-soft"
                  data-token={token}
                >
                  <div
                    className="max-w-full bg-accent-soft"
                    data-specimen-for={token}
                    style={{ [dimension]: `var(${token})` } as CSSProperties}
                  />
                  <code className="block p-ob-2 font-mono text-(length:--type-data-xs)">
                    {label} · {token}
                  </code>
                </div>
              ))}
            </div>
          </div>
        </ReviewSection>

        <ReviewSection title="Interaction and layers">
          <div className="grid gap-ob-3 lg:grid-cols-3">
            <button
              className="h-[var(--control-height)] rounded-md border border-line-strong bg-accent-soft px-ob-4 text-(length:--type-ui-sm) font-bold text-content-primary transition-colors duration-[var(--motion-fast)] focus-visible:border-accent focus-visible:[box-shadow:var(--focus-ring)] focus-visible:outline-none"
              data-testid="focus-specimen"
              data-token="--focus-ring"
              type="button"
            >
              Focus specimen
            </button>
            {(["--motion-fast", "--motion-normal"] as const).map((token) => (
              <div
                key={token}
                className="rounded-md border border-line bg-surface-raised p-ob-3 transition-colors"
                data-token={token}
                style={{ transitionDuration: `var(${token})` }}
              >
                <code className="font-mono text-(length:--type-data-sm)">
                  {token}
                </code>
              </div>
            ))}
          </div>
          <div className="relative mt-ob-3 flex flex-wrap gap-ob-2">
            {layerTokens.map(([label, token]) => (
              <div
                key={token}
                className="relative rounded-md border border-line bg-surface-raised px-ob-3 py-ob-2"
                data-token={token}
                style={{ zIndex: `var(${token})` }}
              >
                <span className="text-(length:--type-ui-sm)">{label}</span>
                <code className="ml-ob-2 font-mono text-(length:--type-data-xs) text-content-muted">
                  {token}
                </code>
              </div>
            ))}
          </div>
        </ReviewSection>
      </div>
    </section>
  )
}
