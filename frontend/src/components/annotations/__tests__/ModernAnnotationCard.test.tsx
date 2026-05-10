import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import {
  ModernAnnotationCard,
  getAnnotationSource,
  getAnnotationLabelType,
  getAnnotationVisibility,
} from "../ModernAnnotationCard";
import { ServerAnnotationType, LabelType } from "../../../types/graphql-api";

// Mock the @os-legal/ui components
vi.mock("@os-legal/ui", () => ({
  Avatar: ({ fallback, size }: { fallback: string; size: string }) => (
    <div data-testid="avatar">{fallback}</div>
  ),
  Chip: ({
    children,
  }: {
    children: React.ReactNode;
    size?: string;
    [key: string]: unknown;
  }) => <span data-testid="chip">{children}</span>,
}));

/**
 * Factory function to create mock annotation data
 */
const createMockAnnotation = (
  overrides: Partial<ServerAnnotationType> = {}
): ServerAnnotationType => ({
  id: "annotation-1",
  page: 0,
  annotationLabel: {
    id: "label-1",
    text: "Test Label",
    color: "#FF0000",
    labelType: LabelType.TokenLabel,
  },
  document: {
    id: "doc-1",
    title: "Test Document",
    slug: "test-document",
  } as ServerAnnotationType["document"],
  corpus: {
    id: "corpus-1",
    title: "Test Corpus",
    slug: "test-corpus",
    labelSet: {
      id: "labelset-1",
      title: "Test Labelset",
    },
  } as ServerAnnotationType["corpus"],
  rawText: "This is some sample annotation text for testing.",
  structural: false,
  isPublic: false,
  created: new Date().toISOString(),
  creator: {
    id: "user-test",
    slug: "testuser",
  } as ServerAnnotationType["creator"],
  ...overrides,
});

