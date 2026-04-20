/**
 * Regression net for useVisibleAnnotations — the single-source-of-truth
 * filter that decides which annotations get rendered in the PDF viewer and
 * sidebar.
 *
 * The hook's behavior is the contract the PdfAnnotator package must preserve
 * across the extraction: every branch (forced-by-selection, forced-by-relation,
 * structural toggle, label filter, showSelectedOnly mode) is pinned here so
 * a silent regression surfaces as a failing test.
 */
import React from "react";
import { renderHook } from "@testing-library/react-hooks";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { RelationGroup, ServerTokenAnnotation } from "../../types/annotations";
import type { AnnotationLabelType } from "../../../../types/graphql-api";
import { useVisibleAnnotations } from "../useVisibleAnnotations";

// ───────────────────────────────────────────────────────────────
// Mocks for the four hook dependencies
// ───────────────────────────────────────────────────────────────
vi.mock("../useAllAnnotations", () => ({
  useAllAnnotations: vi.fn(),
}));

vi.mock("../../context/UISettingsAtom", () => ({
  useAnnotationDisplay: vi.fn(),
  useAnnotationControls: vi.fn(),
  useAnnotationSelection: vi.fn(),
}));

vi.mock("../AnnotationHooks", () => ({
  usePdfAnnotations: vi.fn(),
}));

import { useAllAnnotations } from "../useAllAnnotations";
import {
  useAnnotationDisplay,
  useAnnotationControls,
  useAnnotationSelection,
} from "../../context/UISettingsAtom";
import { usePdfAnnotations } from "../AnnotationHooks";

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

/** Minimal valid MultipageAnnotationJson for a ServerTokenAnnotation. */
const minimalJson = {
  0: {
    bounds: { top: 0, bottom: 10, left: 0, right: 10 },
    rawText: "",
    tokensJsons: [],
  },
};

function makeAnnot(opts: {
  id: string;
  label?: AnnotationLabelType;
  structural?: boolean;
}): ServerTokenAnnotation {
  return new ServerTokenAnnotation(
    0,
    opts.label ?? labelA,
    "raw",
    opts.structural ?? false,
    minimalJson as any,
    [],
    false,
    false,
    false,
    opts.id
  );
}

interface State {
  annotations: ServerTokenAnnotation[];
  relations: RelationGroup[];
  display: {
    showStructural: boolean;
    showStructuralRelationships: boolean;
    showSelectedOnly: boolean;
  };
  controls: {
    spanLabelsToView: AnnotationLabelType[] | null;
  };
  selection: {
    selectedAnnotations: string[];
    selectedRelations: RelationGroup[];
  };
}

function defaultState(overrides: Partial<State> = {}): State {
  return {
    annotations: [],
    relations: [],
    display: {
      showStructural: true,
      showStructuralRelationships: false,
      showSelectedOnly: false,
    },
    controls: { spanLabelsToView: null },
    selection: { selectedAnnotations: [], selectedRelations: [] },
    ...overrides,
  };
}

function primeMocks(state: State): void {
  // NOTE: In production, `useAllAnnotations` returns a de-duplicated UNION of
  // `pdfAnnotations.annotations` and the structural annotations atom, while
  // `pdfAnnotations.annotations` holds only the PDF annotations. These tests
  // pass the same fixture array to both because the hook under test consumes
  // `useAllAnnotations` for the visibility predicate and `pdfAnnotations.relations`
  // (not `pdfAnnotations.annotations`) for the relation-forced-visibility logic,
  // so the two sources never interact in this test's reads. Collapsing them
  // keeps fixtures simple; don't copy this conflation into tests that assert on
  // dedup behavior.
  (useAllAnnotations as any).mockReturnValue(state.annotations);
  (usePdfAnnotations as any).mockReturnValue({
    pdfAnnotations: {
      annotations: state.annotations,
      relations: state.relations,
      docTypes: [],
    },
  });
  (useAnnotationDisplay as any).mockReturnValue(state.display);
  (useAnnotationControls as any).mockReturnValue(state.controls);
  (useAnnotationSelection as any).mockReturnValue(state.selection);
}

