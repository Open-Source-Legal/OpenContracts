/**
 * Reactive-var write-discipline regression test.
 *
 * Per docs/frontend/routing_system.md, the following Apollo reactive vars
 * may only be SET (called with arguments) by CentralRouteManager. All other
 * production code must read them via useReactiveVar() and update them
 * indirectly by changing the URL.
 *
 *   Entity vars      : openedCorpus, openedDocument, openedExtract,
 *                      openedThread, openedLabelset, openedUser
 *   URL-driven vars  : selectedAnnotationIds, selectedAnalysesIds,
 *                      selectedExtractIds, showStructuralAnnotations,
 *                      showSelectedAnnotationOnly,
 *                      showAnnotationBoundingBoxes, showAnnotationLabels
 *   Routing state    : routeLoading, routeError
 *
 * This test grep-walks frontend/src and fails if any setter call (a call
 * passing one or more arguments) appears outside the allowlisted files.
 *
 * Allowlist:
 *   - The manager itself (sets these as part of its job).
 *   - The cache definition file (initial values via makeVar).
 *   - The deprecated test-only setters in UISettingsAtom (guarded by
 *     console.warn and used only by component tests that mount without a
 *     CentralRouteManager).
 *   - Test files (*.test.*, *.spec.*, *.ct.*, anything under tests/ or
 *     __tests__/) which legitimately reset state in beforeEach blocks.
 *
 * If you are tempted to add a new allowlist entry: don't. Update the
 * URL via a navigation utility instead. See routing_system.md for the
 * unidirectional flow rule.
 */

import { describe, it, expect } from "vitest";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(__dirname, "../../..");
const SRC_DIR = path.join(REPO_ROOT, "src");
const MANAGER_PATH = path.join(SRC_DIR, "routing/CentralRouteManager.tsx");

const RESERVED_SETTERS = [
  "openedCorpus",
  "openedDocument",
  "openedExtract",
  "openedResearchReport",
  "openedThread",
  "openedLabelset",
  "openedUser",
  "selectedAnnotationIds",
  "selectedAnalysesIds",
  "selectedExtractIds",
  "showStructuralAnnotations",
  "showSelectedAnnotationOnly",
  "showAnnotationBoundingBoxes",
  "showAnnotationLabels",
  "routeLoading",
  "routeError",
];

const ALLOWLISTED_PATHS = [
  // The manager owns these writes.
  "src/routing/CentralRouteManager.tsx",
  // The definition file initialises the makeVar values.
  "src/graphql/cache.ts",
  // Test-only deprecated setters guarded by console.warn (see file header).
  "src/components/annotator/context/UISettingsAtom.tsx",
];

const TEST_FILE_PATTERN = /(\.test\.|\.spec\.|\.ct\.|\/__tests__\/|\/tests\/)/;

interface Violation {
  file: string;
  line: number;
  text: string;
  symbol: string;
}

/**
 * Returns true if `text` looks like a setter call:
 *   `symbol(<non-empty arg list>)`
 * but NOT:
 *   `useReactiveVar(symbol)`  — read
 *   `symbol()`                — read
 *   `symbol,` / `import { symbol }` — type/import
 *   `// symbol(...)` / `* symbol(...)` — comment
 */
function isSetterCall(symbol: string, text: string): boolean {
  const trimmed = text.trim();
  if (trimmed.startsWith("//") || trimmed.startsWith("*")) return false;
  if (trimmed.startsWith("import ") || trimmed.startsWith("export ")) {
    return false;
  }
  // useReactiveVar(symbol) and similar wrapping reads.
  if (new RegExp(`useReactiveVar\\s*\\(\\s*${symbol}\\b`).test(text)) {
    return false;
  }
  // Bare reads: symbol() with no arguments.
  if (new RegExp(`\\b${symbol}\\s*\\(\\s*\\)`).test(text)) {
    return false;
  }
  // Setter signature: symbol(<something>...
  return new RegExp(`\\b${symbol}\\s*\\([^)]`).test(text);
}

