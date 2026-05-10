/**
 * Source-level regression for the Extracts view refetch shape.
 *
 * The pre-fix Extracts view shared the same shape problems Documents.tsx
 * had (PR #1517 / #1553):
 *
 *   - ``useEffect(() => { if (currentUser) refetch(); })`` fired every time
 *     the ``userObj`` reactive var settled, on top of the implicit
 *     ``useQuery`` refetch already triggered by the search-term variable.
 *   - The query asked for ``fullDocumentList { id }`` and
 *     ``fieldset.fullColumnList { id }`` purely to read ``.length`` on the
 *     frontend, paying for an N+1 per-document permission filter and a
 *     full Column-row payload per row.
 *   - The query did not pass ``first`` or ``after`` to the connection at
 *     all, so the server quietly clamped every request to ``max_limit=15``
 *     and the cursor sent by ``fetchMore`` was silently ignored — broken
 *     pagination.
 *
 * The bug is invisible to MockedProvider because Apollo deduplicates
 * concurrent identical queries before they reach MockLink. We pin the
 * structural fix at the source level so a regression fails loudly here.
 */
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXTRACTS_TSX = readFileSync(join(HERE, "Extracts.tsx"), "utf8");

describe("Extracts view refetch shape (regression)", () => {
  it("does not call refetch() from any useEffect block", () => {
    // The original bug had ``useEffect(() => { if (currentUser) refetch(); }, [currentUser, refetch])``
    // firing on every userObj reactive-var settle. Apollo's useQuery already
    // refetches when its variables change, and AuthGate clears the cache on
    // login/logout — the explicit refetch is double work. The mutation
    // ``onCompleted: () => refetch()`` and the modal's onClose refetch are
    // legitimate refetch sites and not matched by this scan (neither is
    // inside a useEffect).
    //
    // Legitimate exemptions: refetches inside ``useMutation`` ``onCompleted``,
    // ``onClose`` modal callbacks, or imperative event handlers. If a future
    // useEffect refetch is genuinely needed (rare), bind the refetch through
    // a helper variable so this scan no longer matches — and add a comment
    // explaining why ``useQuery`` variables don't already cover the case.
    //
    // The scan is implemented as a balanced-brace walk rather than a regex
    // because a regex with ``[^}]*`` between ``useEffect(... => {`` and
    // ``refetch(`` stops at the first inner ``}``, so a ``refetch()`` nested
    // inside an ``if`` block (or any other brace pair) inside the effect
    // body would slip past undetected.
    const offenders = findUseEffectRefetches(EXTRACTS_TSX);
    expect(
      offenders,
      "Extracts.tsx must not call refetch() from a useEffect — " +
        "Apollo's useQuery already refetches when its variables change. " +
        "AuthGate already clears the cache on login/logout. See the " +
        "comment block where the auth-change effect was removed."
    ).toEqual([]);
  });

  it("imports the slim GET_EXTRACTS_FOR_LIST query, not the heavy GET_EXTRACTS", () => {
    // The list view should use the focused query that omits per-row N+1
    // shapes: ``fullDocumentList { id }`` triggers a per-doc permission
    // filter on the backend, ``fullColumnList { id }`` ships full Column
    // rows when only a count is needed, and several creator/fieldset fields
    // are unused by the card. The shared GET_EXTRACTS is fine for callers
    // that legitimately walk those lists (ExtractItem, CorpusExtractCards,
    // CamlArticleEditor, CreateExtractModal).
    expect(EXTRACTS_TSX).toMatch(/\bGET_EXTRACTS_FOR_LIST\b/);
    // The ``/s`` (dotAll) flag is required: import specifiers can span
    // multiple lines, and ``[^}]*`` would otherwise not cross a newline.
    // Stripping the flag during a future edit would silently make the
    // negative-match test miss multi-line imports.
    const HEAVY_IMPORT_RE =
      /\bimport\s*\{[^}]*\bGET_EXTRACTS\b(?!_FOR_LIST)[^}]*\}\s*from\s*["']\.\.\/graphql\/queries["']/s;
    expect(
      HEAVY_IMPORT_RE.test(EXTRACTS_TSX),
      "Extracts.tsx must not import the heavy GET_EXTRACTS query — " +
        "use GET_EXTRACTS_FOR_LIST for the list view."
    ).toBe(false);
  });

  it("passes explicit page-size and cursor variables to fetchMore", () => {
    // The legacy fetchMore call passed only ``cursor`` as a variable, but
    // the original GET_EXTRACTS query did not include ``$cursor`` / ``$limit``
    // among its operation parameters at all — pagination silently broke.
    // The slim query wires both, and the view passes them through. The page
    // size is sourced from the shared ``EXTRACT_PAGINATION.PAGE_SIZE``
    // constant so the Annotations / Documents / Extracts views stay in sync
    // (Claude review on PR #1602: per-view magic numbers drift over time).
    expect(EXTRACTS_TSX).toMatch(/\bEXTRACT_PAGINATION\.PAGE_SIZE\b/);
    expect(EXTRACTS_TSX).toMatch(/limit\s*:\s*EXTRACT_PAGINATION\.PAGE_SIZE/);
    expect(EXTRACTS_TSX).toMatch(
      /cursor\s*:\s*data\.extracts\.pageInfo\.endCursor/
    );
  });
});

/**
 * Walk ``source`` and return any ``refetch(`` call sites whose enclosing
 * function body is the body of a ``useEffect(() => { ... })`` callback.
 * Implemented as a balanced-brace scanner so calls nested inside ``if``
 * blocks, ternaries, or other inner braces are still detected.
 *
 * Returns the 1-based line numbers of each match — empty array means clean.
 */
function findUseEffectRefetches(source: string): number[] {
  const offenders: number[] = [];
  // Cheap entry-point match: ``useEffect`` followed by an inline arrow that
  // opens a block. The optional ``async`` keyword catches the
  // ``useEffect(async () => {...})`` form too — ``useEffect`` returns its
  // callback's return value, so a Promise-returning arrow is technically a
  // bug, but if a future edit introduces one the same lint should still
  // fire. We then walk the body manually with a brace counter.
  const ENTRY_RE = /useEffect\s*\(\s*(?:async\s*)?\(\s*\)\s*=>\s*\{/g;
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
    const refetchInBody = /\brefetch\s*\(/.exec(body);
    if (refetchInBody) {
      const linesBefore = source.slice(0, bodyStart + refetchInBody.index);
      offenders.push((linesBefore.match(/\n/g)?.length ?? 0) + 1);
    }
  }
  return offenders;
}
