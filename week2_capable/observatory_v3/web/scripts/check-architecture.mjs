import { readdir, readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const packageRoot = fileURLToPath(new URL("..", import.meta.url))
const v3Root = path.resolve(packageRoot, "..")
const sourceRoot = path.join(packageRoot, "src")
const canonicalBackendRoot = path.join(v3Root, "backend")
const backendRoot =
  process.env.OBSERVATORY_V3_BACKEND_ROOT ?? canonicalBackendRoot
const backendFixtureRoot = path.join(
  canonicalBackendRoot,
  "openapi",
  "fixtures"
)
const architectureCheck = fileURLToPath(import.meta.url)
const sourceExtensions = new Set([".js", ".jsx", ".mjs", ".ts", ".tsx"])
const backendExtensions = new Set([".py"])
const generatedDirectories = new Set([
  ".venv",
  "dist",
  "node_modules",
  "playwright-report",
  "test-results",
])
const importPattern =
  /\b(?:from\s+|import\s*(?:\(\s*)?)["'](?<specifier>[^"']+)["']/gu

const prohibitedRuntimeFragments = [
  ["raw document navigation", /\bwindow\.location\b|\bdocument\.location\b/u],
  ["raw history navigation", /\bwindow\.history\b/u],
  ["independent polling loop", /\bsetInterval\s*\(/u],
]
const prohibitedLegacyReferences = [
  "observatory_v2",
  "week2_capable/observatory/",
  "week2_capable/observatory\\",
]
const allowedPresentationDataImports = new Set([
  "@/data/capabilities",
  "@/data/session-catalog",
  "@/data/server-state-provider",
])

async function collectSourceFiles(directory, extensions = sourceExtensions) {
  let entries
  try {
    entries = await readdir(directory, { withFileTypes: true })
  } catch (error) {
    if (error?.code === "ENOENT") {
      return []
    }
    throw error
  }
  const nestedFiles = await Promise.all(
    entries.map(async (entry) => {
      const absolutePath = path.join(directory, entry.name)
      if (entry.isDirectory()) {
        if (generatedDirectories.has(entry.name)) {
          return []
        }
        return collectSourceFiles(absolutePath, extensions)
      }

      if (extensions.has(path.extname(entry.name))) {
        return [absolutePath]
      }

      return []
    })
  )

  return nestedFiles.flat()
}

function isInsidePackage(file) {
  const relativePath = path.relative(packageRoot, file)
  return relativePath !== ".." && !relativePath.startsWith(`..${path.sep}`)
}

function isApprovedContractFixtureImport(file, specifier) {
  if (!file.endsWith(".test.ts") && !file.endsWith(".test.tsx")) {
    return false
  }
  const [sourcePath, query = ""] = specifier.split("?")
  if (sourcePath === undefined || query !== "raw") {
    return false
  }
  const resolved = path.resolve(path.dirname(file), sourcePath)
  const relative = path.relative(backendFixtureRoot, resolved)
  return (
    relative !== ".." &&
    !relative.startsWith(`..${path.sep}`) &&
    path.extname(resolved) === ".json"
  )
}

const scannedDirectories = ["scripts", "src", "tests"].map((directory) =>
  path.join(packageRoot, directory)
)
const topLevelFiles = [
  "playwright.config.ts",
  "vite.config.ts",
  "vitest.config.ts",
].map((file) => path.join(packageRoot, file))
const sourceFiles = [
  ...(
    await Promise.all(
      scannedDirectories.map((directory) => collectSourceFiles(directory))
    )
  ).flat(),
  ...topLevelFiles,
].filter((file) => file !== architectureCheck)
const sourceContents = await Promise.all(
  sourceFiles.map(async (file) => ({
    contents: await readFile(file, "utf8"),
    file,
  }))
)
const backendFiles = await collectSourceFiles(backendRoot, backendExtensions)
const backendContents = await Promise.all(
  backendFiles.map(async (file) => ({
    contents: await readFile(file, "utf8"),
    file,
  }))
)
const failures = []

for (const { contents, file } of sourceContents) {
  const relativeFile = path.relative(packageRoot, file)
  const isRuntimeSource =
    file === sourceRoot || file.startsWith(`${sourceRoot}${path.sep}`)

  if (isRuntimeSource) {
    for (const match of contents.matchAll(
      /\brefetchInterval\s*:\s*(?<value>[^,\n}]+)/gu
    )) {
      if (match.groups?.value.trim() !== "false") {
        failures.push(`${relativeFile}: recurring query polling enabled`)
      }
    }

    for (const legacyReference of prohibitedLegacyReferences) {
      if (contents.includes(legacyReference)) {
        failures.push(
          `${relativeFile}: legacy production reference ${legacyReference}`
        )
      }
    }

    for (const [label, pattern] of prohibitedRuntimeFragments) {
      if (pattern.test(contents)) {
        failures.push(`${relativeFile}: ${label}`)
      }
    }

    if (!relativeFile.startsWith(`src${path.sep}data${path.sep}`)) {
      if (/\b(?:fetch|EventSource|WebSocket)\b/u.test(contents)) {
        failures.push(`${relativeFile}: network transport outside src/data`)
      }
      if (/["'`]\/api\/v\d/u.test(contents)) {
        failures.push(`${relativeFile}: API route literal outside src/data`)
      }
      if (
        /\b(?:interface|type)\s+\w+(?:Request|Response|Dto|DTO|Payload)\b/u.test(
          contents
        )
      ) {
        failures.push(
          `${relativeFile}: independently authored transport type outside src/data`
        )
      }
      if (contents.includes("@tanstack/react-query")) {
        failures.push(
          `${relativeFile}: direct TanStack Query use outside src/data`
        )
      }
      if (contents.includes("refetchInterval")) {
        failures.push(`${relativeFile}: polling configuration outside src/data`)
      }
    }
  }

  for (const match of contents.matchAll(importPattern)) {
    const specifier = match.groups?.specifier
    if (specifier === undefined) {
      continue
    }

    if (
      isRuntimeSource &&
      !relativeFile.startsWith(`src${path.sep}data${path.sep}`) &&
      specifier.startsWith("@/data/") &&
      !allowedPresentationDataImports.has(specifier)
    ) {
      failures.push(
        `${relativeFile}: direct data implementation import ${specifier}`
      )
    }

    if (
      prohibitedLegacyReferences.some((fragment) =>
        specifier.includes(fragment)
      )
    ) {
      failures.push(`${relativeFile}: legacy runtime import ${specifier}`)
    }

    if (specifier.includes("radix")) {
      failures.push(
        `${relativeFile}: unapproved behavior provider ${specifier}`
      )
    }

    if (
      specifier.includes("base-ui") &&
      !relativeFile.startsWith(
        `${path.join("src", "components", "ui")}${path.sep}`
      )
    ) {
      failures.push(
        `${relativeFile}: Base UI import outside canonical components ${specifier}`
      )
    }

    if (specifier.endsWith(".module.css")) {
      failures.push(`${relativeFile}: CSS Module import ${specifier}`)
    }

    if (specifier.endsWith(".css")) {
      const isApprovedRootStyle =
        relativeFile === path.join("src", "main.tsx") &&
        specifier === "./index.css"
      if (!isApprovedRootStyle) {
        failures.push(`${relativeFile}: stylesheet import ${specifier}`)
      }
    }

    if (specifier.startsWith(".")) {
      const [sourcePath] = specifier.split("?")
      const resolvedImport = path.resolve(
        path.dirname(file),
        sourcePath ?? specifier
      )
      if (
        !isInsidePackage(resolvedImport) &&
        !isApprovedContractFixtureImport(file, specifier)
      ) {
        failures.push(`${relativeFile}: import escapes package ${specifier}`)
      }
    }
  }
}

const backendLegacyPatterns = [
  [
    "legacy Python import",
    /(?:^|\n)\s*(?:from|import)\s+(?:observatory_api|observatory_v2)(?:\b|\.)/u,
  ],
  ["legacy repository path", /week2_capable[\\/]observatory(?:_v2)?[\\/]/u],
  ["legacy relative path", /(?:\.\.[\\/])+observatory(?:_v2)?(?:[\\/]|$)/u],
]

for (const { contents, file } of backendContents) {
  const relativeFile = path.relative(v3Root, file)
  for (const [label, pattern] of backendLegacyPatterns) {
    if (pattern.test(contents)) {
      failures.push(`${relativeFile}: ${label}`)
    }
  }
}

if (failures.length > 0) {
  throw new Error(`Architecture boundary failed:\n${failures.join("\n")}`)
}

console.log(
  `Architecture boundary passed (${sourceFiles.length} web files and ${backendFiles.length} backend files checked).`
)
