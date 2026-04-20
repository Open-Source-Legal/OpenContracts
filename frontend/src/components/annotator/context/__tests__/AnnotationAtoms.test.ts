/**
 * Regression net for the derived annotation atoms:
 *   - allAnnotationsAtom   → de-duplicated union of pdfAnnotations.annotations
 *                            and structuralAnnotations (structural appended,
 *                            duplicates skipped by id)
 *   - perPageAnnotationsAtom → Map<pageIndex, annotations[]> bucketed from the
 *                              canonical list
 *
 * These computed atoms will move with the PdfAnnotator package and must keep
 * the same dedup + bucketing semantics.
 */
import { createStore } from "jotai";
import { describe, it, expect } from "vitest";
import {
  allAnnotationsAtom,
  pdfAnnotationsAtom,
  perPageAnnotationsAtom,
  structuralAnnotationsAtom,
} from "../AnnotationAtoms";
import { PdfAnnotations, ServerTokenAnnotation } from "../../types/annotations";
import type { AnnotationLabelType } from "../../../../types/graphql-api";

// ───────────────────────────────────────────────────────────────
// Fixtures
// ───────────────────────────────────────────────────────────────
const label: AnnotationLabelType = {
  id: "label-1",
  text: "Label",
  color: "#000",
  description: "",
  labelType: "SPAN_LABEL" as any,
  icon: "tag" as any,
  readonly: false,
};

const json = {
  0: {
    bounds: { top: 0, bottom: 10, left: 0, right: 10 },
    rawText: "",
    tokensJsons: [],
  },
};

function token(
  id: string,
  page = 0,
  structural = false
): ServerTokenAnnotation {
  return new ServerTokenAnnotation(
    page,
    label,
    "raw",
    structural,
    json as any,
    [],
    false,
    false,
    false,
    id
  );
}

// ───────────────────────────────────────────────────────────────
// Tests
// ───────────────────────────────────────────────────────────────
describe("allAnnotationsAtom", () => {
  it("returns only pdf annotations when structural list is empty", () => {
    const store = createStore();
    store.set(
      pdfAnnotationsAtom,
      new PdfAnnotations([token("a"), token("b")], [], [])
    );
    expect(store.get(allAnnotationsAtom).map((x) => x.id)).toEqual(["a", "b"]);
  });

  it("returns only structural annotations when pdf list is empty", () => {
    const store = createStore();
    store.set(structuralAnnotationsAtom, [token("s1", 0, true)]);
    expect(store.get(allAnnotationsAtom).map((x) => x.id)).toEqual(["s1"]);
  });

  it("concatenates pdf annotations before structural annotations", () => {
    const store = createStore();
    store.set(
      pdfAnnotationsAtom,
      new PdfAnnotations([token("pdf-1"), token("pdf-2")], [], [])
    );
    store.set(structuralAnnotationsAtom, [token("struct-1", 0, true)]);
    expect(store.get(allAnnotationsAtom).map((x) => x.id)).toEqual([
      "pdf-1",
      "pdf-2",
      "struct-1",
    ]);
  });

  it("de-duplicates by id: pdf annotation wins over structural with same id", () => {
    const store = createStore();
    const pdfCopy = token("dup");
    const structuralCopy = token("dup", 0, true);
    store.set(pdfAnnotationsAtom, new PdfAnnotations([pdfCopy], [], []));
    store.set(structuralAnnotationsAtom, [structuralCopy]);

    const out = store.get(allAnnotationsAtom);
    expect(out).toHaveLength(1);
    expect(out[0]).toBe(pdfCopy); // the structural copy is dropped
  });

  it("is recomputed when either source atom changes", () => {
    const store = createStore();
    store.set(pdfAnnotationsAtom, new PdfAnnotations([token("a")], [], []));
    expect(store.get(allAnnotationsAtom).map((x) => x.id)).toEqual(["a"]);

    store.set(structuralAnnotationsAtom, [token("s", 0, true)]);
    expect(store.get(allAnnotationsAtom).map((x) => x.id)).toEqual(["a", "s"]);

    store.set(pdfAnnotationsAtom, new PdfAnnotations([], [], []));
    expect(store.get(allAnnotationsAtom).map((x) => x.id)).toEqual(["s"]);
  });
});

describe("perPageAnnotationsAtom", () => {
  it("buckets annotations by their .page field", () => {
    const store = createStore();
    store.set(
      pdfAnnotationsAtom,
      new PdfAnnotations([token("a", 0), token("b", 0), token("c", 2)], [], [])
    );
    const map = store.get(perPageAnnotationsAtom);
    expect(map.get(0)?.map((x) => x.id)).toEqual(["a", "b"]);
    expect(map.get(2)?.map((x) => x.id)).toEqual(["c"]);
    expect(map.get(1)).toBeUndefined();
  });

  it("treats undefined .page as page 0", () => {
    const store = createStore();
    const weirdTok = token("x", 0);
    // @ts-expect-error: intentionally stomp on readonly for the test
    weirdTok.page = undefined;
    store.set(pdfAnnotationsAtom, new PdfAnnotations([weirdTok], [], []));
    const map = store.get(perPageAnnotationsAtom);
    expect(map.get(0)?.map((x) => x.id)).toEqual(["x"]);
  });

  it("includes structural annotations via the allAnnotations dedup pipeline", () => {
    const store = createStore();
    store.set(pdfAnnotationsAtom, new PdfAnnotations([token("a", 0)], [], []));
    store.set(structuralAnnotationsAtom, [token("s", 1, true)]);
    const map = store.get(perPageAnnotationsAtom);
    expect(map.get(0)?.map((x) => x.id)).toEqual(["a"]);
    expect(map.get(1)?.map((x) => x.id)).toEqual(["s"]);
  });

  it("returns an empty Map when there are no annotations at all", () => {
    const store = createStore();
    const map = store.get(perPageAnnotationsAtom);
    expect(map.size).toBe(0);
  });
});
