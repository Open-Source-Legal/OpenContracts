/**
 * Regression net for RelationHighlightItem — one row in the relationship
 * sidebar that represents a single source or target annotation in a
 * RelationGroup.
 *
 * Pins: source/target icon switch, page-label visibility rules (always for
 * PDF token annotations, only when page > 0 for spans), raw-text rendering,
 * read-only and handler-gated remove button, click-to-select and click-to-
 * remove wiring. The sibling HighlightItem already has its own scroll test
 * file — this covers the relationship variant that has NO dedicated test.
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { RelationHighlightItem } from "../RelationHighlightItem";
import {
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../../types/annotations";
import { PermissionTypes } from "../../../types";
import type { AnnotationLabelType } from "../../../../types/graphql-api";

// ─── Fixtures ──────────────────────────────────────────────────
const label: AnnotationLabelType = {
  id: "label-1",
  text: "Party",
  color: "#3b82f6",
  description: "Party label",
  labelType: "SPAN_LABEL" as any,
  icon: "tag" as any,
  readonly: false,
};

const minimalTokenJson = {
  0: {
    bounds: { top: 0, bottom: 10, left: 0, right: 10 },
    rawText: "Alice",
    tokensJsons: [],
  },
};

function makeTokenAnnot(
  opts: { id?: string; page?: number; rawText?: string } = {}
): ServerTokenAnnotation {
  return new ServerTokenAnnotation(
    opts.page ?? 0,
    label,
    opts.rawText ?? "Alice",
    false,
    minimalTokenJson as any,
    [PermissionTypes.CAN_READ],
    false,
    false,
    false,
    opts.id ?? "tok-1"
  );
}

function makeSpanAnnot(
  opts: { id?: string; page?: number; rawText?: string } = {}
): ServerSpanAnnotation {
  return new ServerSpanAnnotation(
    opts.page ?? 0,
    label,
    opts.rawText ?? "Alice",
    false,
    { start: 0, end: 5 },
    [PermissionTypes.CAN_READ],
    false,
    false,
    false,
    opts.id ?? "span-1"
  );
}

// ─── Tests ─────────────────────────────────────────────────────
describe("RelationHighlightItem", () => {
  let onSelect: ReturnType<typeof vi.fn>;
  let onRemove: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onSelect = vi.fn();
    onRemove = vi.fn();
  });

  describe("type switch (SOURCE vs TARGET)", () => {
    it("renders the source avatar when type=SOURCE", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot()}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      // The semantic contract is the alt text — the icon source filename is an
      // implementation detail that could change without affecting users, so we
      // only assert on `alt` here.
      const avatar = screen.getByAltText("Source");
      expect(avatar).toBeInTheDocument();
    });

    it("renders the target avatar when type=TARGET", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot()}
          type="TARGET"
          read_only={false}
          onSelect={onSelect}
        />
      );
      const avatar = screen.getByAltText("Target");
      expect(avatar).toBeInTheDocument();
    });
  });

  describe("label pill", () => {
    it("shows the annotationLabel text", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot()}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      expect(screen.getByText("Party")).toBeInTheDocument();
    });

    it("fires onSelect with annotation id when pill is clicked", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot({ id: "tok-xyz" })}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      fireEvent.click(screen.getByText("Party"));
      expect(onSelect).toHaveBeenCalledTimes(1);
      expect(onSelect).toHaveBeenCalledWith("tok-xyz");
    });
  });

  describe("page label visibility", () => {
    it("always shows page label for PDF token annotations (even page 0)", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot({ page: 0 })}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      expect(screen.getByText("Page 1")).toBeInTheDocument();
    });

    it("shows page label for PDF token annotations on later pages (1-indexed display)", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot({ page: 4 })}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      expect(screen.getByText("Page 5")).toBeInTheDocument();
    });

    it("hides page label for span annotations on page 0 (sentinel)", () => {
      render(
        <RelationHighlightItem
          annotation={makeSpanAnnot({ page: 0 })}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      expect(screen.queryByText(/^Page /)).not.toBeInTheDocument();
    });

    it("shows page label for span annotations when page > 0", () => {
      render(
        <RelationHighlightItem
          annotation={makeSpanAnnot({ page: 2 })}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      expect(screen.getByText("Page 3")).toBeInTheDocument();
    });
  });

  describe("raw text rendering", () => {
    it("renders truncated raw text when present", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot({ rawText: "Alice Liddell" })}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      expect(screen.getByText(/Alice Liddell/)).toBeInTheDocument();
    });

    it("omits raw-text block when rawText is empty", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot({ rawText: "" })}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      // The only text on the page should be the label and page label
      expect(screen.getByText("Party")).toBeInTheDocument();
      expect(screen.queryByText(/Alice/)).not.toBeInTheDocument();
    });
  });

  describe("remove button gating", () => {
    it("renders the remove button when not read-only and handler is supplied", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot()}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
          onRemoveAnnotationFromRelation={onRemove}
        />
      );
      expect(
        screen.getByLabelText("Remove annotation from relation")
      ).toBeInTheDocument();
    });

    it("hides the remove button when read-only is true even with a handler", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot()}
          type="SOURCE"
          read_only={true}
          onSelect={onSelect}
          onRemoveAnnotationFromRelation={onRemove}
        />
      );
      expect(
        screen.queryByLabelText("Remove annotation from relation")
      ).not.toBeInTheDocument();
    });

    it("hides the remove button when no handler is supplied", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot()}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
        />
      );
      expect(
        screen.queryByLabelText("Remove annotation from relation")
      ).not.toBeInTheDocument();
    });

    it("fires onRemoveAnnotationFromRelation with annotation id when clicked", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot({ id: "tok-xyz" })}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
          onRemoveAnnotationFromRelation={onRemove}
        />
      );
      fireEvent.click(screen.getByLabelText("Remove annotation from relation"));
      expect(onRemove).toHaveBeenCalledTimes(1);
      expect(onRemove).toHaveBeenCalledWith("tok-xyz");
    });

    it("clicking the remove button does not also fire onSelect (stopPropagation)", () => {
      render(
        <RelationHighlightItem
          annotation={makeTokenAnnot()}
          type="SOURCE"
          read_only={false}
          onSelect={onSelect}
          onRemoveAnnotationFromRelation={onRemove}
        />
      );
      fireEvent.click(screen.getByLabelText("Remove annotation from relation"));
      expect(onRemove).toHaveBeenCalled();
      expect(onSelect).not.toHaveBeenCalled();
    });
  });
});
