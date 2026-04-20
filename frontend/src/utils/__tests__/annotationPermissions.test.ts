/**
 * Exhaustive branch tests for the annotation permission predicates.
 *
 * Covers issue #1269: every branch of every permission check is exercised.
 *
 * Note on semantics: the backend enforces
 *   Effective Permission = MIN(document, corpus)
 * but the frontend predicate tested here is intentionally more permissive
 * (OR). See `annotationPermissions.ts` for the rationale. Tests document the
 * actual predicate so drift is detected.
 */
import { describe, it, expect } from "vitest";
import {
  canEditAnnotationsInCorpus,
  canDeleteAnnotation,
  canUpdateAnnotation,
  AnnotationPermissionShape,
} from "../annotationPermissions";
import { PermissionTypes } from "../../components/types";

const makeAnnotation = (
  overrides: Partial<AnnotationPermissionShape> = {}
): AnnotationPermissionShape => ({
  structural: false,
  myPermissions: [],
  ...overrides,
});

describe("canEditAnnotationsInCorpus", () => {
  describe("readOnly override", () => {
    it("returns false when readOnly is true even with full permissions", () => {
      const result = canEditAnnotationsInCorpus({
        readOnly: true,
        corpusId: "corpus-1",
        canUpdateCorpus: true,
        documentPermissions: [PermissionTypes.CAN_UPDATE],
      });
      expect(result).toBe(false);
    });

    it("returns false when readOnly is true regardless of corpus context", () => {
      const result = canEditAnnotationsInCorpus({
        readOnly: true,
        corpusId: null,
        canUpdateCorpus: false,
        documentPermissions: [],
      });
      expect(result).toBe(false);
    });
  });

  describe("corpus requirement", () => {
    it("returns false without a corpus, even with document CAN_UPDATE", () => {
      const result = canEditAnnotationsInCorpus({
        readOnly: false,
        corpusId: null,
        canUpdateCorpus: false,
        documentPermissions: [PermissionTypes.CAN_UPDATE],
      });
      expect(result).toBe(false);
    });

    it("returns false for undefined corpusId", () => {
      const result = canEditAnnotationsInCorpus({
        readOnly: false,
        corpusId: undefined,
        canUpdateCorpus: true,
        documentPermissions: [PermissionTypes.CAN_UPDATE],
      });
      expect(result).toBe(false);
    });

    it("returns false for empty-string corpusId", () => {
      const result = canEditAnnotationsInCorpus({
        readOnly: false,
        corpusId: "",
        canUpdateCorpus: true,
        documentPermissions: [PermissionTypes.CAN_UPDATE],
      });
      expect(result).toBe(false);
    });
  });

  describe("permission truth table (corpus x document)", () => {
    // The predicate short-circuits on corpus, then falls back to document.
    // Each row exercises one combination of the two grant flags.
    const rows = [
      {
        name: "no corpus grant, no doc grant -> denied",
        canUpdateCorpus: false,
        documentPermissions: [] as PermissionTypes[],
        expected: false,
      },
      {
        name: "no corpus grant, doc grants CAN_UPDATE -> allowed (fallback)",
        canUpdateCorpus: false,
        documentPermissions: [PermissionTypes.CAN_UPDATE],
        expected: true,
      },
      {
        name: "corpus grants CAN_UPDATE, doc has no grant -> allowed",
        canUpdateCorpus: true,
        documentPermissions: [],
        expected: true,
      },
      {
        name: "both corpus and doc grant CAN_UPDATE -> allowed",
        canUpdateCorpus: true,
        documentPermissions: [PermissionTypes.CAN_UPDATE],
        expected: true,
      },
    ];

    rows.forEach(({ name, canUpdateCorpus, documentPermissions, expected }) => {
      it(name, () => {
        const result = canEditAnnotationsInCorpus({
          readOnly: false,
          corpusId: "corpus-1",
          canUpdateCorpus,
          documentPermissions,
        });
        expect(result).toBe(expected);
      });
    });
  });

  describe("unrelated document permissions", () => {
    it("does not allow editing when document only has non-update perms", () => {
      const result = canEditAnnotationsInCorpus({
        readOnly: false,
        corpusId: "corpus-1",
        canUpdateCorpus: false,
        documentPermissions: [
          PermissionTypes.CAN_READ,
          PermissionTypes.CAN_COMMENT,
          PermissionTypes.CAN_REMOVE,
        ],
      });
      // CAN_REMOVE does not imply CAN_UPDATE on its own.
      expect(result).toBe(false);
    });

    it("allows editing when CAN_UPDATE is present alongside others", () => {
      const result = canEditAnnotationsInCorpus({
        readOnly: false,
        corpusId: "corpus-1",
        canUpdateCorpus: false,
        documentPermissions: [
          PermissionTypes.CAN_READ,
          PermissionTypes.CAN_UPDATE,
          PermissionTypes.CAN_REMOVE,
        ],
      });
      expect(result).toBe(true);
    });
  });
});

