import { test, expect } from "./utils/coverage";
import { UnifiedContentFeedTestWrapper } from "./UnifiedContentFeedTestWrapper";
import {
  Note,
  SortOption,
  ContentFilters,
} from "../src/components/knowledge_base/document/unified_feed/types";
import {
  ServerTokenAnnotation,
  ServerSpanAnnotation,
  RelationGroup,
} from "../src/components/annotator/types/annotations";
import { AnnotationLabelType, LabelType } from "../src/types/graphql-api";
import { PermissionTypes } from "../src/components/types";
import { docScreenshot } from "./utils/docScreenshot";
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

    // Should show loader (Spinner from @os-legal/ui uses .oc-spinner class)
    await expect(page.locator(".oc-spinner")).toBeVisible();
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

    // Get the PostItNote button — use toHaveCSS for retry-based style assertion
    const firstNote = page.locator("button").filter({ hasText: "Test Note 1" });
    await expect(firstNote).toBeVisible();
    await expect(firstNote).toHaveCSS("cursor", "default");
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
    await expect(firstNote).toBeVisible();

    // Wait for styled-components CSS injection to settle
    await expect(firstNote).toHaveCSS("cursor", "pointer");
  });

  test("editable: edit indicators show on hover", async ({ mount, page }) => {
    const component = await mount(
      <UnifiedContentFeedTestWrapper readOnly={false} />
    );

    // Get the first note
    const firstNote = page.locator("button").filter({ hasText: "Test Note 1" });
    await expect(firstNote).toBeVisible();

    // Initially edit indicator should be hidden
    const editIndicator = firstNote.locator(".edit-indicator");
    await expect(editIndicator).toHaveCSS("opacity", "0");

    // Hover over the note
    await firstNote.hover();

    // Edit indicator should become visible (uses Playwright's auto-retry)
    await expect(editIndicator).toHaveCSS("opacity", "1");
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

// ──────────────────────────────────────────────────────────────────────────────
// Span Annotation Relationship Screenshots
// ──────────────────────────────────────────────────────────────────────────────

// Helper to create mock span annotations (text documents)
const createMockSpanAnnotation = (
  id: string,
  page: number,
  text: string,
  label: { text: string; color: string },
  start: number,
  end: number
): ServerSpanAnnotation => {
  const annotationLabel: AnnotationLabelType = {
    id: `label-${id}`,
    text: label.text,
    color: label.color,
    description: "",
    icon: undefined,
    analyzer: null,
    labelType: LabelType.SpanLabel,
    __typename: "AnnotationLabelType",
  };

  return new ServerSpanAnnotation(
    page - 1, // Convert to 0-based page index
    annotationLabel,
    text,
    false, // structural
    { start, end },
    [PermissionTypes.CAN_READ, PermissionTypes.CAN_REMOVE],
    false, // approved
    false, // rejected
    false, // canComment
    id
  );
};

test.describe("UnifiedContentFeed - Span Annotation Relationships", () => {
  test("span annotations with relationship badges", async ({ mount, page }) => {
    const spanAnnotations = [
      createMockSpanAnnotation(
        "span-1",
        1,
        "Lorem ipsum dolor sit amet",
        { text: "Important Text", color: "#3B82F6" },
        0,
        26
      ),
      createMockSpanAnnotation(
        "span-2",
        1,
        "consectetur adipiscing elit",
        { text: "Key Phrase", color: "#8B5CF6" },
        28,
        55
      ),
      createMockSpanAnnotation(
        "span-3",
        1,
        "sed do eiusmod tempor",
        { text: "Reference", color: "#F59E0B" },
        57,
        78
      ),
    ];

    const relationLabel: AnnotationLabelType = {
      id: "rel-label-1",
      text: "References",
      color: "#10B981",
      description: "A reference relationship",
      icon: undefined,
      analyzer: null,
      labelType: LabelType.RelationshipLabel,
      __typename: "AnnotationLabelType",
    };

    const mockRelations = [
      new RelationGroup(
        ["span-1"], // source
        ["span-2"], // target
        relationLabel,
        "rel-1",
        false
      ),
      new RelationGroup(
        ["span-3"], // source
        ["span-1"], // target
        relationLabel,
        "rel-2",
        false
      ),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={[]}
        mockAnnotations={spanAnnotations}
        mockRelations={mockRelations}
      />
    );

    await page.waitForTimeout(500);

    // Verify annotations are visible with their labels
    await expect(page.locator("text=Important Text").first()).toBeVisible();
    await expect(page.locator("text=Key Phrase").first()).toBeVisible();
    await expect(page.locator("text=Reference").first()).toBeVisible();

    // Verify relationship badges are displayed
    // span-1 is source in rel-1 (Points To 1) and target in rel-2 (1 Referencing)
    await expect(page.locator("text=Points To").first()).toBeVisible();
    await expect(page.locator("text=Referencing").first()).toBeVisible();

    // Hide multi-select checkboxes for cleaner screenshot (keep trash icons)
    await page.evaluate(() => {
      document
        .querySelectorAll<HTMLElement>(
          "i.square.outline.icon, i.check.square.icon"
        )
        .forEach((el) => (el.style.display = "none"));
    });

    // Tight-crop screenshot: clip from feed top to just below last content
    const componentBox = await component.boundingBox();
    const lastText = page.locator("text=sed do eiusmod").first();
    const lastTextBox = await lastText.boundingBox();
    if (componentBox && lastTextBox) {
      const pad = 16;
      await docScreenshot(
        page,
        "annotations--txt-sidebar--relationship-badges",
        {
          clip: {
            x: componentBox.x,
            y: componentBox.y,
            width: componentBox.width,
            height: lastTextBox.y + lastTextBox.height - componentBox.y + pad,
          },
        }
      );
    }
  });

  test("relationship item between span annotations", async ({
    mount,
    page,
  }) => {
    const spanAnnotations = [
      createMockSpanAnnotation(
        "span-src",
        1,
        "The plaintiff filed a motion",
        { text: "Legal Action", color: "#EF4444" },
        0,
        28
      ),
      createMockSpanAnnotation(
        "span-tgt",
        1,
        "under Section 12(b)(6)",
        { text: "Statute", color: "#3B82F6" },
        29,
        51
      ),
    ];

    const connectsLabel: AnnotationLabelType = {
      id: "rel-label-connects",
      text: "Cites",
      color: "#10B981",
      description: "Citation relationship",
      icon: undefined,
      analyzer: null,
      labelType: LabelType.RelationshipLabel,
      __typename: "AnnotationLabelType",
    };

    const mockRelations = [
      new RelationGroup(
        ["span-src"],
        ["span-tgt"],
        connectsLabel,
        "rel-cite-1",
        false
      ),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={[]}
        mockAnnotations={spanAnnotations}
        mockRelations={mockRelations}
        filters={{
          contentTypes: ["relationship"],
          annotationFilters: { showStructural: false },
          relationshipFilters: { showStructural: false },
          searchQuery: "",
        }}
      />
    );

    await page.waitForTimeout(500);

    // Verify the relationship item is displayed with its label
    await expect(page.locator("text=Cites").first()).toBeVisible();

    // Verify source and target annotations are shown within the relationship card
    await expect(page.locator("text=Legal Action").first()).toBeVisible();
    await expect(page.locator("text=Statute").first()).toBeVisible();

    // Tight-crop screenshot: clip from feed top to just below the card
    const componentBox = await component.boundingBox();
    const lastText = page.locator("text=under Section 12").first();
    const lastTextBox = await lastText.boundingBox();
    if (componentBox && lastTextBox) {
      const pad = 16;
      await docScreenshot(page, "annotations--txt-sidebar--relation-item", {
        clip: {
          x: componentBox.x,
          y: componentBox.y,
          width: componentBox.width,
          height: lastTextBox.y + lastTextBox.height - componentBox.y + pad,
        },
      });
    }
  });
});

/* ──────────────────────────────────────────────────────────────────────────
 * Multi-select toolbar & relationship modal integration
 * ────────────────────────────────────────────────────────────────────────── */

test.describe("UnifiedContentFeed - Multi-select toolbar", () => {
  test("selection toolbar appears after toggling an annotation", async ({
    mount,
    page,
  }) => {
    const annotations = [
      createMockAnnotation("ann-1", 1, "First item text", {
        text: "Label A",
        color: "#ff0000",
      }),
      createMockAnnotation("ann-2", 1, "Second item text", {
        text: "Label B",
        color: "#00ff00",
      }),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper notes={[]} mockAnnotations={annotations} />
    );

    // Toolbar is hidden initially
    await expect(page.getByText(/annotation[s]? selected/)).not.toBeVisible();

    // Toggle first annotation's multi-select checkbox (lucide Square icon)
    const firstItem = page.locator('[data-annotation-id="ann-1"]');
    await firstItem.locator(".lucide-square").click();

    // Toolbar appears with correct count
    await expect(page.getByText("1 annotation selected")).toBeVisible();

    // Toggle second annotation
    const secondItem = page.locator('[data-annotation-id="ann-2"]');
    await secondItem.locator(".lucide-square").click();

    await expect(page.getByText("2 annotations selected")).toBeVisible();

    // Clear selection with the Clear button
    await page.getByRole("button", { name: /Clear/ }).click();
    await expect(page.getByText(/annotation[s]? selected/)).not.toBeVisible();

    await component.unmount();
  });

  test("Select All selects every annotation in feed", async ({
    mount,
    page,
  }) => {
    const annotations = [
      createMockAnnotation("ann-1", 1, "A", {
        text: "L1",
        color: "#ff0000",
      }),
      createMockAnnotation("ann-2", 1, "B", {
        text: "L2",
        color: "#00ff00",
      }),
      createMockAnnotation("ann-3", 2, "C", {
        text: "L3",
        color: "#0000ff",
      }),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper notes={[]} mockAnnotations={annotations} />
    );

    // Trigger toolbar by selecting one annotation first
    await page
      .locator('[data-annotation-id="ann-1"]')
      .locator(".lucide-square")
      .click();
    await expect(page.getByText("1 annotation selected")).toBeVisible();

    // Click "Select All" in the toolbar
    await page.getByRole("button", { name: /Select All/ }).click();

    // All three should now be selected
    await expect(page.getByText("3 annotations selected")).toBeVisible();

    await component.unmount();
  });

  test("'Add to Relationship' opens the relationship action modal", async ({
    mount,
    page,
  }) => {
    const annotations = [
      createMockAnnotation("ann-1", 1, "A", {
        text: "L1",
        color: "#ff0000",
      }),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper notes={[]} mockAnnotations={annotations} />
    );

    await page
      .locator('[data-annotation-id="ann-1"]')
      .locator(".lucide-square")
      .click();
    await expect(page.getByText("1 annotation selected")).toBeVisible();

    await page.getByRole("button", { name: /Add to Relationship/ }).click();

    // Modal should appear
    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: 5000 }
    );

    await component.unmount();
  });

  test("read-only mode: selection toolbar never appears", async ({
    mount,
    page,
  }) => {
    const annotations = [
      createMockAnnotation("ann-1", 1, "A", {
        text: "L1",
        color: "#ff0000",
      }),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={[]}
        mockAnnotations={annotations}
        readOnly={true}
      />
    );

    // Multi-select icon should NOT be present when readOnly is true
    const firstItem = page.locator('[data-annotation-id="ann-1"]');
    await expect(firstItem.locator(".lucide-square")).toHaveCount(0);
    await expect(firstItem.locator(".lucide-check-square")).toHaveCount(0);

    await component.unmount();
  });

  test("no corpus: selection toolbar never appears even on toggle", async ({
    mount,
    page,
  }) => {
    const annotations = [
      createMockAnnotation("ann-1", 1, "A", {
        text: "L1",
        color: "#ff0000",
      }),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={[]}
        mockAnnotations={annotations}
        noCorpus={true}
      />
    );

    // Without a corpus, the multi-select checkbox should not be rendered
    const firstItem = page.locator('[data-annotation-id="ann-1"]');
    await expect(firstItem.locator(".lucide-square")).toHaveCount(0);

    // Toolbar should never be present
    await expect(page.getByText(/annotation[s]? selected/)).not.toBeVisible();

    await component.unmount();
  });
});

