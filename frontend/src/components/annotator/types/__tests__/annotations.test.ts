/**
 * Regression net for the annotation data classes:
 *   - ServerTokenAnnotation (.update, immutability, ID preservation)
 *   - ServerSpanAnnotation  (.update, immutability, ID preservation)
 *   - PdfAnnotations        (.saved, .undoAnnotation — reducer-style returns)
 *   - RelationGroup         (.fromObject, .updateForAnnotationDeletion)
 *   - ServerTokenAnnotation.fromObject
 *
 * The PdfAnnotator package will ship these classes as its public type
 * surface. Any silent change to .update() semantics, the readonly fields,
 * or the reducer-style return of PdfAnnotations would break downstream
 * consumers, so they are pinned here.
 *
 */
import { describe, it, expect } from "vitest";
import {
  PdfAnnotations,
  RelationGroup,
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../annotations";
import type { AnnotationLabelType } from "../../../../types/graphql-api";
import { PermissionTypes } from "../../../types";

// ───────────────────────────────────────────────────────────────
// Fixtures
// ───────────────────────────────────────────────────────────────
const labelA: AnnotationLabelType = {
  id: "label-a",
  text: "Label A",
  color: "#ff0000",
  description: "A",
  labelType: "SPAN_LABEL" as any,
  icon: "tag" as any,
  readonly: false,
};

const labelB: AnnotationLabelType = {
  id: "label-b",
  text: "Label B",
  color: "#00ff00",
  description: "B",
  labelType: "SPAN_LABEL" as any,
  icon: "tag" as any,
  readonly: false,
};

const minimalJson = {
  0: {
    bounds: { top: 0, bottom: 10, left: 0, right: 10 },
    rawText: "hello",
    tokensJsons: [{ pageIndex: 0, tokenIndex: 0 }],
  },
};

function makeToken(id = "tok-1"): ServerTokenAnnotation {
  return new ServerTokenAnnotation(
    0,
    labelA,
    "hello",
    false,
    minimalJson as any,
    [PermissionTypes.CAN_READ, PermissionTypes.CAN_UPDATE],
    false,
    false,
    false,
    id
  );
}

function makeSpan(id = "span-1"): ServerSpanAnnotation {
  return new ServerSpanAnnotation(
    0,
    labelA,
    "hello",
    false,
    { start: 0, end: 5 },
    [PermissionTypes.CAN_READ],
    false,
    false,
    false,
    id
  );
}

// ───────────────────────────────────────────────────────────────
// Tests
// ───────────────────────────────────────────────────────────────
describe("ServerTokenAnnotation", () => {
  it("preserves the id passed to the constructor", () => {
    expect(makeToken("custom-id").id).toBe("custom-id");
  });

  it("generates a uuid when no id is supplied", () => {
    const annot = new ServerTokenAnnotation(
      0,
      labelA,
      "",
      false,
      minimalJson as any,
      [],
      false,
      false
    );
    expect(annot.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
    );
  });

  describe(".update()", () => {
    it("returns a new instance (does not mutate the original)", () => {
      const original = makeToken("tok-1");
      const updated = original.update({ approved: true });
      expect(updated).not.toBe(original);
      expect(original.approved).toBe(false);
      expect(updated.approved).toBe(true);
    });

    it("preserves the id across updates", () => {
      const original = makeToken("tok-1");
      const updated = original.update({ rawText: "changed" });
      expect(updated.id).toBe("tok-1");
    });

    it("applies a partial delta and keeps other fields intact", () => {
      const original = makeToken();
      const updated = original.update({
        annotationLabel: labelB,
        rejected: true,
      });
      expect(updated.annotationLabel).toBe(labelB);
      expect(updated.rejected).toBe(true);
      expect(updated.rawText).toBe(original.rawText);
      expect(updated.page).toBe(original.page);
      expect(updated.structural).toBe(original.structural);
    });

    it("copies the annotationLabel by value when none is provided in the delta", () => {
      // The implementation does `Object.assign({}, this.annotationLabel)` when
      // delta.annotationLabel is undefined — so the returned annotation has a
      // DIFFERENT label object than the original (shallow clone).
      const original = makeToken();
      const updated = original.update({});
      expect(updated.annotationLabel).not.toBe(original.annotationLabel);
      expect(updated.annotationLabel).toEqual(original.annotationLabel);
    });

    it("accepts an empty delta and returns an equivalent-but-new instance", () => {
      const original = makeToken();
      const updated = original.update();
      expect(updated).not.toBe(original);
      expect(updated.id).toBe(original.id);
      expect(updated.rawText).toBe(original.rawText);
    });
  });

  describe(".fromObject()", () => {
    it("reconstructs a class instance from a plain-object clone", () => {
      const original = makeToken("tok-1");
      const plain = JSON.parse(JSON.stringify(original));
      const reconstructed = ServerTokenAnnotation.fromObject(plain);
      expect(reconstructed).toBeInstanceOf(ServerTokenAnnotation);
      expect(reconstructed.id).toBe(original.id);
      expect(reconstructed.rawText).toBe(original.rawText);
    });
  });
});

describe("ServerSpanAnnotation", () => {
  it("preserves the id passed to the constructor", () => {
    expect(makeSpan("span-42").id).toBe("span-42");
  });

  it(".update() returns a new instance and preserves id", () => {
    const original = makeSpan("span-1");
    const updated = original.update({ approved: true });
    expect(updated).not.toBe(original);
    expect(updated.approved).toBe(true);
    expect(original.approved).toBe(false);
    expect(updated.id).toBe("span-1");
  });
});

describe("RelationGroup", () => {
  it("preserves the id passed to the constructor", () => {
    const rel = new RelationGroup(["a"], ["b"], labelA, "rel-42");
    expect(rel.id).toBe("rel-42");
  });

  it("generates a uuid when no id is supplied", () => {
    const rel = new RelationGroup(["a"], ["b"], labelA);
    expect(rel.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
    );
  });

  it("defaults structural to false", () => {
    const rel = new RelationGroup(["a"], ["b"], labelA);
    expect(rel.structural).toBe(false);
  });

  it(".fromObject() reconstructs a class instance", () => {
    const rel = new RelationGroup(["a"], ["b"], labelA, "rel-1", true);
    const plain = JSON.parse(JSON.stringify(rel));
    const reconstructed = RelationGroup.fromObject(plain);
    expect(reconstructed).toBeInstanceOf(RelationGroup);
    expect(reconstructed.sourceIds).toEqual(["a"]);
    expect(reconstructed.targetIds).toEqual(["b"]);
    expect(reconstructed.id).toBe("rel-1");
    expect(reconstructed.structural).toBe(true);
  });

  describe(".updateForAnnotationDeletion()", () => {
    it("returns undefined when the sole source is deleted", () => {
      const rel = new RelationGroup(["a"], ["b"], labelA, "rel-1");
      expect(rel.updateForAnnotationDeletion(makeToken("a"))).toBeUndefined();
    });

    it("returns undefined when the sole target is deleted", () => {
      const rel = new RelationGroup(["a"], ["b"], labelA, "rel-1");
      expect(rel.updateForAnnotationDeletion(makeToken("b"))).toBeUndefined();
    });

    it("returns undefined when the deleted annotation is sole member of both sides", () => {
      const rel = new RelationGroup(["a"], ["a"], labelA, "rel-1");
      expect(rel.updateForAnnotationDeletion(makeToken("a"))).toBeUndefined();
    });

    it("survives with updated sourceIds when one of many sources is deleted", () => {
      const rel = new RelationGroup(["a", "b"], ["c"], labelA, "rel-1", true);
      const updated = rel.updateForAnnotationDeletion(makeToken("a"));
      expect(updated).toBeInstanceOf(RelationGroup);
      expect(updated!.sourceIds).toEqual(["b"]);
      expect(updated!.targetIds).toEqual(["c"]);
      // Preserve identity/structural so persistence treats it as same entity.
      expect(updated!.id).toBe("rel-1");
      expect(updated!.structural).toBe(true);
    });

    it("survives with updated targetIds when one of many targets is deleted", () => {
      const rel = new RelationGroup(["a"], ["b", "c"], labelA, "rel-1", true);
      const updated = rel.updateForAnnotationDeletion(makeToken("b"));
      expect(updated).toBeInstanceOf(RelationGroup);
      expect(updated!.sourceIds).toEqual(["a"]);
      expect(updated!.targetIds).toEqual(["c"]);
      expect(updated!.id).toBe("rel-1");
      expect(updated!.structural).toBe(true);
    });

    it("survives unchanged when the deleted annotation is not in the relation", () => {
      const rel = new RelationGroup(["a"], ["b"], labelA, "rel-1");
      const updated = rel.updateForAnnotationDeletion(makeToken("z"));
      expect(updated).toBeInstanceOf(RelationGroup);
      expect(updated!.sourceIds).toEqual(["a"]);
      expect(updated!.targetIds).toEqual(["b"]);
      expect(updated!.id).toBe("rel-1");
      expect(updated!.structural).toBe(false);
    });
  });
});

describe("PdfAnnotations", () => {
  it("defaults unsavedChanges to false", () => {
    const pdf = new PdfAnnotations([], [], []);
    expect(pdf.unsavedChanges).toBe(false);
  });

  describe(".saved()", () => {
    it("returns a new instance with unsavedChanges=false", () => {
      const pdf = new PdfAnnotations([makeToken()], [], [], true);
      const saved = pdf.saved();
      expect(saved).not.toBe(pdf);
      expect(saved.unsavedChanges).toBe(false);
    });

    it("preserves the annotations, relations, and docTypes arrays by reference", () => {
      const annots = [makeToken()];
      const rels: RelationGroup[] = [];
      const pdf = new PdfAnnotations(annots, rels, [], true);
      const saved = pdf.saved();
      expect(saved.annotations).toBe(annots);
      expect(saved.relations).toBe(rels);
    });
  });

  describe(".undoAnnotation()", () => {
    it("returns self when there are no annotations to pop", () => {
      const pdf = new PdfAnnotations([], [], []);
      expect(pdf.undoAnnotation()).toBe(pdf);
    });

    it("removes the last annotation and marks unsavedChanges=true", () => {
      const a = makeToken("a");
      const b = makeToken("b");
      const pdf = new PdfAnnotations([a, b], [], []);
      const undone = pdf.undoAnnotation();
      expect(undone).not.toBe(pdf);
      expect(undone.unsavedChanges).toBe(true);
      expect(undone.annotations.map((x) => x.id)).toEqual(["a"]);
    });

    it("does not mutate the original instance's annotations array", () => {
      const a = makeToken("a");
      const b = makeToken("b");
      const originalArray = [a, b];
      const pdf = new PdfAnnotations(originalArray, [], []);
      pdf.undoAnnotation();
      expect(pdf.annotations).toBe(originalArray);
      expect(pdf.annotations.map((x) => x.id)).toEqual(["a", "b"]);
      expect(originalArray.map((x) => x.id)).toEqual(["a", "b"]);
    });

    it("prunes any relations that referenced only the popped annotation", () => {
      const a = makeToken("a");
      const b = makeToken("b");
      // orphanRel has "b" as its sole source; popping "b" empties sourceIds
      // and must drop the whole relation.
      const orphanRel = new RelationGroup(["b"], ["a"], labelA, "rel-1");
      // survivorRel does not reference "b"; it should remain.
      const survivorRel = new RelationGroup(["a"], ["a"], labelA, "rel-2");
      const pdf = new PdfAnnotations([a, b], [orphanRel, survivorRel], []);
      const undone = pdf.undoAnnotation();
      expect(undone.relations).toHaveLength(1);
      expect(undone.relations[0].sourceIds).toEqual(["a"]);
      expect(undone.relations[0].targetIds).toEqual(["a"]);
    });

    it("prunes relations left with no targets after deletion", () => {
      const a = makeToken("a");
      const b = makeToken("b");
      // Target side references only "b"; popping "b" empties the target.
      const orphanRel = new RelationGroup(["a"], ["b"], labelA, "rel-1");
      const pdf = new PdfAnnotations([a, b], [orphanRel], []);
      const undone = pdf.undoAnnotation();
      expect(undone.relations).toHaveLength(0);
    });
  });
});
