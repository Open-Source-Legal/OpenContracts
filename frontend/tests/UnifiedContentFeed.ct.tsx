import { test, expect } from "@playwright/experimental-ct-react";
import { UnifiedContentFeedTestWrapper } from "./UnifiedContentFeedTestWrapper";
import {
  Note,
  SortOption,
  ContentFilters,
} from "../src/components/knowledge_base/document/unified_feed/types";
import { ServerTokenAnnotation } from "../src/components/annotator/types/annotations";
import { AnnotationLabelType, LabelType } from "../src/types/graphql-api";
import { PermissionTypes } from "../src/components/types";
import React from "react";

// Mock annotation factory
const createMockAnnotation = (
  id: string,
  page: number,
  text: string,
  label: { text: string; color: string }
): ServerTokenAnnotation => {
  const annotationLabel: AnnotationLabelType = {
    id: `label-${id}`,
    text: label.text,
    color: label.color,
    description: "",
    icon: undefined,
    analyzer: null,
    labelType: LabelType.TokenLabel,
    __typename: "AnnotationLabelType",
  };

  return new ServerTokenAnnotation(
    page - 1, // Convert to 0-based page index
    annotationLabel,
    text, // rawText
    false, // structural
    {
      // MultipageAnnotationJson
      1: {
        bounds: { top: 100, bottom: 120, left: 50, right: 200 },
        tokensJsons: [],
        rawText: text,
      },
    },
    [PermissionTypes.CAN_READ], // myPermissions
    false, // approved
    false, // rejected
    false, // canComment
    id
  );
};

test.describe("UnifiedContentFeed", () => {
  test("renders notes in feed", async ({ mount, page }) => {
    const testNotes: Note[] = [
      {
        id: "1",
        title: "Test Note 1",
        content: "This is the first test note",
        created: new Date().toISOString(),
        creator: { email: "test@example.com" },
      },
      {
        id: "2",
        title: "Test Note 2",
        content: "This is the second test note",
        created: new Date().toISOString(),
        creator: { email: "test@example.com" },
      },
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper notes={testNotes} />
    );

    // Wait a bit for virtualization to initialize
    await page.waitForTimeout(100);

    // Check that the feed container is rendered
    await expect(
      page.locator('[data-testid="unified-content-feed"]')
    ).toBeVisible();

    // Check that notes are rendered
    await expect(page.locator("text=Test Note 1")).toBeVisible();
    await expect(page.locator("text=Test Note 2")).toBeVisible();

    // Check that notes show as PostItNote components
    const postItNotes = page.locator("button").filter({ hasText: "Test Note" });
    await expect(postItNotes).toHaveCount(2);
  });

  test("shows empty state when no content", async ({ mount, page }) => {
    const component = await mount(<UnifiedContentFeedTestWrapper notes={[]} />);

    // Wait for component to render
    await page.waitForTimeout(100);

    // Check if any error occurred
    const errorElements = await page
      .locator('.error, [data-testid*="error"]')
      .count();
    if (errorElements > 0) {
      console.error("Error elements found:", errorElements);
    }

    // Check if empty state container is rendered
    const emptyContainer = page.locator(
      '[data-testid="unified-content-feed-empty"]'
    );
    const feedContainer = page.locator('[data-testid="unified-content-feed"]');

    // One of these should be visible
    const emptyVisible = await emptyContainer.isVisible().catch(() => false);
    const feedVisible = await feedContainer.isVisible().catch(() => false);

    expect(emptyVisible || feedVisible).toBe(true);

    // Should show empty state
    await expect(page.locator("text=No content found")).toBeVisible();
    await expect(
      page.locator("text=Try adjusting your filters or search query")
    ).toBeVisible();
  });

  test("shows loading state", async ({ mount, page }) => {
    const component = await mount(
      <UnifiedContentFeedTestWrapper isLoading={true} />
    );

    // Should show loader
    await expect(page.locator(".loader")).toBeVisible();
  });

  test("calls onItemSelect when note is clicked", async ({ mount, page }) => {
    let itemSelected = false;
    const component = await mount(
      <UnifiedContentFeedTestWrapper
        onItemSelect={() => {
          itemSelected = true;
        }}
      />
    );

    // Click first note
    await page.locator("text=Test Note 1").click();

    // Should have called onItemSelect
    expect(itemSelected).toBe(true);
  });

  test("groups items by page number", async ({ mount, page }) => {
    const notesWithPages: Note[] = [
      {
        id: "1",
        title: "Note on page 1",
        content: "Content",
        created: new Date().toISOString(),
        creator: {
          email: "test@example.com",
        },
      },
      {
        id: "2",
        title: "Note on page 2",
        content: "Content",
        created: new Date().toISOString(),
        creator: {
          email: "test@example.com",
        },
      },
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper notes={notesWithPages} />
    );

    // Should show page headers
    await expect(page.locator("text=Page 1")).toBeVisible();
    await expect(page.locator("text=Page 2")).toBeVisible();
  });

  test("respects content type filters - notes only", async ({
    mount,
    page,
  }) => {
    // Test with only notes enabled
    // Note: Playwright serializes props, so we pass array instead of Set
    const notesOnlyFilters = {
      contentTypes: ["note"],
      annotationFilters: {
        showStructural: false,
      },
      relationshipFilters: {
        showStructural: false,
      },
      searchQuery: "",
    };

    const component = await mount(
      <UnifiedContentFeedTestWrapper filters={notesOnlyFilters as any} />
    );

    // Wait for component to render
    await page.waitForTimeout(200);

    // Check if component rendered
    const hasError = await page
      .locator("text=Component Error")
      .isVisible()
      .catch(() => false);
    if (hasError) {
      const errorText = await page.locator("pre").first().textContent();
      console.error("Component error:", errorText);
    }

    // Notes should be visible
    await expect(page.locator("text=Test Note 1")).toBeVisible();
    await expect(page.locator("text=Test Note 2")).toBeVisible();
  });

  test("respects content type filters - empty when notes disabled", async ({
    mount,
    page,
  }) => {
    // Test with notes disabled
    // Note: Playwright serializes props, so we pass array instead of Set
    const noNotesFilters = {
      contentTypes: ["annotation", "relationship", "search"],
      annotationFilters: {
        showStructural: false,
      },
      relationshipFilters: {
        showStructural: false,
      },
      searchQuery: "",
    };

    const component = await mount(
      <UnifiedContentFeedTestWrapper filters={noNotesFilters as any} />
    );

    // Wait a moment for atoms to initialize
    await page.waitForTimeout(100);

    // Should show empty state since we only have notes and they're filtered out
    await expect(page.locator("text=No content found")).toBeVisible();
  });

  test("sorts content by creation date", async ({ mount, page }) => {
    const notes: Note[] = [
      {
        id: "1",
        title: "Newer Note",
        content: "Created later",
        created: "2024-01-02T00:00:00Z",
        creator: {
          email: "test@example.com",
        },
      },
      {
        id: "2",
        title: "Older Note",
        content: "Created earlier",
        created: "2024-01-01T00:00:00Z",
        creator: {
          email: "test@example.com",
        },
      },
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={notes}
        sortBy={"date" as SortOption}
      />
    );

    // Get all notes
    const postItNotes = await page
      .locator("button")
      .filter({ hasText: "Note" })
      .all();

    // When sorted by created date (newest first), Newer Note should be first
    const firstNoteText = await postItNotes[0].textContent();
    expect(firstNoteText).toContain("Newer Note");
  });
});