function findViolations(): Violation[] {
  const violations: Violation[] = [];
  for (const symbol of RESERVED_SETTERS) {
    let raw: string;
    try {
      raw = execSync(
        `grep -rn --include='*.ts' --include='*.tsx' "\\b${symbol}\\s*(" ${SRC_DIR}`,
        { encoding: "utf8" }
      );
    } catch (e: any) {
      // grep exits 1 when no matches — treat as empty.
      if (e.status === 1) continue;
      throw e;
    }

    for (const hit of raw.split("\n")) {
      if (!hit) continue;
      const match = hit.match(/^([^:]+):(\d+):(.*)$/);
      if (!match) continue;
      const [, absPath, lineStr, text] = match;
      const relPath = path.relative(REPO_ROOT, absPath).replace(/\\/g, "/");

      if (TEST_FILE_PATTERN.test(relPath)) continue;
      if (ALLOWLISTED_PATHS.includes(relPath)) continue;
      if (!isSetterCall(symbol, text)) continue;

      violations.push({
        file: relPath,
        line: Number(lineStr),
        text: text.trim(),
        symbol,
      });
    }
  }
  return violations;
}

describe("Central Routing write discipline", () => {
  it("no production code outside CentralRouteManager sets reserved reactive vars", () => {
    const violations = findViolations();
    if (violations.length > 0) {
      const grouped = violations
        .map((v) => `  ${v.file}:${v.line}  [${v.symbol}]  ${v.text}`)
        .join("\n");
      throw new Error(
        `Found ${violations.length} reactive-var write(s) outside CentralRouteManager.\n` +
          `These vars are owned by the manager — update the URL via navigationUtils\n` +
          `helpers instead. See docs/frontend/routing_system.md.\n\n${grouped}`
      );
    }
    expect(violations).toEqual([]);
  });
});

/**
 * Regression guard for the openedResearchReport state-hygiene gap.
 *
 * CentralRouteManager's Phase 1 corpus and document branches set only
 * openedCorpus / openedDocument; they intentionally do NOT clear sibling
 * entity vars. So a transition that changes neither corpusId nor documentId
 * in a way that re-clears it — e.g. /research/:slug → /c/:user/:corpus, a
 * top-level/landing route, or browser back/forward into a corpus/document
 * route — would leave openedResearchReport stale unless Phase 1 clears it up
 * front based on the route type. This asserts that single-source-of-truth
 * early clear exists and runs BEFORE the per-branch resolveEntity() logic
 * (so it covers the corpus/document branches that never clear it themselves).
 */
describe("openedResearchReport route-transition clearing", () => {
  const SOURCE = readFileSync(MANAGER_PATH, "utf8");

  it("clears openedResearchReport for any non-research route before resolution", () => {
    const earlyClear =
      'if (route.type !== "research" && openedResearchReport() !== null) {';
    const earlyClearIdx = SOURCE.indexOf(earlyClear);
    expect(
      earlyClearIdx,
      "Phase 1 must contain the route-type-driven openedResearchReport clear"
    ).toBeGreaterThan(-1);

    // The actual clearing call must live inside that guard block.
    const guardWindow = SOURCE.slice(earlyClearIdx, earlyClearIdx + 200);
    expect(
      guardWindow.includes("openedResearchReport(null)"),
      "the route-type guard must call openedResearchReport(null)"
    ).toBe(true);

    // It must run before the async resolveEntity definition, so it covers the
    // corpus/document branches (which do not clear openedResearchReport).
    const resolveEntityIdx = SOURCE.indexOf(
      "const resolveEntity = async () => {"
    );
    expect(resolveEntityIdx).toBeGreaterThan(-1);
    expect(
      earlyClearIdx,
      "early research-report clear must run before resolveEntity()"
    ).toBeLessThan(resolveEntityIdx);
  });
});
