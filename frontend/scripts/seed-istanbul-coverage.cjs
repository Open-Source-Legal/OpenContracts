#!/usr/bin/env node
/* eslint-disable */
/**
 * Seed the nyc temp-dir with empty Istanbul coverage entries for every
 * source file matched by the package.json `nyc` config so `nyc report`
 * reports the full source-file denominator.
 *
 * Why this is needed: nyc's `--all` flag (which would otherwise do this)
 * only runs when nyc is invoked as a *test wrapper* (`nyc <test-cmd>`),
 * not when invoked as `nyc report` — `nyc report --all` silently ignores
 * the flag. Even when nyc IS invoked as a wrapper, its `addAllFiles()`
 * uses `Module._extensions[".ts" / ".tsx"]` to read source, which is
 * unregistered without ts-node, so .ts/.tsx files are skipped and the
 * coverage data file ends up an empty `{}`. (Verified locally: with our
 * nyc 18 + vite-plugin-istanbul setup, both `nyc report --all` and
 * `nyc --all <noop>` produce 0 SF entries against 483 source files.)
 *
 * This script bypasses both limitations by parsing each source file with
 * istanbul-lib-instrument's TypeScript-aware parser, then writing the
 * resulting empty file-coverage maps to a single JSON file in the temp
 * dir. `nyc report` merges that file with the per-test JSON files written
 * by `tests/utils/coverage.ts` and produces a full-denominator lcov.
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { createInstrumenter } = require("istanbul-lib-instrument");
const { globSync } = require("glob");

const cwd = process.cwd();
const tempDir = path.resolve(cwd, process.argv[2] || "coverage/ct/.nyc_output");

// Mirror the package.json `nyc` config. Keep these in sync.
const include = ["src/**/*.{ts,tsx}"];
const exclude = [
  "src/**/*.test.{ts,tsx}",
  "src/setupTests.ts",
  "src/main.tsx",
  "**/*.d.ts",
];

const files = globSync(include, { cwd, ignore: exclude, absolute: true });

const instrumenter = createInstrumenter({
  esModules: true,
  produceSourceMap: false,
  parserPlugins: [
    "asyncGenerators",
    "bigInt",
    "classProperties",
    "classPrivateProperties",
    "classPrivateMethods",
    ["decorators", { decoratorsBeforeExport: false }],
    "dynamicImport",
    "importMeta",
    "jsx",
    "numericSeparator",
    "objectRestSpread",
    "optionalCatchBinding",
    "optionalChaining",
    "topLevelAwait",
    "typescript",
  ],
});

const allCoverage = {};
let succeeded = 0;
const failures = [];
for (const filename of files) {
  const source = fs.readFileSync(filename, "utf8");
  try {
    instrumenter.instrumentSync(source, filename);
    const fileCoverage = instrumenter.lastFileCoverage();
    if (fileCoverage) {
      allCoverage[fileCoverage.path] = { ...fileCoverage, all: true };
      succeeded += 1;
    }
  } catch (err) {
    failures.push({ file: path.relative(cwd, filename), message: err.message });
  }
}

fs.mkdirSync(tempDir, { recursive: true });
const outFile = path.join(tempDir, `seed-all-${crypto.randomUUID()}.json`);
fs.writeFileSync(outFile, JSON.stringify(allCoverage));

console.log(
  `[seed-istanbul-coverage] seeded ${succeeded} file(s) into ${path.relative(
    cwd,
    outFile
  )}`
);
if (failures.length > 0) {
  console.warn(
    `[seed-istanbul-coverage] ${failures.length} file(s) could not be parsed and will be missing from the denominator:`
  );
  for (const { file, message } of failures) {
    console.warn(`  - ${file}: ${message}`);
  }
}
