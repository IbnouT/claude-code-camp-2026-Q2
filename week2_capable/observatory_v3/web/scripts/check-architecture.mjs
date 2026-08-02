import { readdir, readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const packageRoot = fileURLToPath(new URL("..", import.meta.url))
const v3Root = path.resolve(packageRoot, "..")
const sourceRoot = path.join(packageRoot, "src")
const backendRoot =
  process.env.OBSERVATORY_V3_BACKEND_ROOT ?? path.join(v3Root, "backend")
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
      if (/\bfetch\s*\(/u.test(contents)) {
        failures.push(`${relativeFile}: fetch outside src/data`)
      }
    }
  }

  for (const match of contents.matchAll(importPattern)) {
    const specifier = match.groups?.specifier
    if (specifier === undefined) {
      continue
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
      const resolvedImport = path.resolve(path.dirname(file), specifier)
      if (!isInsidePackage(resolvedImport)) {
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
