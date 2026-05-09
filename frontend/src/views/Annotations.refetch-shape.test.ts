/**
 * Source-level regression for the Annotations view refetch shape.
 *
 * The pre-fix Annotations view had two redundant ``useEffect`` blocks that
 * called ``refetch_annotations()``:
 *
 *   - one watching the same six reactive vars (filters, search term, auth
 *     token) that already drove ``annotation_variables``, doubling every
 *     filter-change refetch with a second round-trip;
 *   - one watching ``opened_corpus`` despite ``opened_corpus`` not being
 *     part of the query variables — every corpus-open fired a no-op
 *     refetch of the same data.
 *
 * On top of that, ``annotation_variables`` was a fresh ``let``-bound
 * object literal each render, forcing Apollo to deep-compare the
 * variables on every parent re-render before it could decide *not* to
 * refetch. Memoising on the underlying primitives kills the deep-compare
 * cost on the hot path.
 *
 * As with the Documents/Extracts regressions, MockedProvider's request
 * deduplication hides the storm in CT tests, so we pin the fix at the
 * source level here.
 */
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const ANNOTATIONS_TSX = readFileSync(join(HERE, "Annotations.tsx"), "utf8");

describe("Annotations view refetch shape (regression)", () => {
  it("does not call refetch_annotations() from any useEffect block", () => {
    const USE_EFFECT_REFETCH_RE =
      /useEffect\s*\(\s*\(\s*\)\s*=>\s*\{[^}]*\brefetch_annotations\s*\(/s;
    expect(
      USE_EFFECT_REFETCH_RE.test(ANNOTATIONS_TSX),
      "Annotations.tsx must not call refetch_annotations() from a " +
        "useEffect — Apollo's useQuery already refetches when its " +
        "variables change. AuthGate clears the cache on login/logout. " +
        "If you need a refetch trigger, add the value to " +
        "annotation_variables instead."
    ).toBe(false);
  });

  it("does not call refetch_corpus() from any useEffect block", () => {
    // The previous opened_corpus effect also called refetch_corpus(); the
    // GET_CORPUS_LABELSET_AND_LABELS query already refetches on
    // ``corpus_scope_id`` change because corpus_scope_id is a query
    // variable. The explicit refetch_corpus() call doubled the request.
    const USE_EFFECT_REFETCH_CORPUS_RE =
      /useEffect\s*\(\s*\(\s*\)\s*=>\s*\{[^}]*\brefetch_corpus\s*\(/s;
    expect(
      USE_EFFECT_REFETCH_CORPUS_RE.test(ANNOTATIONS_TSX),
      "Annotations.tsx must not call refetch_corpus() from a useEffect."
    ).toBe(false);
  });

  it("memoises annotation_variables on its filter dependencies", () => {
    // The legacy code built ``annotation_variables`` with ``let`` at the
    // top of the component, producing a fresh reference every render.
    // ``useMemo`` ensures Apollo only sees a new variables identity when
    // a real input changes.
    expect(ANNOTATIONS_TSX).toMatch(/const annotation_variables = useMemo</);
  });
});
