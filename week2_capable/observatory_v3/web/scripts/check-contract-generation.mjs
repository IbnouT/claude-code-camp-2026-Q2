import { execFileSync } from "node:child_process"
import { createHash } from "node:crypto"
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative } from "node:path"

const generatedRoot = "src/data/generated"

function files(root) {
  return readdirSync(root)
    .flatMap((entry) => {
      const path = join(root, entry)
      return statSync(path).isDirectory() ? files(path) : [path]
    })
    .sort()
}

function digest(root) {
  const hash = createHash("sha256")
  for (const path of files(root)) {
    hash.update(relative(root, path))
    hash.update("\0")
    hash.update(readFileSync(path))
    hash.update("\0")
  }
  return hash.digest("hex")
}

const before = digest(generatedRoot)
const orval = join("node_modules", ".bin", "orval")

execFileSync(orval, ["--config", "orval.config.ts"], { stdio: "inherit" })
const first = digest(generatedRoot)
execFileSync(orval, ["--config", "orval.config.ts"], { stdio: "inherit" })
const second = digest(generatedRoot)

if (first !== second) {
  throw new Error("Contract generation is not deterministic")
}
if (before !== first) {
  throw new Error(
    "Generated contracts were stale. Review and commit the regenerated output."
  )
}
