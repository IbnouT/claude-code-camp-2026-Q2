import { gzipSync } from "node:zlib";
import { readdir, readFile } from "node:fs/promises";

const budgets = {
  javascript: {
    entry: { raw: 300_000, gzip: 90_000 },
    lazy: { raw: 100_000, gzip: 25_000 },
  },
  css: {
    entry: { raw: 60_000, gzip: 12_000 },
    lazy: { raw: 30_000, gzip: 8_000 },
  },
};
const assets = await readdir(new URL("../dist/assets/", import.meta.url));
let failed = false;

for (const [kind, extension] of [["javascript", ".js"], ["css", ".css"]]) {
  const names = assets.filter((asset) => asset.endsWith(extension)).sort();
  if (names.length === 0) {
    throw new Error(`Missing ${kind} production asset`);
  }
  for (const name of names) {
    const bytes = await readFile(
      new URL(`../dist/assets/${name}`, import.meta.url),
    );
    const gzip = gzipSync(bytes).byteLength;
    const scope = name.startsWith("index-") ? "entry" : "lazy";
    const budget = budgets[kind][scope];
    const result = {
      kind,
      scope,
      asset: name,
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
}

if (failed) {
  process.exitCode = 1;
}
