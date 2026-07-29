import { gzipSync } from "node:zlib";
import { readdir, readFile } from "node:fs/promises";

const budgets = {
  javascript: { raw: 300_000, gzip: 90_000 },
  css: { raw: 60_000, gzip: 12_000 },
};
const assets = await readdir(new URL("../dist/assets/", import.meta.url));
let failed = false;

for (const [kind, extension] of [["javascript", ".js"], ["css", ".css"]]) {
  const name = assets.find((asset) => asset.endsWith(extension));
  if (name === undefined) {
    throw new Error(`Missing ${kind} production asset`);
  }
  const bytes = await readFile(
    new URL(`../dist/assets/${name}`, import.meta.url),
  );
  const gzip = gzipSync(bytes).byteLength;
  const budget = budgets[kind];
  const result = {
    kind,
    raw: bytes.byteLength,
    rawBudget: budget.raw,
    gzip,
    gzipBudget: budget.gzip,
  };
  console.log(JSON.stringify(result));
  if (bytes.byteLength > budget.raw || gzip > budget.gzip) {
    failed = true;
  }
}

if (failed) {
  process.exitCode = 1;
}
