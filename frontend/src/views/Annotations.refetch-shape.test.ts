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
  // Legitimate exemptions: refetches inside useMutation onCompleted, modal
  // onClose handlers, or imperative event callbacks. If a future useEffect
  // refetch is genuinely required, route it through a helper variable so
  // ``findUseEffectCalls`` no longer matches — and add a comment explaining
  // why useQuery variable-change refetches don't already cover the case.
  //
  // The detector walks the source with a balanced-brace scanner instead of
  // a regex with ``[^}]*``: a regex stops at the first inner ``}``, so a
  // call nested inside an ``if`` block (or any brace pair) within the
  // effect body would slip past undetected.
  it("does not call refetch_annotations() from any useEffect block", () => {
    expect(
      findUseEffectCalls(ANNOTATIONS_TSX, "refetch_annotations"),
      "Annotations.tsx must not call refetch_annotations() from a " +
        "useEffect — Apollo's useQuery already refetches when its " +
        "variables change. AuthGate clears the cache on login/logout. " +
        "If you need a refetch trigger, add the value to " +
        "annotation_variables instead."
    ).toEqual([]);
  });

  it("does not call refetch_corpus() from any useEffect block", () => {
    // The previous opened_corpus effect also called refetch_corpus(); the
    // GET_CORPUS_LABELSET_AND_LABELS query already refetches on
    // ``corpus_scope_id`` change because corpus_scope_id is a query
    // variable. The explicit refetch_corpus() call doubled the request.
    expect(
      findUseEffectCalls(ANNOTATIONS_TSX, "refetch_corpus"),
      "Annotations.tsx must not call refetch_corpus() from a useEffect."
    ).toEqual([]);
  });

  it("memoises annotation_variables on its filter dependencies", () => {
    // The legacy code built ``annotation_variables`` with ``let`` at the
    // top of the component, producing a fresh reference every render.
    // ``useMemo`` ensures Apollo only sees a new variables identity when
    // a real input changes.
    expect(ANNOTATIONS_TSX).toMatch(/const annotation_variables = useMemo</);
  });
});

/**
 * Return the 1-based line numbers of any ``${callName}(`` site whose
 * enclosing function body is the body of a ``useEffect(() => { ... })``
 * callback. Empty array means clean.
 */
function findUseEffectCalls(source: string, callName: string): number[] {
  const offenders: number[] = [];
  // The optional ``async`` keyword catches the
  // ``useEffect(async () => {...})`` form so a future
  // ``useEffect(async () => { refetch_annotations(); })`` doesn't slip past
  // this scan.
  const ENTRY_RE = /useEffect\s*\(\s*(?:async\s*)?\(\s*\)\s*=>\s*\{/g;
  const callRe = new RegExp(`\\b${callName}\\s*\\(`);
  let match: RegExpExecArray | null;
  while ((match = ENTRY_RE.exec(source)) !== null) {
    const bodyStart = match.index + match[0].length;
    let depth = 1;
    let cursor = bodyStart;
    while (cursor < source.length && depth > 0) {
      const ch = source[cursor];
      if (ch === "{") depth++;
      else if (ch === "}") depth--;
      cursor++;
    }
    const body = source.slice(bodyStart, Math.max(bodyStart, cursor - 1));
    const hit = callRe.exec(body);
    if (hit) {
      const linesBefore = source.slice(0, bodyStart + hit.index);
      offenders.push((linesBefore.match(/\n/g)?.length ?? 0) + 1);
    }
  }
  return offenders;
}
