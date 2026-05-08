/**
 * Focused tests for HighlightItem scroll-to-annotation behavior and page display.
 *
 * Verifies:
 * 1. scrollIntoView is only called for PDF token annotations, not text span annotations.
 * 2. Page labels always appear for PDF token annotations (page is always meaningful).
 * 3. Page labels appear for span annotations only when page > 0 (page=0 is a sentinel).
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { HighlightItem } from "../HighlightItem";
import {
  ServerTokenAnnotation,
  ServerSpanAnnotation,
} from "../../types/annotations";
import { PermissionTypes } from "../../../types";
import { LabelType } from "../../../../types/graphql-api";

// ---------- Mocks ----------

const mockScrollIntoView = vi.fn();

vi.mock("../../hooks/useAnnotationRefs", () => ({
  useAnnotationRefs: () => ({
    annotationElementRefs: {
      current: {
        "token-annot-1": { scrollIntoView: mockScrollIntoView },
        "span-annot-1": { scrollIntoView: mockScrollIntoView },
      },
    },
  }),
}));

vi.mock("../../context/UISettingsAtom", () => ({
  useAnnotationSelection: () => ({
    selectedAnnotations: [],
  }),
}));

vi.mock("../../hooks/useAnnotationImages", () => ({
  useAnnotationImages: () => ({
    images: [],
    loading: false,
    error: false,
    hasFetchedEmpty: false,
  }),
}));

// ---------- Helpers ----------

const mockLabel = {
  id: "label-1",
  text: "Test Label",
  color: "#3B82F6",
  icon: "tag" as any,
  description: "Test label",
  labelType: LabelType.SpanLabel,
};

function makeTokenAnnotation(page: number) {
  return new ServerTokenAnnotation(
    page,
    mockLabel,
    "Token text",
    false,
    {},
    [PermissionTypes.CAN_READ],
    false,
    false,
    false,
    "token-annot-1"
  );
}

function makeSpanAnnotation(page: number) {
  return new ServerSpanAnnotation(
    page,
    mockLabel,
    "Span text",
    false,
    { start: 0, end: 9 },
    [PermissionTypes.CAN_READ],
    false,
    false,
    false,
    "span-annot-1"
  );
}

function renderHighlightItem(
  annotation: ServerTokenAnnotation | ServerSpanAnnotation
) {
  return render(
    <MemoryRouter>
      <HighlightItem
        annotation={annotation}
        read_only
        relations={[]}
        onSelect={vi.fn()}
      />
    </MemoryRouter>
  );
}

// ---------- Tests ----------

describe("HighlightItem scroll behaviour", () => {
  beforeEach(() => {
    mockScrollIntoView.mockClear();
  });

  it("calls scrollIntoView when clicking a PDF token annotation", () => {
    renderHighlightItem(makeTokenAnnotation(2));
    fireEvent.click(screen.getByTestId("highlight-item"));
    expect(mockScrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });
  });

  it("does NOT call scrollIntoView when clicking a text span annotation", () => {
    renderHighlightItem(makeSpanAnnotation(0));
    fireEvent.click(screen.getByTestId("highlight-item"));
    expect(mockScrollIntoView).not.toHaveBeenCalled();
  });
});

describe("HighlightItem page label display", () => {
  it("shows page label when annotation.page > 0", () => {
    const { getByText } = renderHighlightItem(makeTokenAnnotation(2));
    expect(getByText("Page 3")).toBeTruthy();
  });

  it("shows page label for page-0 token annotation (Page 1)", () => {
    const { getByText } = renderHighlightItem(makeTokenAnnotation(0));
    expect(getByText("Page 1")).toBeTruthy();
  });

  it("shows page label for span annotation when page > 0", () => {
    const { getByText } = renderHighlightItem(makeSpanAnnotation(5));
    expect(getByText("Page 6")).toBeTruthy();
  });

  it("hides page label for span annotation when page is 0", () => {
    const { queryByText } = renderHighlightItem(makeSpanAnnotation(0));
    expect(queryByText(/^Page/)).toBeNull();
  });
});