describe("canDeleteAnnotation", () => {
  describe("structural annotation lock (read-only unless superuser)", () => {
    it("returns false for structural annotations even with CAN_REMOVE", () => {
      const annotation = makeAnnotation({
        structural: true,
        myPermissions: [PermissionTypes.CAN_REMOVE],
      });
      expect(canDeleteAnnotation(annotation, false)).toBe(false);
    });

    it("returns false for structural annotations with all permissions", () => {
      const annotation = makeAnnotation({
        structural: true,
        myPermissions: [
          PermissionTypes.CAN_READ,
          PermissionTypes.CAN_UPDATE,
          PermissionTypes.CAN_CREATE,
          PermissionTypes.CAN_REMOVE,
          PermissionTypes.CAN_PUBLISH,
          PermissionTypes.CAN_PERMISSION,
          PermissionTypes.CAN_COMMENT,
        ],
      });
      expect(canDeleteAnnotation(annotation, false)).toBe(false);
    });
  });

  describe("readOnly override", () => {
    it("returns false when readOnly is true even with CAN_REMOVE", () => {
      const annotation = makeAnnotation({
        structural: false,
        myPermissions: [PermissionTypes.CAN_REMOVE],
      });
      expect(canDeleteAnnotation(annotation, true)).toBe(false);
    });

    it("readOnly wins over structural (both false)", () => {
      const annotation = makeAnnotation({
        structural: true,
        myPermissions: [PermissionTypes.CAN_REMOVE],
      });
      expect(canDeleteAnnotation(annotation, true)).toBe(false);
    });
  });

  describe("CAN_REMOVE gate", () => {
    it("returns true when non-structural, not readonly, has CAN_REMOVE", () => {
      const annotation = makeAnnotation({
        structural: false,
        myPermissions: [PermissionTypes.CAN_REMOVE],
      });
      expect(canDeleteAnnotation(annotation, false)).toBe(true);
    });

    it("returns false when missing CAN_REMOVE even with other perms", () => {
      const annotation = makeAnnotation({
        structural: false,
        myPermissions: [
          PermissionTypes.CAN_READ,
          PermissionTypes.CAN_UPDATE,
          PermissionTypes.CAN_CREATE,
        ],
      });
      expect(canDeleteAnnotation(annotation, false)).toBe(false);
    });

    it("returns false with empty permissions", () => {
      const annotation = makeAnnotation({
        structural: false,
        myPermissions: [],
      });
      expect(canDeleteAnnotation(annotation, false)).toBe(false);
    });
  });

  describe("full truth table (structural x readOnly x CAN_REMOVE)", () => {
    // 2^3 = 8 combinations. Only one path yields true.
    const rows: Array<{
      structural: boolean;
      readOnly: boolean;
      hasRemove: boolean;
      expected: boolean;
    }> = [
      { structural: false, readOnly: false, hasRemove: false, expected: false },
      { structural: false, readOnly: false, hasRemove: true, expected: true },
      { structural: false, readOnly: true, hasRemove: false, expected: false },
      { structural: false, readOnly: true, hasRemove: true, expected: false },
      { structural: true, readOnly: false, hasRemove: false, expected: false },
      { structural: true, readOnly: false, hasRemove: true, expected: false },
      { structural: true, readOnly: true, hasRemove: false, expected: false },
      { structural: true, readOnly: true, hasRemove: true, expected: false },
    ];

    rows.forEach(({ structural, readOnly, hasRemove, expected }) => {
      const label = `structural=${structural} readOnly=${readOnly} hasRemove=${hasRemove} -> ${expected}`;
      it(label, () => {
        const annotation = makeAnnotation({
          structural,
          myPermissions: hasRemove ? [PermissionTypes.CAN_REMOVE] : [],
        });
        expect(canDeleteAnnotation(annotation, readOnly)).toBe(expected);
      });
    });
  });
});

describe("canUpdateAnnotation", () => {
  it("returns true when non-structural, not readonly, has CAN_UPDATE", () => {
    const annotation = makeAnnotation({
      structural: false,
      myPermissions: [PermissionTypes.CAN_UPDATE],
    });
    expect(canUpdateAnnotation(annotation, false)).toBe(true);
  });

  it("returns false for structural annotations with CAN_UPDATE", () => {
    const annotation = makeAnnotation({
      structural: true,
      myPermissions: [PermissionTypes.CAN_UPDATE],
    });
    expect(canUpdateAnnotation(annotation, false)).toBe(false);
  });

  it("returns false when readOnly is true even with CAN_UPDATE", () => {
    const annotation = makeAnnotation({
      structural: false,
      myPermissions: [PermissionTypes.CAN_UPDATE],
    });
    expect(canUpdateAnnotation(annotation, true)).toBe(false);
  });

  it("returns false when missing CAN_UPDATE", () => {
    const annotation = makeAnnotation({
      structural: false,
      myPermissions: [PermissionTypes.CAN_REMOVE, PermissionTypes.CAN_READ],
    });
    expect(canUpdateAnnotation(annotation, false)).toBe(false);
  });
});
