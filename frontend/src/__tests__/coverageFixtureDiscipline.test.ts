/**
 * Coverage-fixture import-discipline regression test.
 *
 * Istanbul browser coverage for Playwright tests is collected ONLY by the
 * extended `page` fixture inside two wrapper modules. A test that imports
 * `test`/`expect` straight from the raw Playwright package gets the
 * un-wrapped runner: it compiles, runs, and passes — but `window.__coverage__`
 * is never read, so the file's coverage is silently discarded.
 *
 *   | Test type | Glob                       | Must import test/expect from |
 *   |-----------|----------------------------|------------------------------|
 *   | Component | tests/**\/*.ct.tsx         | tests/utils/coverage.ts      |
 *   | E2E       | tests/e2e/**\/*.spec.ts    | tests/e2e/fixtures.ts        |
 *
 * The failure mode is invisible: nothing fails, CI stays green, but
 * `codecov/patch` drops because a whole test file vanished from the report.
 * PR #1744 hit exactly this — 7 mobile component tests imported from
 * `@playwright/experimental-ct-react` and reported ~30% coverage despite
 * fully passing suites.
 *
 * This test walks frontend/tests and fails if any component or e2e test
 * sources the `test`/`expect` runtime from a raw Playwright package instead
 * of its coverage fixture. It mirrors `centralRouteDiscipline.test.ts`.
 *
 * Importing a *type* is fine — `import type { Page } from "@playwright/test"`
 * has no runtime and cannot bypass coverage; only the `test`/`expect` value
 * imports are forbidden.
 *
 * See issue #1746 (follow-up to PR #1744).
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const TESTS_DIR = path.join(FRONTEND_ROOT, "tests");
const E2E_DIR = path.join(TESTS_DIR, "e2e");

/**
 * Raw Playwright packages. Importing the `test`/`expect` *runtime* from
 * either of these skips the coverage-collecting fixture wrapper.
 */
const RAW_PLAYWRIGHT_PACKAGES = new Set([
  "@playwright/test",
  "@playwright/experimental-ct-react",
]);

/** Symbols whose import source decides whether coverage is collected. */
const RUNTIME_SYMBOLS = new Set(["test", "expect"]);

type Category = "component" | "e2e";

interface FixtureSpec {
  /** Human-readable required module, used in error messages. */
  label: string;
  /** True when an import specifier resolves to this category's fixture. */
  matches: (specifier: string) => boolean;
}

const FIXTURES: Record<Category, FixtureSpec> = {
  component: {
    label: "tests/utils/coverage",
    // ./utils/coverage, ../utils/coverage, ../../utils/coverage, ...
    matches: (s) => /(^|\/)utils\/coverage(\.[tj]sx?)?$/.test(s),
  },
  e2e: {
    label: "tests/e2e/fixtures",
    // ./fixtures (every e2e spec lives directly in tests/e2e/)
    matches: (s) => /(^|\/)fixtures(\.[tj]s)?$/.test(s),
  },
};

interface NamedImport {
  /** The imported name (the symbol before any `as` alias). */
  name: string;
  /** True for a per-specifier `type X` import. */
  typeOnly: boolean;
}

interface ParsedImport {
  /** True for a whole-statement `import type { ... }`. */
  typeOnly: boolean;
  named: NamedImport[];
  module: string;
}

interface Violation {
  file: string;
  message: string;
}

/**
 * Extract every named-import statement from `source`, multi-line aware.
 * Default-only / namespace imports are irrelevant here (Playwright's
 * `test`/`expect` are named exports) and are skipped.
 */
