import { describe, it, expect } from "vitest";
import { filterRelationshipLabels } from "../DocumentRelationshipModal";
import { LabelType } from "../../../types/graphql-api";

const makeLabel = (
  overrides: Partial<{
    id: string;
    text: string | null;
    labelType: string | undefined;
  }> = {}
) => ({
  id: "l-1",
  text: "references",
  labelType: LabelType.RelationshipLabel,
  ...overrides,
});

describe("filterRelationshipLabels", () => {
  it("returns empty list when hasCorpus is false", () => {
    const labels = [makeLabel({ id: "l-1", text: "references" })];
    expect(filterRelationshipLabels(labels, "", false)).toEqual([]);
  });

  it("returns empty list for null/undefined labels", () => {
    expect(filterRelationshipLabels(null, "", true)).toEqual([]);
    expect(filterRelationshipLabels(undefined, "", true)).toEqual([]);
  });

  it("keeps only RelationshipLabel typed labels", () => {
    const labels = [
      makeLabel({ id: "l-1", text: "references" }),
      makeLabel({ id: "l-2", text: "header", labelType: LabelType.TokenLabel }),
      makeLabel({ id: "l-3", text: "amends" }),
    ];
    const out = filterRelationshipLabels(labels, "", true);
    expect(out.map((l) => l.id)).toEqual(["l-1", "l-3"]);
  });

  it("excludes labels whose labelType is undefined (not just null)", () => {
    // Strict equality `=== LabelType.RelationshipLabel` excludes both null
    // and undefined; this exercises the undefined edge-case explicitly so a
    // future refactor doesn't accidentally start accepting unset labelType.
    const labels = [
      makeLabel({ id: "l-1", text: "references" }),
      makeLabel({ id: "l-2", text: "header", labelType: undefined }),
    ];
    const out = filterRelationshipLabels(labels, "", true);
    expect(out.map((l) => l.id)).toEqual(["l-1"]);
  });

  it("returns all relationship labels unfiltered when searchTerm is empty", () => {
    const labels = [
      makeLabel({ id: "l-1", text: "references" }),
      makeLabel({ id: "l-2", text: "amends" }),
    ];
    expect(filterRelationshipLabels(labels, "", true)).toHaveLength(2);
  });

  it("filters by case-insensitive substring match on text", () => {
    const labels = [
      makeLabel({ id: "l-1", text: "References" }),
      makeLabel({ id: "l-2", text: "amends" }),
      makeLabel({ id: "l-3", text: "supersedes" }),
    ];
    const out = filterRelationshipLabels(labels, "REF", true);
    expect(out.map((l) => l.id)).toEqual(["l-1"]);
  });

  it("treats null text as empty string (does not match any needle)", () => {
    const labels = [
      makeLabel({ id: "l-1", text: null }),
      makeLabel({ id: "l-2", text: "references" }),
    ];
    const out = filterRelationshipLabels(labels, "ref", true);
    expect(out.map((l) => l.id)).toEqual(["l-2"]);
  });

  it("returns empty array when no relationship labels match needle", () => {
    const labels = [makeLabel({ id: "l-1", text: "references" })];
    expect(filterRelationshipLabels(labels, "zzz", true)).toEqual([]);
  });
});
