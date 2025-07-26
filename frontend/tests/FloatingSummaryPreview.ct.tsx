import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedResponse } from "@apollo/client/testing";
import { FloatingSummaryPreviewTestWrapper } from "./FloatingSummaryPreviewTestWrapper";
import { GET_DOCUMENT_SUMMARY_VERSIONS } from "../src/components/knowledge_base/document/floating_summary_preview/graphql/documentSummaryQueries";

/* --------------------------------------------------------------------------
 * Mock data & helpers
 * -------------------------------------------------------------------------- */
const TEST_DOC_ID = "DOC_123";
const TEST_CORPUS_ID = "CORPUS_456";

// Mock summary versions - simulating multiple revisions
const mockSummaryVersions = [
  {
    id: "rev-5",
    version: 5,
    created: "2025-01-28T10:00:00Z",
    snapshot:
      "# Latest Summary\n\nThis is the most recent version of the document summary with comprehensive updates and improvements.",
    diff: "",
    author: {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
    },
  },
  {
    id: "rev-4",
    version: 4,
    created: "2025-01-27T15:30:00Z",
    snapshot:
      "# Summary v4\n\nThis version includes additional context and clarifications.",
    diff: "",
    author: {
      id: "user-2",
      username: "otheruser",
      email: "other@example.com",
    },
  },
  {
    id: "rev-3",
    version: 3,
    created: "2025-01-26T12:00:00Z",
    snapshot: "# Summary v3\n\nMajor restructuring of the content.",
    diff: "",
    author: {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
    },
  },
  {
    id: "rev-2",
    version: 2,
    created: "2025-01-25T09:00:00Z",
    snapshot: "# Summary v2\n\nMinor updates and corrections.",
    diff: "",
    author: {
      id: "user-3",
      username: "thirduser",
      email: "third@example.com",
    },
  },
  {
    id: "rev-1",
    version: 1,
    created: "2025-01-24T14:00:00Z",
    snapshot:
      "# Initial Summary\n\nThis is the first version of the document summary.",
    diff: "",
    author: {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
    },
  },
];

const createMocks = (versions = mockSummaryVersions): MockedResponse[] => [
  {
    request: {
      query: GET_DOCUMENT_SUMMARY_VERSIONS,
      variables: {
        documentId: TEST_DOC_ID,
        corpusId: TEST_CORPUS_ID,
      },
    },
    result: {
      data: {
        document: {
          id: TEST_DOC_ID,
          summaryContent: versions[0]?.snapshot || "",
          currentSummaryVersion: versions[0]?.version || 0,
          summaryRevisions: versions,
          __typename: "DocumentType",
        },
      },
    },
  },
];

// Mock for empty/no summaries
const emptyMocks: MockedResponse[] = [
  {
    request: {
      query: GET_DOCUMENT_SUMMARY_VERSIONS,
      variables: {
        documentId: TEST_DOC_ID,
        corpusId: TEST_CORPUS_ID,
      },
    },
    result: {
      data: {
        document: {
          id: TEST_DOC_ID,
          summaryContent: "",
          currentSummaryVersion: 0,
          summaryRevisions: [],
          __typename: "DocumentType",
        },
      },
    },
  },
];

/* --------------------------------------------------------------------------
 * Tests
 * -------------------------------------------------------------------------- */

test.use({ viewport: { width: 1200, height: 800 } });

test("renders collapsed summary button with version badge", async ({
  mount,
  page,
}) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
    />
  );

  // Wait for collapsed button to be visible with longer timeout for data loading
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await expect(summaryButton).toBeVisible({ timeout: 10000 });

  // Check version badge - it's in a div with specific styling
  const versionBadge = page
    .locator('div:has-text("v5")')
    .filter({ hasText: /^v5$/ });
  await expect(versionBadge).toBeVisible({ timeout: 5000 });
});

test("expands to show version stack when clicked", async ({ mount, page }) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
    />
  );

  // Click summary button to expand
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await expect(summaryButton).toBeVisible({ timeout: 10000 });
  await summaryButton.click();

  // Wait for expanded container - look for the title that includes the icon
  await expect(page.locator('h3:has-text("Document Summary")')).toBeVisible();

  // Move mouse away to top-left to avoid auto-hovering which hides the toggle
  await page.mouse.move(1, 1);

  // Wait for network requests and a short delay for animations
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(700);

  // Verify that the content of the cards is rendered and visible.
  await expect(
    page.locator("p", { hasText: "This is the most recent version" })
  ).toBeVisible({ timeout: 10000 });
  await expect(
    page.locator("p", { hasText: "This version includes additional context" })
  ).toBeVisible();

  // Now, check for the "Show all" button.
  if (mockSummaryVersions.length > 3) {
    // The button may take time to become visible due to animations.
    // We will poll for it to ensure it's ready.
    await expect(async () => {
      const showAllButton = page.getByTestId("fan-toggle-button");
      await expect(showAllButton).toBeVisible();
    }).toPass({
      timeout: 10000,
    });
  }
});

