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
    // legitimate refetch sites and are not matched by this regex (neither is
    // inside a useEffect).
    const USE_EFFECT_REFETCH_RE =
      /useEffect\s*\(\s*\(\s*\)\s*=>\s*\{[^}]*\brefetch\s*\(/s;
    expect(
      USE_EFFECT_REFETCH_RE.test(EXTRACTS_TSX),
      "Extracts.tsx must not call refetch() from a useEffect — " +
        "Apollo's useQuery already refetches when its variables change. " +
        "AuthGate already clears the cache on login/logout. See the " +
        "comment block where the auth-change effect was removed."
    ).toBe(false);
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
    // The slim query wires both, and the view passes them through.
    expect(EXTRACTS_TSX).toMatch(/\bEXTRACTS_PAGE_SIZE\b/);
    expect(EXTRACTS_TSX).toMatch(/limit\s*:\s*EXTRACTS_PAGE_SIZE/);
    expect(EXTRACTS_TSX).toMatch(
      /cursor\s*:\s*data\.extracts\.pageInfo\.endCursor/
    );
  });
});
