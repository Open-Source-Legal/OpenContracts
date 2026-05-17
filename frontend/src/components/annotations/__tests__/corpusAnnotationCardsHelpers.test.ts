/**
 * Unit tests for the pure helpers behind ``CorpusAnnotationCards``'s
 * blockContext deep-link wiring (issue #1645). The component itself
 * pulls Apollo + the router so we cover the data-shape logic here.
 */

import { describe, expect, it } from "vitest";
import {
  buildAnnotationClickQueryParams,
  buildBlockRelationshipIdMap,
} from "../corpusAnnotationCardsHelpers";
import type { SemanticSearchResult } from "../../../graphql/queries";

function makeResult(
  annotationId: string,
  blockRelationshipId?: string
): SemanticSearchResult {
  return {
    annotation: { id: annotationId } as SemanticSearchResult["annotation"],
    similarityScore: 0.9,
    document: null,
    corpus: null,
    blockContext: blockRelationshipId
      ? {
          relationshipId: blockRelationshipId,
          sourceAnnotationId: annotationId,
          sourceText: "src",
          targetAnnotationIds: ["t1", "t2"],
          blockText: "block",
        }
      : null,
  };
}

describe("buildBlockRelationshipIdMap", () => {
  it("returns an empty map when semantic search is inactive", () => {
    const map = buildBlockRelationshipIdMap(false, [
      makeResult("a-1", "rel-42"),
    ]);
    expect(map.size).toBe(0);
  });

  it("returns an empty map when results have no blockContext", () => {
    const map = buildBlockRelationshipIdMap(true, [
      makeResult("a-1"),
      makeResult("a-2"),
    ]);
    expect(map.size).toBe(0);
  });

  it("maps annotation id → relationship id for results carrying blockContext", () => {
    const map = buildBlockRelationshipIdMap(true, [
      makeResult("a-1", "rel-42"),
      makeResult("a-2"),
      makeResult("a-3", "rel-7"),
    ]);
    expect(map.get("a-1")).toBe("rel-42");
    expect(map.get("a-2")).toBeUndefined();
    expect(map.get("a-3")).toBe("rel-7");
  });
});

describe("buildAnnotationClickQueryParams", () => {
  it("includes only annotationIds when no analysis or block relationship", () => {
    const params = buildAnnotationClickQueryParams({ id: "a-1" }, new Map());
    expect(params).toEqual({ annotationIds: ["a-1"] });
  });

  it("includes analysisIds when the annotation came from an analysis", () => {
    const params = buildAnnotationClickQueryParams(
      { id: "a-1", analysis: { id: "an-9" } },
      new Map()
    );
    expect(params.analysisIds).toEqual(["an-9"]);
  });

  it("includes relationshipId when the annotation has a containing block", () => {
    const map = new Map([["a-1", "rel-42"]]);
    const params = buildAnnotationClickQueryParams({ id: "a-1" }, map);
    expect(params.relationshipId).toBe("rel-42");
  });

  it("omits relationshipId for annotations not present in the block map", () => {
    const map = new Map([["a-1", "rel-42"]]);
    const params = buildAnnotationClickQueryParams({ id: "a-2" }, map);
    expect(params.relationshipId).toBeUndefined();
  });
});