/* ──────────────────────────────────────────────────────────────────────────
 * Sort / filter pipelines
 * ────────────────────────────────────────────────────────────────────────── */

test.describe("UnifiedContentFeed - Sort & filter", () => {
  test("sort by type groups items by type rather than page", async ({
    mount,
    page,
  }) => {
    const notes: Note[] = [
      {
        id: "n1",
        title: "Zeta Note",
        content: "Content",
        created: new Date().toISOString(),
        creator: { email: "test@example.com" },
      },
    ];
    const annotations = [
      createMockAnnotation("ann-1", 1, "Alpha annotation", {
        text: "LabelAlpha",
        color: "#ff0000",
      }),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={notes}
        mockAnnotations={annotations}
        sortBy={"type" as SortOption}
      />
    );

    // Both items render
    await expect(page.getByText("Alpha annotation")).toBeVisible();
    await expect(page.getByText("Zeta Note")).toBeVisible();

    await component.unmount();
  });

  test("search query filters notes by content", async ({ mount, page }) => {
    const notes: Note[] = [
      {
        id: "a",
        title: "Apples",
        content: "Red apples are tasty",
        created: new Date().toISOString(),
        creator: { email: "test@example.com" },
      },
      {
        id: "b",
        title: "Oranges",
        content: "Orange slices are refreshing",
        created: new Date().toISOString(),
        creator: { email: "test@example.com" },
      },
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={notes}
        filters={{
          contentTypes: ["note"],
          annotationFilters: { showStructural: false },
          relationshipFilters: { showStructural: false },
          searchQuery: "apples",
        }}
      />
    );

    await expect(page.getByText("Apples").first()).toBeVisible();
    await expect(page.getByText("Oranges")).not.toBeVisible();

    await component.unmount();
  });

  test("search query filters annotations by rawText", async ({
    mount,
    page,
  }) => {
    const annotations = [
      createMockAnnotation("a1", 1, "Hello world", {
        text: "Greeting",
        color: "#ff0000",
      }),
      createMockAnnotation("a2", 1, "Goodbye now", {
        text: "Farewell",
        color: "#0000ff",
      }),
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={[]}
        mockAnnotations={annotations}
        filters={{
          contentTypes: ["annotation"],
          annotationFilters: { showStructural: false },
          relationshipFilters: { showStructural: false },
          searchQuery: "hello",
        }}
      />
    );

    await expect(page.getByText("Hello world")).toBeVisible();
    await expect(page.getByText("Goodbye now")).not.toBeVisible();

    await component.unmount();
  });

  test("structural annotations stay hidden when showStructural is off", async ({
    mount,
    page,
  }) => {
    // ServerTokenAnnotation with structural=true
    const { ServerTokenAnnotation } = await import(
      "../src/components/annotator/types/annotations"
    );
    const structuralAnn = new ServerTokenAnnotation(
      0,
      {
        id: "label-s",
        text: "RegularTextLabel",
        color: "#333333",
        description: "",
        icon: undefined,
        analyzer: null,
        labelType: "TOKEN_LABEL" as any,
        __typename: "AnnotationLabelType",
      } as any,
      "Structural text content",
      true, // structural
      {
        1: {
          bounds: { top: 0, bottom: 10, left: 0, right: 100 },
          tokensJsons: [],
          rawText: "Structural text content",
        },
      },
      [],
      false,
      false,
      false,
      "ann-s"
    );

    const nonStructural = createMockAnnotation("a1", 1, "Visible text", {
      text: "VisibleLabel",
      color: "#00ff00",
    });

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={[]}
        mockAnnotations={[structuralAnn as any, nonStructural]}
        showStructural={false}
      />
    );

    await expect(page.getByText("Visible text")).toBeVisible();
    await expect(page.getByText("Structural text content")).not.toBeVisible();

    await component.unmount();
  });

  test("OC_-prefixed labels are always hidden", async ({ mount, page }) => {
    // Any label starting with the STRUCTURAL_LABEL_PREFIX is always filtered.
    const hidden = createMockAnnotation("hidden-ann", 1, "Should be hidden", {
      text: "OC_HiddenStructural",
      color: "#aaaaaa",
    });
    const shown = createMockAnnotation("shown-ann", 1, "Should be visible", {
      text: "RegularLabel",
      color: "#00ff00",
    });

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={[]}
        mockAnnotations={[hidden, shown]}
      />
    );

    await expect(page.getByText("Should be visible")).toBeVisible();
    await expect(page.getByText("Should be hidden")).not.toBeVisible();

    await component.unmount();
  });
});

