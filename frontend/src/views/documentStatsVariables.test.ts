import { describe, expect, it } from "vitest";
import { buildDocumentStatsVariables } from "./documentStatsVariables";

// Each branch of the conditional spreads matters for two reasons:
//   1. Wire payload: omitting falsy filters keeps the MockedProvider mock
//      shape stable at ``{}`` and lets the backend skip filter clauses.
//   2. Branch coverage: the inline ``&&`` spreads in Documents.tsx were the
//      patch's uncovered partials before this helper was extracted.
describe("buildDocumentStatsVariables", () => {
  it("returns an empty object when no filters are set", () => {
    expect(buildDocumentStatsVariables({})).toEqual({});
  });

  it("treats null/undefined filter values as absent", () => {
    expect(
      buildDocumentStatsVariables({
        searchTerm: null,
        labelId: undefined,
        corpus: null,
      })
    ).toEqual({});
  });

  it("treats an empty search string as absent", () => {
    // Empty strings are falsy — the Documents view leaves
    // ``documentSearchTerm`` as "" when the search box is cleared.
    expect(buildDocumentStatsVariables({ searchTerm: "" })).toEqual({});
  });

  it("includes textSearch when searchTerm is set", () => {
    expect(buildDocumentStatsVariables({ searchTerm: "contract" })).toEqual({
      textSearch: "contract",
    });
  });

  it("includes hasLabelWithId when labelId is set", () => {
    expect(buildDocumentStatsVariables({ labelId: "lbl-7" })).toEqual({
      hasLabelWithId: "lbl-7",
    });
  });

  it("includes inCorpusWithId and forces includeCaml when a corpus is set", () => {
    expect(
      buildDocumentStatsVariables({ corpus: { id: "corpus-42" } })
    ).toEqual({
      inCorpusWithId: "corpus-42",
      includeCaml: true,
    });
  });

  it("combines all three filters when all are set", () => {
    expect(
      buildDocumentStatsVariables({
        searchTerm: "contract",
        labelId: "lbl-7",
        corpus: { id: "corpus-42" },
      })
    ).toEqual({
      textSearch: "contract",
      hasLabelWithId: "lbl-7",
      inCorpusWithId: "corpus-42",
      includeCaml: true,
    });
  });
});