test("fans out all versions and enables navigation", async ({
  mount,
  page,
}) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
    />
  );

  // Expand the component
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await summaryButton.click();
  await moveMouseAway(page);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  await clickFanToggle(page);
  await page.waitForTimeout(400);

  // Navigation arrows should appear
  const leftArrow = page
    .locator("button")
    .filter({ has: page.locator('svg[class*="lucide-chevron-left"]') });
  const rightArrow = page
    .locator("button")
    .filter({ has: page.locator('svg[class*="lucide-chevron-right"]') });

  await expect(leftArrow).toBeVisible();
  await expect(rightArrow).toBeVisible();

  // Left arrow should be disabled at start
  await expect(leftArrow).toBeDisabled();

  // Version indicator should show position
  await expect(page.locator("text=1 / 5")).toBeVisible();
});

test("navigates through versions with arrow buttons", async ({
  mount,
  page,
}) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
    />
  );

  // Expand and fan out
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await summaryButton.click();
  await moveMouseAway(page);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  await clickFanToggle(page);
  await page.waitForTimeout(400);

  const rightArrow = page
    .locator("button")
    .filter({ has: page.locator('svg[class*="lucide-chevron-right"]') });

  // Navigate to next version
  await rightArrow.click();
  await expect(page.locator("text=2 / 5")).toBeVisible();

  // Navigate again
  await rightArrow.click();
  await expect(page.locator("text=3 / 5")).toBeVisible();
});

test("supports keyboard navigation", async ({ mount, page }) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
    />
  );

  // Expand and fan out
  await page.locator('button:has-text("Summary")').click();
  await moveMouseAway(page);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  await clickFanToggle(page);
  await page.waitForTimeout(400);

  // Use arrow keys
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("text=2 / 5")).toBeVisible();

  await page.keyboard.press("ArrowRight");
  await expect(page.locator("text=3 / 5")).toBeVisible();

  await page.keyboard.press("ArrowLeft");
  await expect(page.locator("text=2 / 5")).toBeVisible();
});

test("calls onSwitchToKnowledge when version is clicked", async ({
  mount,
  page,
}) => {
  let switchedContent: string | undefined;

  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
      onSwitchToKnowledge={(content) => {
        switchedContent = content;
      }}
    />
  );

  // Expand
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await summaryButton.click();
  await expect(page.locator('h3:has-text("Document Summary")')).toBeVisible();

  // Wait for cards to be visible
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1000);

  // Click on the latest version card by its content
  const latestCardContent = page.locator("p", {
    hasText: "This is the most recent version",
  });
  await latestCardContent.click({ force: true });

  // Should have called the callback with the content
  await page.waitForTimeout(100);
  expect(switchedContent).toContain("Latest Summary");
});

test("shows empty state when no summaries exist", async ({ mount, page }) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={emptyMocks}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
    />
  );

  // Expand
  await page.locator('button:has-text("Summary")').click();

  // Should show empty state
  await expect(page.locator("text=No summary versions yet.")).toBeVisible();
  await expect(
    page.locator("text=Create your first summary to get started!")
  ).toBeVisible();
});

test("minimizes when minimize button is clicked", async ({ mount, page }) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
    />
  );

  // Expand
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await summaryButton.click();
  // In normal mode (not knowledge layer), title is "Document Summary" without "(Preview)"
  await expect(
    page.locator('h3:has-text("Document Summary")').first()
  ).toBeVisible();

  // Click minimize
  const minimizeButton = page.getByTestId("minimize-button");
  await expect(minimizeButton).toBeVisible();
  await minimizeButton.click();

  // Wait for animation to complete
  await page.waitForTimeout(500);

  // Should be collapsed again - the h3 title should not be visible
  await expect(
    page.locator('h3:has-text("Document Summary")')
  ).not.toBeVisible();
  await expect(summaryButton).toBeVisible();
});

test("renders in knowledge layer mode with back button", async ({
  mount,
  page,
}) => {
  let backClicked = false;

  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
      isInKnowledgeLayer={true}
      onBackToDocument={() => {
        backClicked = true;
      }}
    />
  );

  // Should show back button instead of summary button
  const backButton = page.locator('button:has-text("Back")');
  await expect(backButton).toBeVisible();

  // Click back button
  await backButton.click();
  await page.waitForTimeout(100);
  expect(backClicked).toBe(true);
});

test("shows content preview on card hover", async ({ mount, page }) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
    />
  );

  // Expand and fan out
  await page.locator('button:has-text("Summary")').click();
  await moveMouseAway(page);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  await clickFanToggle(page);
  await page.waitForTimeout(400);

  // Hover over a card - the card should expand slightly
  // Look for the v4 version card
  const card = page.locator("p", {
    hasText: "This version includes additional context",
  });
  const cardHandle = await card.elementHandle();
  if (cardHandle) {
    await page.evaluate((el) => {
      el.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    }, cardHandle);
  }

  // Move to next card
  const rightArrow = page
    .locator("button")
    .filter({ has: page.locator('svg[class*="lucide-chevron-right"]') });
  await rightArrow.click();
  await expect(page.locator("text=2 / 5")).toBeVisible();
});