function parseNamedImports(source: string): ParsedImport[] {
  const imports: ParsedImport[] = [];
  // `import [type] [Default,] { ... } from "..."` — the non-greedy [\s\S]*?
  // makes the brace body span newlines without swallowing later statements.
  const re =
    /import\s+(type\s+)?(?:[A-Za-z_$][\w$]*\s*,\s*)?\{([\s\S]*?)\}\s*from\s*['"]([^'"]+)['"]/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(source)) !== null) {
    const [, typeKeyword, body, module] = match;
    const named = body
      .split(",")
      .map((piece) => piece.trim())
      .filter(Boolean)
      .map<NamedImport>((spec) => {
        let typeOnly = false;
        let rest = spec;
        if (rest.startsWith("type ")) {
          typeOnly = true;
          rest = rest.slice("type ".length).trim();
        }
        const name = rest.split(/\s+as\s+/)[0].trim();
        return { name, typeOnly };
      });
    imports.push({ typeOnly: Boolean(typeKeyword), named, module });
  }
  return imports;
}

/**
 * Check a single test file. Returns a violation when it imports the
 * `test`/`expect` runtime from a raw Playwright package, or when it never
 * sources `test` from its category's coverage fixture.
 */
function checkFile(absPath: string, category: Category): Violation[] {
  const relPath = path.relative(FRONTEND_ROOT, absPath).replace(/\\/g, "/");
  const fixture = FIXTURES[category];
  const imports = parseNamedImports(fs.readFileSync(absPath, "utf8"));
  const violations: Violation[] = [];
  let importsTestFromFixture = false;

  for (const imp of imports) {
    // A whole-statement `import type { ... }` has no runtime effect.
    if (imp.typeOnly) continue;

    for (const { name, typeOnly } of imp.named) {
      if (typeOnly) continue; // per-specifier `type X` — type-only
      if (!RUNTIME_SYMBOLS.has(name)) continue; // ignore Page, Route, Locator...

      if (RAW_PLAYWRIGHT_PACKAGES.has(imp.module)) {
        violations.push({
          file: relPath,
          message:
            `imports \`${name}\` from "${imp.module}" — Istanbul coverage ` +
            `from this file is silently discarded. Import it from ` +
            `"${fixture.label}" instead.`,
        });
      }

      if (name === "test" && fixture.matches(imp.module)) {
        importsTestFromFixture = true;
      }
    }
  }

  if (!importsTestFromFixture) {
    violations.push({
      file: relPath,
      message:
        `does not import \`test\` from the coverage fixture ` +
        `"${fixture.label}" — its coverage will not be collected.`,
    });
  }

  return violations;
}

/** Recursively collect every file path under `dir`. */
function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walk(full));
    } else if (entry.isFile()) {
      out.push(full);
    }
  }
  return out;
}

function assertClean(violations: Violation[], header: string): void {
  if (violations.length === 0) return;
  const detail = violations
    .map((v) => `  ${v.file}\n    ${v.message}`)
    .join("\n");
  throw new Error(
    `${header}\n\n${detail}\n\n` +
      `Only the extended fixtures (tests/utils/coverage.ts, ` +
      `tests/e2e/fixtures.ts) read window.__coverage__. See issue #1746.`
  );
}

const allTestFiles = walk(TESTS_DIR);
const componentTests = allTestFiles.filter((f) => f.endsWith(".ct.tsx"));
const e2eTests = allTestFiles.filter(
  (f) => f.endsWith(".spec.ts") && f.startsWith(E2E_DIR + path.sep)
);

describe("Coverage-fixture import discipline", () => {
  it("every component test imports test/expect from tests/utils/coverage", () => {
    // Guard against the walk silently finding nothing (dir moved/renamed).
    expect(componentTests.length).toBeGreaterThan(0);

    const violations = componentTests.flatMap((f) => checkFile(f, "component"));
    assertClean(
      violations,
      `Found ${violations.length} component test(s) bypassing the Istanbul ` +
        `coverage fixture (tests/utils/coverage.ts).`
    );
    expect(violations).toEqual([]);
  });

  it("every e2e spec imports test/expect from tests/e2e/fixtures", () => {
    expect(e2eTests.length).toBeGreaterThan(0);

    const violations = e2eTests.flatMap((f) => checkFile(f, "e2e"));
    assertClean(
      violations,
      `Found ${violations.length} e2e spec(s) bypassing the Istanbul ` +
        `coverage fixture (tests/e2e/fixtures.ts).`
    );
    expect(violations).toEqual([]);
  });
});