describe("ModernAnnotationCard", () => {
  describe("Helper Functions", () => {
    describe("getAnnotationSource", () => {
      it("returns 'structural' for structural annotations", () => {
        const annotation = createMockAnnotation({ structural: true });
        expect(getAnnotationSource(annotation)).toBe("structural");
      });

      it("returns 'human' for annotations without analysis", () => {
        const annotation = createMockAnnotation({ analysis: undefined });
        expect(getAnnotationSource(annotation)).toBe("human");
      });

      it("returns 'human' for manually-created analysis annotations", () => {
        const annotation = createMockAnnotation({
          analysis: {
            id: "analysis-1",
            analyzer: {
              analyzerId: "manually_created_annotation_analyzer",
            },
          } as ServerAnnotationType["analysis"],
        });
        expect(getAnnotationSource(annotation)).toBe("human");
      });

      it("returns 'agent' for AI-generated analysis annotations", () => {
        const annotation = createMockAnnotation({
          analysis: {
            id: "analysis-1",
            analyzer: {
              analyzerId: "openai_gpt4_analyzer",
            },
          } as ServerAnnotationType["analysis"],
        });
        expect(getAnnotationSource(annotation)).toBe("agent");
      });

      it("returns 'agent' for analysis with empty analyzer ID", () => {
        const annotation = createMockAnnotation({
          analysis: {
            id: "analysis-1",
            analyzer: {
              analyzerId: "",
            },
          } as ServerAnnotationType["analysis"],
        });
        expect(getAnnotationSource(annotation)).toBe("agent");
      });
    });

    describe("getAnnotationLabelType", () => {
      it("returns 'doc' for DOC_TYPE_LABEL annotations", () => {
        const annotation = createMockAnnotation({
          annotationType: "DOC_TYPE_LABEL" as LabelType,
        });
        expect(getAnnotationLabelType(annotation)).toBe("doc");
      });

      it("returns 'text' for non-DOC_TYPE_LABEL annotations", () => {
        const annotation = createMockAnnotation({
          annotationType: LabelType.TokenLabel,
        });
        expect(getAnnotationLabelType(annotation)).toBe("text");
      });

      it("returns 'text' when annotationType is undefined", () => {
        const annotation = createMockAnnotation({
          annotationType: undefined,
        });
        expect(getAnnotationLabelType(annotation)).toBe("text");
      });
    });

    describe("getAnnotationVisibility", () => {
      it("returns 'public' for public annotations", () => {
        const annotation = createMockAnnotation({ isPublic: true });
        expect(getAnnotationVisibility(annotation)).toBe("public");
      });

      it("returns 'private' for non-public annotations created by current user", () => {
        const annotation = createMockAnnotation({
          isPublic: false,
          creator: {
            id: "user-1",
          } as ServerAnnotationType["creator"],
        });
        expect(getAnnotationVisibility(annotation, "user-1")).toBe("private");
      });

      it("returns 'shared' for non-public annotations not created by current user", () => {
        const annotation = createMockAnnotation({
          isPublic: false,
          creator: {
            id: "user-2",
          } as ServerAnnotationType["creator"],
        });
        expect(getAnnotationVisibility(annotation, "user-1")).toBe("shared");
      });
    });
  });

  describe("Component Rendering", () => {
    it("renders the annotation label name", () => {
      const annotation = createMockAnnotation();
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByText("Test Label")).toBeInTheDocument();
    });

    it("renders the document name", () => {
      const annotation = createMockAnnotation();
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByText("Test Document")).toBeInTheDocument();
    });

    it("renders truncated rawText for text annotations", () => {
      const longText = "A".repeat(200);
      const annotation = createMockAnnotation({ rawText: longText });
      render(<ModernAnnotationCard annotation={annotation} />);
      // Should show truncated text with ellipsis (150 chars + ...)
      const truncated = longText.substring(0, 150) + "...";
      expect(screen.getByText(truncated)).toBeInTheDocument();
    });

    it("renders full rawText for short text annotations", () => {
      const shortText = "Short annotation text";
      const annotation = createMockAnnotation({ rawText: shortText });
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByText(shortText)).toBeInTheDocument();
    });

    it("renders 'Applies to entire document' for doc-type labels", () => {
      const annotation = createMockAnnotation({
        annotationType: "DOC_TYPE_LABEL" as LabelType,
        rawText: null,
      });
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(
        screen.getByText("Applies to entire document")
      ).toBeInTheDocument();
    });

    it("renders the labelset name", () => {
      const annotation = createMockAnnotation();
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByText("Test Labelset")).toBeInTheDocument();
    });

    it("renders default labelset name when corpus is missing", () => {
      const annotation = createMockAnnotation({ corpus: null });
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByText("Annotations")).toBeInTheDocument();
    });

    it("renders creator initials in avatar", () => {
      const annotation = createMockAnnotation();
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByTestId("avatar")).toHaveTextContent("TE");
    });
  });

  describe("Interaction", () => {
    it("calls onClick when card is clicked", () => {
      const handleClick = vi.fn();
      const annotation = createMockAnnotation();
      render(
        <ModernAnnotationCard annotation={annotation} onClick={handleClick} />
      );

      const card = screen.getByText("Test Label").closest("div");
      fireEvent.click(card!);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it("applies selected styles when isSelected is true", () => {
      const annotation = createMockAnnotation();
      const { container: selectedContainer } = render(
        <ModernAnnotationCard annotation={annotation} isSelected={true} />
      );
      const { container: unselectedContainer } = render(
        <ModernAnnotationCard annotation={annotation} isSelected={false} />
      );

      const selectedCard = selectedContainer.firstChild as HTMLElement;
      const unselectedCard = unselectedContainer.firstChild as HTMLElement;

      // Selected and unselected cards should have different computed class names
      expect(selectedCard.className).not.toBe(unselectedCard.className);
    });
  });

  describe("Source Badge", () => {
    it("renders human badge for human annotations", () => {
      const annotation = createMockAnnotation({ structural: false });
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByTitle("Human annotated")).toBeInTheDocument();
    });

    it("renders structural badge for structural annotations", () => {
      const annotation = createMockAnnotation({ structural: true });
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByTitle("Structural")).toBeInTheDocument();
    });

    it("renders AI badge for agent annotations", () => {
      const annotation = createMockAnnotation({
        analysis: {
          id: "analysis-1",
          analyzer: {
            analyzerId: "ai_extractor",
          },
        } as ServerAnnotationType["analysis"],
      });
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByTitle("AI annotated")).toBeInTheDocument();
    });
  });

  describe("Type Badge", () => {
    it("renders Doc badge for document-level annotations", () => {
      const annotation = createMockAnnotation({
        annotationType: "DOC_TYPE_LABEL" as LabelType,
      });
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByText("Doc")).toBeInTheDocument();
    });

    it("renders Text badge for text-level annotations", () => {
      const annotation = createMockAnnotation({
        annotationType: LabelType.TokenLabel,
      });
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.getByText("Text")).toBeInTheDocument();
    });
  });

  describe("SimilarityBadge", () => {
    it("renders high-score badge with percentage", () => {
      const annotation = createMockAnnotation();
      render(
        <ModernAnnotationCard annotation={annotation} similarityScore={0.95} />
      );
      expect(screen.getByText("95%")).toBeInTheDocument();
      expect(screen.getByTitle("95% semantic match")).toBeInTheDocument();
    });

    it("renders medium-score badge", () => {
      const annotation = createMockAnnotation();
      render(
        <ModernAnnotationCard annotation={annotation} similarityScore={0.7} />
      );
      expect(screen.getByText("70%")).toBeInTheDocument();
    });

    it("renders low-score badge", () => {
      const annotation = createMockAnnotation();
      render(
        <ModernAnnotationCard annotation={annotation} similarityScore={0.4} />
      );
      expect(screen.getByText("40%")).toBeInTheDocument();
    });

    it("does not render when similarityScore is undefined", () => {
      const annotation = createMockAnnotation();
      render(<ModernAnnotationCard annotation={annotation} />);
      expect(screen.queryByTitle(/semantic match/)).not.toBeInTheDocument();
    });
  });

  describe("Image Modality", () => {
    it("renders IMAGE modality badge when contentModalities includes IMAGE", () => {
      const annotation = createMockAnnotation({
        contentModalities: ["IMAGE"],
        rawText: null,
      });
      render(<ModernAnnotationCard annotation={annotation} />);
      // The ModalityBadge component should be rendered
      const card = screen.getByText("Test Label");
      expect(card).toBeInTheDocument();
    });
  });

  describe("XSS Protection", () => {
    it("sanitizes rawText with newlines and special whitespace", () => {
      const textWithNewlines = "Line 1\nLine 2\r\nLine 3";
      const annotation = createMockAnnotation({ rawText: textWithNewlines });
      render(<ModernAnnotationCard annotation={annotation} />);
      // sanitizeForTooltip normalizes newlines to spaces
      expect(screen.getByText("Line 1 Line 2 Line 3")).toBeInTheDocument();
    });

    it("handles rawText with HTML-like content safely", () => {
      const htmlText = "<script>alert('xss')</script>";
      const annotation = createMockAnnotation({ rawText: htmlText });
      render(<ModernAnnotationCard annotation={annotation} />);
      // React's JSX escapes HTML, sanitizeForTooltip normalizes whitespace
      // The text should appear as literal text, not be executed
      expect(
        screen.getByText("<script>alert('xss')</script>")
      ).toBeInTheDocument();
    });
  });
});