// ───────────────────────────────────────────────────────────────
// Tests
// ───────────────────────────────────────────────────────────────
describe("useVisibleAnnotations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns every annotation when no filters are active", () => {
    const a = makeAnnot({ id: "a" });
    const b = makeAnnot({ id: "b" });
    primeMocks(defaultState({ annotations: [a, b] }));

    const { result } = renderHook(() => useVisibleAnnotations());
    expect(result.current.map((x) => x.id)).toEqual(["a", "b"]);
  });

  describe("structural filter", () => {
    it("hides structural annotations when showStructural is false", () => {
      const regular = makeAnnot({ id: "reg" });
      const structural = makeAnnot({ id: "struct", structural: true });
      primeMocks(
        defaultState({
          annotations: [regular, structural],
          display: {
            showStructural: false,
            showStructuralRelationships: false,
            showSelectedOnly: false,
          },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id)).toEqual(["reg"]);
    });

    it("keeps structural annotations when showStructural is true", () => {
      const regular = makeAnnot({ id: "reg" });
      const structural = makeAnnot({ id: "struct", structural: true });
      primeMocks(defaultState({ annotations: [regular, structural] }));

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id)).toEqual(["reg", "struct"]);
    });
  });

  describe("label filter (spanLabelsToView)", () => {
    it("keeps only annotations whose label is in spanLabelsToView", () => {
      const withA = makeAnnot({ id: "a-annot", label: labelA });
      const withB = makeAnnot({ id: "b-annot", label: labelB });
      primeMocks(
        defaultState({
          annotations: [withA, withB],
          controls: { spanLabelsToView: [labelA] },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id)).toEqual(["a-annot"]);
    });

    it("treats an empty spanLabelsToView array as 'no filter'", () => {
      const withA = makeAnnot({ id: "a-annot", label: labelA });
      const withB = makeAnnot({ id: "b-annot", label: labelB });
      primeMocks(
        defaultState({
          annotations: [withA, withB],
          controls: { spanLabelsToView: [] },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current).toHaveLength(2);
    });

    it("applies label filter to structural annotations too", () => {
      const structA = makeAnnot({ id: "sa", label: labelA, structural: true });
      const structB = makeAnnot({ id: "sb", label: labelB, structural: true });
      primeMocks(
        defaultState({
          annotations: [structA, structB],
          controls: { spanLabelsToView: [labelB] },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id)).toEqual(["sb"]);
    });
  });

  describe("forced-by-selection", () => {
    it("keeps a selected annotation even if its label is filtered out", () => {
      const withA = makeAnnot({ id: "a-annot", label: labelA });
      const withB = makeAnnot({ id: "b-annot", label: labelB });
      primeMocks(
        defaultState({
          annotations: [withA, withB],
          controls: { spanLabelsToView: [labelA] }, // B would be filtered…
          selection: {
            selectedAnnotations: ["b-annot"], // …but it is selected.
            selectedRelations: [],
          },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id).sort()).toEqual([
        "a-annot",
        "b-annot",
      ]);
    });

    it("keeps a selected structural annotation even when showStructural is false", () => {
      const structural = makeAnnot({ id: "struct", structural: true });
      primeMocks(
        defaultState({
          annotations: [structural],
          display: {
            showStructural: false,
            showStructuralRelationships: false,
            showSelectedOnly: false,
          },
          selection: {
            selectedAnnotations: ["struct"],
            selectedRelations: [],
          },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id)).toEqual(["struct"]);
    });
  });

  describe("forced-by-selected-relation", () => {
    it("shows source + target annotations of a selected relation (showStructural=true)", () => {
      const src = makeAnnot({ id: "src", label: labelB });
      const tgt = makeAnnot({ id: "tgt", label: labelB });
      const other = makeAnnot({ id: "other", label: labelB });
      const rel = new RelationGroup(["src"], ["tgt"], labelA, "rel-1");

      primeMocks(
        defaultState({
          annotations: [src, tgt, other],
          relations: [rel],
          // label filter would hide ALL three (they have labelB, filter is labelA)
          controls: { spanLabelsToView: [labelA] },
          selection: {
            selectedAnnotations: [],
            selectedRelations: [rel],
          },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      const ids = result.current.map((x) => x.id).sort();
      expect(ids).toEqual(["src", "tgt"]); // "other" still filtered out
    });

    it("applies forced-by-selected-relation even when showStructural is false (issue #1289)", () => {
      // Explicit relation selection is a user-initiated signal and should
      // force its members visible regardless of the showStructural toggle,
      // mirroring the behavior of forcedBySelection for individual annotations.
      const src = makeAnnot({ id: "src" });
      const tgt = makeAnnot({ id: "tgt" });
      const rel = new RelationGroup(["src"], ["tgt"], labelA, "rel-1");

      primeMocks(
        defaultState({
          annotations: [src, tgt],
          relations: [rel],
          display: {
            showStructural: false,
            showStructuralRelationships: false,
            showSelectedOnly: false,
          },
          controls: { spanLabelsToView: [labelB] }, // would otherwise exclude both
          selection: {
            selectedAnnotations: [],
            selectedRelations: [rel],
          },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id).sort()).toEqual(["src", "tgt"]);
    });

    it("keeps structural relation members visible when showStructural is false but the relation is selected", () => {
      // Relation members that happen to be structural should still be forced
      // visible when the user has explicitly selected the relation, even with
      // the structural toggle off.
      const src = makeAnnot({ id: "src", structural: true });
      const tgt = makeAnnot({ id: "tgt", structural: true });
      const rel = new RelationGroup(["src"], ["tgt"], labelA, "rel-1");

      primeMocks(
        defaultState({
          annotations: [src, tgt],
          relations: [rel],
          display: {
            showStructural: false,
            showStructuralRelationships: false,
            showSelectedOnly: false,
          },
          selection: {
            selectedAnnotations: [],
            selectedRelations: [rel],
          },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id).sort()).toEqual(["src", "tgt"]);
    });
  });

  describe("forced-by-all-relationships", () => {
    it("when showStructuralRelationships is on (and showStructural is on), all relation members are visible", () => {
      const src = makeAnnot({ id: "src", label: labelB });
      const tgt = makeAnnot({ id: "tgt", label: labelB });
      const loose = makeAnnot({ id: "loose", label: labelB });
      const rel = new RelationGroup(["src"], ["tgt"], labelA, "rel-1");

      primeMocks(
        defaultState({
          annotations: [src, tgt, loose],
          relations: [rel],
          display: {
            showStructural: true,
            showStructuralRelationships: true,
            showSelectedOnly: false,
          },
          controls: { spanLabelsToView: [labelA] }, // would hide all three
          selection: { selectedAnnotations: [], selectedRelations: [] },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      const ids = result.current.map((x) => x.id).sort();
      expect(ids).toEqual(["src", "tgt"]); // loose still hidden
    });

    it("stays gated on showStructural: does NOT force-show relation members when showStructural is false and no relation is selected", () => {
      // Companion to the issue #1289 fix: the *explicit* selected-relation
      // bypass is un-gated, but the *implicit* showStructuralRelationships
      // bypass must remain gated on showStructural — otherwise toggling
      // structural off would have no effect on relation members at all.
      const src = makeAnnot({ id: "src", structural: true });
      const tgt = makeAnnot({ id: "tgt", structural: true });
      const rel = new RelationGroup(["src"], ["tgt"], labelA, "rel-1");

      primeMocks(
        defaultState({
          annotations: [src, tgt],
          relations: [rel],
          display: {
            showStructural: false, // structural off
            showStructuralRelationships: true, // but "show all" is on
            showSelectedOnly: false,
          },
          selection: { selectedAnnotations: [], selectedRelations: [] }, // no explicit selection
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      // Both members are structural and nothing forces them visible, so
      // the structural filter hides them.
      expect(result.current.map((x) => x.id)).toEqual([]);
    });
  });

  describe("showSelectedOnly mode", () => {
    it("hides every annotation that is neither selected nor connected via a selected relation", () => {
      const selected = makeAnnot({ id: "sel" });
      const connected = makeAnnot({ id: "conn" });
      const unrelated = makeAnnot({ id: "other" });
      const rel = new RelationGroup(["sel"], ["conn"], labelA, "rel-1");

      primeMocks(
        defaultState({
          annotations: [selected, connected, unrelated],
          relations: [rel],
          display: {
            showStructural: true,
            showStructuralRelationships: false,
            showSelectedOnly: true,
          },
          selection: {
            selectedAnnotations: ["sel"],
            selectedRelations: [rel],
          },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      const ids = result.current.map((x) => x.id).sort();
      expect(ids).toEqual(["conn", "sel"]);
    });

    it("hides connected annotations when the linking relation is NOT selected", () => {
      const selected = makeAnnot({ id: "sel" });
      const other = makeAnnot({ id: "other" });
      const rel = new RelationGroup(["sel"], ["other"], labelA, "rel-1");

      primeMocks(
        defaultState({
          annotations: [selected, other],
          relations: [rel],
          display: {
            showStructural: true,
            showStructuralRelationships: false,
            showSelectedOnly: true,
          },
          selection: {
            selectedAnnotations: ["sel"],
            selectedRelations: [], // relation not selected
          },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id)).toEqual(["sel"]);
    });
  });

  describe("combined filters", () => {
    it("respects precedence: forced-by-selection beats showSelectedOnly + label filter", () => {
      const selected = makeAnnot({ id: "sel", label: labelB });
      const filtered = makeAnnot({ id: "filt", label: labelB });

      primeMocks(
        defaultState({
          annotations: [selected, filtered],
          display: {
            showStructural: true,
            showStructuralRelationships: false,
            showSelectedOnly: true,
          },
          controls: { spanLabelsToView: [labelA] },
          selection: {
            selectedAnnotations: ["sel"],
            selectedRelations: [],
          },
        })
      );

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id)).toEqual(["sel"]);
    });
  });

  describe("null safety", () => {
    it("handles missing pdfAnnotations gracefully (no relations)", () => {
      const a = makeAnnot({ id: "a" });
      (useAllAnnotations as any).mockReturnValue([a]);
      (usePdfAnnotations as any).mockReturnValue({ pdfAnnotations: null });
      (useAnnotationDisplay as any).mockReturnValue({
        showStructural: true,
        showStructuralRelationships: true,
        showSelectedOnly: false,
      });
      (useAnnotationControls as any).mockReturnValue({
        spanLabelsToView: null,
      });
      (useAnnotationSelection as any).mockReturnValue({
        selectedAnnotations: [],
        selectedRelations: [],
      });

      const { result } = renderHook(() => useVisibleAnnotations());
      expect(result.current.map((x) => x.id)).toEqual(["a"]);
    });
  });
});
