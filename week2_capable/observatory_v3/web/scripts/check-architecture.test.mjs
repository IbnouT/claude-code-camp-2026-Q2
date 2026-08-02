import { execFileSync } from "node:child_process"
import { mkdtemp, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import assert from "node:assert/strict"
import { fileURLToPath } from "node:url"

const check = fileURLToPath(
  new URL("./check-architecture.mjs", import.meta.url)
)

test("backend legacy imports fail the architecture boundary", async () => {
  const backend = await mkdtemp(
    path.join(os.tmpdir(), "observatory-v3-backend-boundary-")
  )

  try {
    await writeFile(
      path.join(backend, "legacy_dependency.py"),
      "from observatory_api import app\n",
      "utf8"
    )

    assert.throws(
      () =>
        execFileSync(process.execPath, [check], {
          encoding: "utf8",
          env: {
            ...process.env,
            OBSERVATORY_V3_BACKEND_ROOT: backend,
          },
          stdio: "pipe",
        }),
      /legacy Python import/u
    )

    await writeFile(
      path.join(backend, "legacy_dependency.py"),
      "from pathlib import Path\n",
      "utf8"
    )

    const output = execFileSync(process.execPath, [check], {
      encoding: "utf8",
      env: {
        ...process.env,
        OBSERVATORY_V3_BACKEND_ROOT: backend,
      },
    })
    assert.match(output, /Architecture boundary passed/u)
  } finally {
    await rm(backend, { force: true, recursive: true })
  }
})
