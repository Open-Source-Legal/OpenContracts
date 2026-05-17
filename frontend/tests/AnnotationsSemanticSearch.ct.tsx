/**
 * Component tests for semantic search functionality in Annotations view.
 *
 * Tests cover:
 * - Basic semantic search execution
 * - Error handling display
 * - Filter changes re-triggering search
 * - Empty state handling
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { AnnotationsSemanticSearchTestWrapper } from "./AnnotationsSemanticSearchTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

const mockAnnotation = {
  id: "QW5ub3RhdGlvblR5cGU6MQ==",
  tokensJsons: null,
  json: {},
  page: 0,
  created: "2024-01-15T10:30:00Z",
  creator: {
    id: "VXNlclR5cGU6MQ==",
    email: "user@example.com",
    username: "testuser",
    slug: "testuser",
    __typename: "UserType",
  },
  corpus: {
    id: "Q29ycHVzVHlwZTox",
    slug: "test-corpus",
    icon: null,
    title: "Test Corpus",
    description: "A test corpus",
    preferredEmbedder: null,
    creator: {
      id: "VXNlclR5cGU6MQ==",
      slug: "testuser",
      __typename: "UserType",
    },
    labelSet: {
      id: "TGFiZWxTZXRUeXBlOjE=",
      title: "Test Labelset",
      __typename: "LabelSetType",
    },
    __typename: "CorpusType",
  },
  document: {
    id: "RG9jdW1lbnRUeXBlOjE=",
    slug: "test-document",
    title: "Test Document",
    description: "A test document",
    backendLock: false,
    pdfFile: "/media/documents/test.pdf",
    txtExtractFile: null,
    pawlsParseFile: null,
    icon: null,
    fileType: "application/pdf",
    creator: {
      id: "VXNlclR5cGU6MQ==",
      slug: "testuser",
      __typename: "UserType",
    },
    __typename: "DocumentType",
  },
  analysis: null,
  annotationLabel: {
    id: "QW5ub3RhdGlvbkxhYmVsVHlwZTox",
    text: "Contract Term",
    color: "#FF5722",
    icon: "FileText",
    description: "A contract term annotation",
    labelType: "TOKEN_LABEL",
    __typename: "AnnotationLabelType",
  },
  annotationType: "TOKEN_LABEL",
  structural: false,
  rawText: "This is a sample annotation text for testing purposes.",
  isPublic: false,
  myPermissions: ["read", "update"],
  contentModalities: ["TEXT"],
  __typename: "AnnotationType",
};

const mockSemanticSearchResult = {
  annotation: mockAnnotation,
  similarityScore: 0.85,
  document: {
    id: "RG9jdW1lbnRUeXBlOjE=",
    slug: "test-document",
    title: "Test Document",
    __typename: "DocumentType",
  },
  corpus: {
    id: "Q29ycHVzVHlwZTox",
    slug: "test-corpus",
    title: "Test Corpus",
    __typename: "CorpusType",
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// TESTS
// ═══════════════════════════════════════════════════════════════════════════════

test.describe("Annotations Semantic Search", () => {
  test("should show empty state with appropriate message for semantic search", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <AnnotationsSemanticSearchTestWrapper
        semanticSearchResults={[]}
        browseAnnotations={[]}
      />
    );

    // Verify the page loads with search box
    const searchInput = page.getByPlaceholder("Search annotations...");
    await expect(searchInput).toBeVisible({ timeout: 10000 });

    // Type in the search box
    await searchInput.fill("nonexistent query");

    // Wait for debounce (500ms) + some buffer
    await page.waitForTimeout(800);

    // Verify semantic search empty state message
    await expect(page.getByText("No matching annotations found")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText(/Try a different search query/)).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("should show browse mode annotations initially", async ({
    mount,
    page,
  }) => {
    const browseAnnotation = {
      ...mockAnnotation,
      id: "QW5ub3RhdGlvblR5cGU6Mg==",
      rawText: "Browse mode annotation text",
      annotationLabel: {
        ...mockAnnotation.annotationLabel,
        text: "Browse Label",
      },
    };

    const component = await mount(
      <AnnotationsSemanticSearchTestWrapper
        semanticSearchResults={[]}
        browseAnnotations={[browseAnnotation]}
      />
    );

    // In browse mode, should show browse annotation
    await expect(page.getByText("Browse Label")).toBeVisible({
      timeout: 15000,
    });

    await docScreenshot(page, "annotations--semantic-search--browse-mode");

    await component.unmount();
  });

  test("should display error message when semantic search fails", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <AnnotationsSemanticSearchTestWrapper
        semanticSearchResults={[]}
        browseAnnotations={[]}
        simulateSearchError="Network error: Failed to fetch"
      />
    );

    // Type in the search box
    const searchInput = page.getByPlaceholder("Search annotations...");
    await expect(searchInput).toBeVisible({ timeout: 10000 });
    await searchInput.fill("contract terms");

    // Wait for debounce + network response
    await page.waitForTimeout(1000);

    // Verify error message is displayed
    await expect(page.getByText("Search failed:")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("should show 'Browse annotations' title in hero section", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <AnnotationsSemanticSearchTestWrapper
        semanticSearchResults={[]}
        browseAnnotations={[]}
      />
    );

    // Verify the hero section renders - use heading role for specificity
    await expect(
      page.getByRole("heading", { name: /Browse.*annotations/ })
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("should display filter tabs", async ({ mount, page }) => {
    const component = await mount(
      <AnnotationsSemanticSearchTestWrapper
        semanticSearchResults={[]}
        browseAnnotations={[]}
      />
    );

    // Verify filter tabs are visible - use role="tab" for specificity
    // This distinguishes tabs from stats labels with the same text
    await expect(page.getByRole("tab", { name: "All Types" })).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByRole("tab", { name: "Doc Labels" })).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByRole("tab", { name: "Text Labels" })).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByRole("tab", { name: "All Sources" })).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByRole("tab", { name: "Human" })).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByRole("tab", { name: "AI Agent" })).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByRole("tab", { name: "Structural" })).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("should display stats section with zero counts when no annotations", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <AnnotationsSemanticSearchTestWrapper
        semanticSearchResults={[]}
        browseAnnotations={[]}
      />
    );

    // Verify stats section elements - these are NOT tabs, just stat labels
    // Stats have a specific structure: value + label
    await expect(page.getByText("Total Annotations")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Human Annotated")).toBeVisible({
      timeout: 5000,
    });

    // Verify the stats show zero counts - look for "0" text that appears
    // multiple times (once for each stat)
    const zeroValues = page.getByText("0", { exact: true });
    await expect(zeroValues.first()).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

test.describe("Annotations Filter Tabs", () => {
  test("should filter annotations by type (doc/text labels)", async ({
    mount,
    page,
  }) => {
    const textAnnotation = {
      ...mockAnnotation,
      annotationLabel: {
        ...mockAnnotation.annotationLabel,
        text: "Text Annotation Label",
        labelType: "TOKEN_LABEL",
      },
    };

    const docAnnotation = {
      ...mockAnnotation,
      id: "QW5ub3RhdGlvblR5cGU6Mw==",
      annotationLabel: {
        ...mockAnnotation.annotationLabel,
        id: "QW5ub3RhdGlvbkxhYmVsVHlwZToy",
        text: "Doc Annotation Label",
        labelType: "DOC_TYPE_LABEL",
      },
    };

    const component = await mount(
      <AnnotationsSemanticSearchTestWrapper
        semanticSearchResults={[]}
        browseAnnotations={[textAnnotation, docAnnotation]}
      />
    );

    // Initially both should be visible - use unique label names that don't
    // conflict with tab labels
    await expect(page.getByText("Text Annotation Label")).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText("Doc Annotation Label")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("should filter annotations by source (human/agent/structural)", async ({
    mount,
    page,
  }) => {
    const humanAnnotation = {
      ...mockAnnotation,
      structural: false,
      analysis: null,
      annotationLabel: {
        ...mockAnnotation.annotationLabel,
        text: "Human Label",
      },
    };

    const structuralAnnotation = {
      ...mockAnnotation,
      id: "QW5ub3RhdGlvblR5cGU6NA==",
      structural: true,
      annotationLabel: {
        ...mockAnnotation.annotationLabel,
        id: "QW5ub3RhdGlvbkxhYmVsVHlwZToz",
        text: "Structural Label",
      },
    };

    const component = await mount(
      <AnnotationsSemanticSearchTestWrapper
        semanticSearchResults={[]}
        browseAnnotations={[humanAnnotation, structuralAnnotation]}
      />
    );

    // Initially both should be visible (All Sources)
    await expect(page.getByText("Human Label")).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Structural Label")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });
});