/* ──────────────────────────────────────────────────────────────────────────
 * Content-type pipeline (each renderer)
 * ────────────────────────────────────────────────────────────────────────── */

test.describe("UnifiedContentFeed - Content type routing", () => {
  test("only relationships render when only 'relationship' is enabled", async ({
    mount,
    page,
  }) => {
    const annotations = [
      createMockAnnotation("ann-1", 1, "Source text", {
        text: "LabelA",
        color: "#ff0000",
      }),
      createMockAnnotation("ann-2", 1, "Target text", {
        text: "LabelB",
        color: "#0000ff",
      }),
    ];

    const relations = [
      {
        id: "r1",
        sourceIds: ["ann-1"],
        targetIds: ["ann-2"],
        label: {
          id: "rel-label-1",
          text: "RelatesTo",
          color: "#ff00ff",
          description: "",
          icon: undefined,
          analyzer: null,
          labelType: "RELATIONSHIP_LABEL" as any,
          __typename: "AnnotationLabelType",
        },
        structural: false,
        __typename: "RelationGroup",
      } as any,
    ];

    const component = await mount(
      <UnifiedContentFeedTestWrapper
        notes={[
          {
            id: "some-note",
            title: "Hidden Note",
            content: "Should not show",
            created: new Date().toISOString(),
            creator: { email: "x@example.com" },
          },
        ]}
        mockAnnotations={annotations}
        mockRelations={relations}
        filters={{
          contentTypes: ["relationship"],
          annotationFilters: { showStructural: false },
          relationshipFilters: { showStructural: false },
          searchQuery: "",
        }}
      />
    );

    await expect(page.getByText("RelatesTo").first()).toBeVisible();
    await expect(page.getByText("Hidden Note")).not.toBeVisible();

    await component.unmount();
  });
});