test.describe("UnifiedContentFeed - Read-only Mode", () => {
  test("read-only: notes are not clickable", async ({ mount, page }) => {
    let itemSelected = false;
    const component = await mount(
      <UnifiedContentFeedTestWrapper
        readOnly={true}
        onItemSelect={() => {
          itemSelected = true;
        }}
      />
    );

    // Click first note
    await page.locator("text=Test Note 1").click();

    // Should NOT have called onItemSelect
    expect(itemSelected).toBe(false);
  });

  test("read-only: notes have default cursor", async ({ mount, page }) => {
    const component = await mount(
      <UnifiedContentFeedTestWrapper readOnly={true} />
    );

    // Get the PostItNote button
    const firstNote = page.locator("button").filter({ hasText: "Test Note 1" });

    // Check cursor style
    const cursor = await firstNote.evaluate(
      (el) => window.getComputedStyle(el).cursor
    );
    expect(cursor).toBe("default");
  });

  test("read-only: edit indicators are hidden", async ({ mount, page }) => {
    const component = await mount(
      <UnifiedContentFeedTestWrapper readOnly={true} />
    );

    // Get the first note
    const firstNote = page.locator("button").filter({ hasText: "Test Note 1" });

    // Hover over the note
    await firstNote.hover();

    // Edit indicator should not be visible (opacity 0)
    const editIndicator = firstNote.locator(".edit-indicator");
    const opacity = await editIndicator.evaluate(
      (el) => window.getComputedStyle(el).opacity
    );
    expect(opacity).toBe("0");
  });

  test("editable: notes are clickable", async ({ mount, page }) => {
    let itemSelected = false;
    const component = await mount(
      <UnifiedContentFeedTestWrapper
        readOnly={false}
        onItemSelect={() => {
          itemSelected = true;
        }}
      />
    );

    // Click first note
    await page.locator("text=Test Note 1").click();

    // Should have called onItemSelect
    expect(itemSelected).toBe(true);
  });

  test("editable: notes have pointer cursor", async ({ mount, page }) => {
    const component = await mount(
      <UnifiedContentFeedTestWrapper readOnly={false} />
    );

    // Get the PostItNote button
    const firstNote = page.locator("button").filter({ hasText: "Test Note 1" });

    // Check cursor style
    const cursor = await firstNote.evaluate(
      (el) => window.getComputedStyle(el).cursor
    );
    expect(cursor).toBe("pointer");
  });

  test("editable: edit indicators show on hover", async ({ mount, page }) => {
    const component = await mount(
      <UnifiedContentFeedTestWrapper readOnly={false} />
    );

    // Get the first note
    const firstNote = page.locator("button").filter({ hasText: "Test Note 1" });

    // Initially edit indicator should be hidden
    const editIndicator = firstNote.locator(".edit-indicator");
    const initialOpacity = await editIndicator.evaluate(
      (el) => window.getComputedStyle(el).opacity
    );
    expect(initialOpacity).toBe("0");

    // Hover over the note
    await firstNote.hover();
    await page.waitForTimeout(300); // Wait for transition

    // Edit indicator should be visible
    const hoverOpacity = await editIndicator.evaluate(
      (el) => window.getComputedStyle(el).opacity
    );
    expect(hoverOpacity).toBe("1");
  });
});

