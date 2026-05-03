#!/usr/bin/env node
/* eslint-disable */
/**
 * Counts explicit `any` usages across `frontend/src/**\/*.{ts,tsx}` and compares
 * the total against the committed baseline in `frontend/.any-baseline.json`.
 *
 * Behaviour:
 *  - Exits 1 if the current count is greater than the baseline (regression).
 *  - Exits 1 if `--check-strict` is passed and the count is below the baseline
 *    (used by CI to require the baseline file to stay in lockstep with reality).
 *  - With `--write` the baseline is rewritten to the current count and the
 *    per-area breakdown — used when intentionally lowering the gate.
 *
 * The matcher intentionally targets *type-position* uses of `any`:
 *   `: any`, `as any`, `<any>`, `any[]`, `Array<any>`, `Promise<any>`,
 *   `ReadonlyArray<any>`. Comment-only lines are skipped.
 *
 * See `docs/frontend/any-baseline.md` for rationale and workflow.
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "src");
const BASELINE_PATH = path.join(ROOT, ".any-baseline.json");

const ANY_PATTERN =
  /(:\s*any\b|\bas\s+any\b|<any>|\bany\[\]|Array<any>|Promise<any>|ReadonlyArray<any>)/;
const ANY_PATTERN_GLOBAL = new RegExp(ANY_PATTERN.source, "g");

// Areas tracked in the breakdown — keep aligned with the prioritisation list
// in issue #1448. A path matches the longest prefix that wins.
const AREAS = [
  ["components/knowledge_base", "knowledge_base"],
  ["components/annotator", "annotator"],
  ["components/widgets/chat", "widgets_chat"],
  ["components/widgets", "widgets_other"],
  ["components", "components_other"],
  ["graphql", "graphql"],
  ["hooks", "hooks"],
  ["atoms", "atoms"],
  ["routing", "routing"],
  ["utils", "utils"],
  ["types", "types"],
];

function classify(relPath) {
  const norm = relPath.split(path.sep).join("/");
  for (const [prefix, label] of AREAS) {
    if (norm.startsWith(prefix + "/") || norm === prefix) return label;
  }
  return "other";
}

function* walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(full);
    } else if (entry.isFile() && /\.(ts|tsx)$/.test(entry.name)) {
      yield full;
    }
  }
}

function isCommentLine(line) {
  const trimmed = line.trimStart();
  return (
    trimmed.startsWith("//") ||
    trimmed.startsWith("/*") ||
    trimmed.startsWith("*")
  );
}

function countFile(filePath) {
  const content = fs.readFileSync(filePath, "utf8");
  let total = 0;
  for (const line of content.split(/\r?\n/)) {
    if (isCommentLine(line)) continue;
    const matches = line.match(ANY_PATTERN_GLOBAL);
    if (matches) total += matches.length;
  }
  return total;
}

function collect() {
  const byArea = {};
  let total = 0;
  for (const file of walk(SRC)) {
    const n = countFile(file);
    if (n === 0) continue;
    total += n;
    const rel = path.relative(SRC, file);
    const area = classify(rel);
    byArea[area] = (byArea[area] || 0) + n;
  }
  // Stable ordering: descending count, then alphabetical.
  const sorted = Object.fromEntries(
    Object.entries(byArea).sort(
      ([a, av], [b, bv]) => bv - av || a.localeCompare(b)
    )
  );
  return { total, byArea: sorted };
}

function readBaseline() {
  if (!fs.existsSync(BASELINE_PATH)) return null;
  return JSON.parse(fs.readFileSync(BASELINE_PATH, "utf8"));
}

function writeBaseline(payload) {
  const json = JSON.stringify(payload, null, 2) + "\n";
  fs.writeFileSync(BASELINE_PATH, json);
}

function formatBreakdown(byArea) {
  return Object.entries(byArea)
    .map(([k, v]) => `    ${k}: ${v}`)
    .join("\n");
}

function main() {
  const args = new Set(process.argv.slice(2));
  const write = args.has("--write");
  const strict = args.has("--check-strict");

  const { total, byArea } = collect();
  const baseline = readBaseline();

  if (write) {
    writeBaseline({ total, byArea });
    console.log(
      `Updated ${path.relative(ROOT, BASELINE_PATH)} → total=${total}`
    );
    console.log(formatBreakdown(byArea));
    return;
  }

  if (!baseline) {
    console.error(
      `No baseline found at ${BASELINE_PATH}. Run \`yarn any:write\` to create one.`
    );
    process.exit(1);
  }

  console.log(`any usage: current=${total} baseline=${baseline.total}`);
  console.log("breakdown (current):");
  console.log(formatBreakdown(byArea));

  if (total > baseline.total) {
    console.error(
      `\n[FAIL] \`any\` count increased by ${total - baseline.total}. ` +
        `Replace explicit \`any\` with a real type, or — if unavoidable — ` +
        `lower another area in the same PR so the total does not grow.`
    );
    process.exit(1);
  }

  if (strict && total < baseline.total) {
    console.error(
      `\n[FAIL] \`any\` count dropped by ${baseline.total - total} but the ` +
        `baseline file was not updated. Run \`yarn any:write\` and commit the ` +
        `result so the gate ratchets down.`
    );
    process.exit(1);
  }

  if (total < baseline.total) {
    console.log(
      `\n[OK] Count is below baseline by ${baseline.total - total}. ` +
        `Run \`yarn any:write\` to ratchet the baseline down.`
    );
  } else {
    console.log("\n[OK] No regression vs. baseline.");
  }
}

main();
