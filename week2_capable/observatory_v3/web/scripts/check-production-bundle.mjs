import { readdir, readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const packageRoot = fileURLToPath(new URL("..", import.meta.url))
const outputRoot = path.join(packageRoot, "dist")
const developmentOnlyMarkers = [
  "V3_FOUNDATION_REVIEW_ONLY",
  "Foundation review",
  "HMR state probe",
  "observatory.backend-baseline.v1",
  "Backend contract baseline",
  "V3_DEVELOPMENT_ROUTER_REVIEW_ONLY",
  "V3_SERVER_STATE_REVIEW_ONLY",
]

async function collectFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const nestedFiles = await Promise.all(
    entries.map(async (entry) => {
      const absolutePath = path.join(directory, entry.name)
      if (entry.isDirectory()) {
        return collectFiles(absolutePath)
      }

      return [absolutePath]
    })
  )

  return nestedFiles.flat()
}

const outputFiles = await collectFiles(outputRoot)
const searchableFiles = outputFiles.filter((file) =>
  [".css", ".html", ".js", ".map"].includes(path.extname(file))
)
const searchableOutputs = await Promise.all(
  searchableFiles.map(async (file) => ({
    contents: await readFile(file, "utf8"),
    file,
  }))
)

for (const { contents, file } of searchableOutputs) {
  for (const marker of developmentOnlyMarkers) {
    if (contents.includes(marker)) {
      throw new Error(
        `Development-only marker "${marker}" leaked into ${path.relative(
          packageRoot,
          file
        )}`
      )
    }
  }
}

console.log(
  `Production bundle excludes the development review (${outputFiles.length} files checked).`
)