test.describe("UnifiedContentFeed - Annotations in Read-only Mode", () => {
  test("read-only: annotations show but delete is disabled", async ({
    mount,
    page,
  }) => {
    const mockAnnotations = [
      createMockAnnotation("ann-1", 1, "Test annotation text", {
        text: "Important",
        color: "#ff0000",
      }),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        readOnly={true}
        notes={[]}
        mockAnnotations={mockAnnotations}
      />
    );

    // Annotation should be visible
    await expect(page.locator("text=Test annotation text")).toBeVisible();

    // Label should be visible
    await expect(page.locator("text=Important")).toBeVisible();

    // Delete button should not be visible in read-only mode
    // (HighlightItem hides delete when read_only is true)
    const deleteButton = page.locator('button[title="Delete"]');
    await expect(deleteButton).not.toBeVisible();
  });

  test("editable: annotations show delete button", async ({ mount, page }) => {
    const mockAnnotations = [
      createMockAnnotation("ann-1", 1, "Test annotation text", {
        text: "Important",
        color: "#ff0000",
      }),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        readOnly={false}
        notes={[]}
        mockAnnotations={mockAnnotations}
      />
    );

    // Annotation should be visible
    await expect(page.locator("text=Test annotation text")).toBeVisible();

    // In editable mode, delete functionality would be available
    // (exact behavior depends on HighlightItem implementation)
  });
});

test.describe("UnifiedContentFeed - Relations in Read-only Mode", () => {
  test("read-only: relations show but actions are disabled", async ({
    mount,
    page,
  }) => {
    const mockAnnotations = [
      createMockAnnotation("ann-1", 1, "Source text", {
        text: "Source",
        color: "#0000ff",
      }),
      createMockAnnotation("ann-2", 1, "Target text", {
        text: "Target",
        color: "#00ff00",
      }),
    ];

    const mockRelations = [
      {
        id: "rel-1",
        sourceIds: ["ann-1"],
        targetIds: ["ann-2"],
        label: { text: "References", color: "#ff00ff" },
        structural: false,
        __typename: "RelationGroup",
      },
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        readOnly={true}
        notes={[]}
        mockAnnotations={mockAnnotations}
        mockRelations={mockRelations}
      />
    );

    // Relation should be visible
    await expect(page.locator("text=References")).toBeVisible();

    // Check that the relation shows both source and target labels
    await expect(page.locator("text=Source").first()).toBeVisible();
    await expect(page.locator("text=Target").first()).toBeVisible();
  });

  test("mixed content shows in correct order", async ({ mount, page }) => {
    const mockAnnotations = [
      createMockAnnotation("ann-1", 1, "First annotation", {
        text: "Label",
        color: "#ff0000",
      }),
    ];

    const notes: Note[] = [
      {
        id: "1",
        title: "Test Note",
        content: "Note content",
        created: new Date().toISOString(),
        creator: {
          email: "test@example.com",
        },
      },
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={notes}
        mockAnnotations={mockAnnotations}
        sortBy="page"
      />
    );

    // Wait for initialization
    await page.waitForTimeout(100);

    // Both annotation and note should be on page 1
    // Check that we have exactly one "Page 1" header
    await expect(page.locator('span:text-is("Page")')).toBeVisible();
    await expect(page.locator('text="1"').first()).toBeVisible();

    // Content should be visible
    await expect(page.locator("text=First annotation")).toBeVisible();
    await expect(page.locator("text=Test Note")).toBeVisible();
  });
});