test("collapses stack when collapse button is clicked", async ({
  mount,
  page,
}) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
    />
  );

  // Expand and fan out
  await page.locator('button:has-text("Summary")').click();
  await moveMouseAway(page);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  await clickFanToggle(page);
  await page.waitForTimeout(400);

  // Should show navigation
  await expect(page.locator("text=1 / 5")).toBeVisible();

  // Click collapse
  await clickFanToggle(page);
  await moveMouseAway(page);
  await page.waitForTimeout(300);

  // Navigation should be hidden, only 3 cards visible
  await expect(page.locator("text=1 / 5")).not.toBeVisible();

  // The "Show all" button should be visible again
  const showAllBtnAgain = page.getByTestId("fan-toggle-button");
  await expect(showAllBtnAgain).toBeVisible();
});

// Helper to move the mouse away so hover doesn't auto-fan the stack
const moveMouseAway = async (page: any) => {
  await page.mouse.move(1, 1);
  await page.waitForTimeout(200); // small delay
};

// Helper to click the fan-toggle button reliably even if something briefly overlays it
const clickFanToggle = async (page: any) => {
  const btn = page.getByTestId("fan-toggle-button");
  await expect(btn).toBeVisible({ timeout: 10_000 });
  // use JavaScript click to avoid pointer-interception issues
  const handle = await btn.elementHandle();
  if (handle) {
    await page.evaluate((el) => (el as HTMLElement).click(), handle);
  }
};

test("read-only: displays summaries normally", async ({ mount, page }) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
      readOnly={true}
    />
  );

  // Summary button should be visible
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await expect(summaryButton).toBeVisible({ timeout: 10000 });

  // Version badge should show
  const versionBadge = page
    .locator('div:has-text("v5")')
    .filter({ hasText: /^v5$/ });
  await expect(versionBadge).toBeVisible({ timeout: 5000 });

  // Can expand
  await summaryButton.click();
  await expect(page.locator('h3:has-text("Document Summary")')).toBeVisible();
});

test("read-only: navigation between versions works", async ({
  mount,
  page,
}) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
      readOnly={true}
    />
  );

  // Expand and fan out
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await summaryButton.click();
  await moveMouseAway(page);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  await clickFanToggle(page);
  await page.waitForTimeout(400);

  // Navigation should work
  const rightArrow = page
    .locator("button")
    .filter({ has: page.locator('svg[class*="lucide-chevron-right"]') });

  await rightArrow.click();
  await expect(page.locator("text=2 / 5")).toBeVisible();

  // Keyboard navigation should also work
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("text=3 / 5")).toBeVisible();
});

test("read-only: switching to knowledge layer still works", async ({
  mount,
  page,
}) => {
  let switchedContent: string | undefined;

  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
      readOnly={true}
      onSwitchToKnowledge={(content) => {
        switchedContent = content;
      }}
    />
  );

  // Expand
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await summaryButton.click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1000);

  // Click on a version - viewing should still be allowed
  const latestCardContent = page.locator("p", {
    hasText: "This is the most recent version",
  });
  await latestCardContent.click({ force: true });

  await page.waitForTimeout(100);
  expect(switchedContent).toContain("Latest Summary");
});

test("read-only: empty state shows but without edit options", async ({
  mount,
  page,
}) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={emptyMocks}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
      readOnly={true}
    />
  );

  // Expand
  await page.locator('button:has-text("Summary")').click();

  // Empty state message should still show
  await expect(page.locator("text=No summary versions yet.")).toBeVisible();
  await expect(
    page.locator("text=Create your first summary to get started!")
  ).toBeVisible();

  // Note: Since there's no create button in the component,
  // the readOnly flag doesn't affect any UI elements in empty state
});

test("read-only: minimize and back buttons remain functional", async ({
  mount,
  page,
}) => {
  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
      readOnly={true}
    />
  );

  // Expand
  const summaryButton = page.locator("button").filter({ hasText: "Summary" });
  await summaryButton.click();
  await expect(page.locator('h3:has-text("Document Summary")')).toBeVisible();

  // Minimize should work
  const minimizeButton = page.getByTestId("minimize-button");
  await expect(minimizeButton).toBeVisible();
  const handleMin = await minimizeButton.elementHandle();
  if (handleMin) {
    await page.evaluate((el) => (el as HTMLElement).click(), handleMin);
  }

  // Should be collapsed
  await expect(
    page.locator('h3:has-text("Document Summary")')
  ).not.toBeVisible();
  await expect(summaryButton).toBeVisible();
});

test("read-only: knowledge layer mode with back button works", async ({
  mount,
  page,
}) => {
  let backClicked = false;

  await mount(
    <FloatingSummaryPreviewTestWrapper
      mocks={createMocks()}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      documentTitle="Test Document"
      readOnly={true}
      isInKnowledgeLayer={true}
      onBackToDocument={() => {
        backClicked = true;
      }}
    />
  );

  // Back button should be functional
  const backButton = page.locator('button:has-text("Back")');
  await expect(backButton).toBeVisible();

  await backButton.click();
  await page.waitForTimeout(100);
  expect(backClicked).toBe(true);
});
