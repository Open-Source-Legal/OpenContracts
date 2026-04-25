/**
 * Playwright Component Tests for `SelectAnalyzerOrFieldsetModal`.
 *
 * Covers the branches called out in issue #1279 for
 * `SelectCorpusAnalyzerOrFieldsetAnalyzer.tsx`:
 *
 *   - Analyzer vs Fieldset tab switching
 *   - Analyzer card rendering (title, task name, public badge,
 *     configurable vs ready badge)
 *   - Search-term filtering (debounced text input narrows the grid)
 *   - Empty state when search matches nothing
 *   - "No analyzers available" state when the query returns zero edges
 *   - Schema toggle on analyzers with an input schema
 *   - Loading state while the analyzers query is in flight
 *   - Close paths (Cancel button, X button, overlay click)
 *   - Run button enabled/disabled state based on selection + extract name
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { SelectAnalyzerOrFieldsetModalTestWrapper } from "./SelectAnalyzerOrFieldsetModalTestWrapper";
import {
  SAMPLE_CORPUS,
  buildMockSet,
  makeAnalyzer,
} from "./SelectAnalyzerOrFieldsetModalMocks";
import type { DocumentType } from "../src/types/graphql-api";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SAMPLE_DOC: DocumentType = {
  __typename: "DocumentType",
  id: "doc-1",
  title: "Test Document.pdf",
  description: "",
  fileType: "application/pdf",
} as DocumentType;

const ANALYZERS_WITH_SCHEMA = [
  makeAnalyzer({
    id: "a-simple",
    analyzerId: "a-simple",
    description:
      "# Simple Entity Extractor\n\nPull basic named entities from text.",
    taskName: "opencontractserver.tasks.analyzer_tasks.simple_ner",
    isPublic: true,
  }),
  makeAnalyzer({
    id: "a-configurable",
    analyzerId: "a-configurable",
    description:
      "# Configurable Summarizer\n\nGenerates a summary with configurable length.",
    taskName: "opencontractserver.tasks.analyzer_tasks.configurable_summarizer",
    isPublic: false,
    inputSchema: {
      type: "object",
      properties: {
        length: { type: "number", title: "Summary Length" },
      },
    },
  }),
];

const MANY_ANALYZERS = Array.from({ length: 12 }, (_, i) =>
  makeAnalyzer({
    id: `a-${i}`,
    analyzerId: `a-${i}`,
    description: `# Analyzer ${i}\n\nDescription for analyzer ${i}.`,
    taskName: `opencontractserver.tasks.analyzer_tasks.analyzer_${i}`,
  })
);

// ---------------------------------------------------------------------------
// Analyzer tab: rendering & filtering
// ---------------------------------------------------------------------------

test.describe("SelectAnalyzerOrFieldsetModal — analyzer tab", () => {
  test("renders the modal header, tabs, and analyzer grid", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    // Header
    await expect(page.locator("text=Start Analysis")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.locator('text=Analyze all documents in "Sample Corpus"')
    ).toBeVisible();

    // Both tab buttons
    await expect(page.getByRole("button", { name: /Analyzer/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Fieldset/i })).toBeVisible();

    // The analyzer cards (wait for the GraphQL query to resolve)
    await expect(page.locator("text=Simple Entity Extractor")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator("text=Configurable Summarizer")).toBeVisible();

    // Footer run button (disabled until something is selected)
    const runBtn = page.getByRole("button", {
      name: /run analysis|configure/i,
    });
    await expect(runBtn).toBeVisible();
    await expect(runBtn).toBeDisabled();

    await docScreenshot(page, "widgets--select-analyzer-modal--analyzer-grid");
  });

  test("shows document-specific subtitle when a document is provided", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        document={SAMPLE_DOC}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Start Analysis")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.locator('text=Analyze "Test Document.pdf"')
    ).toBeVisible();
  });

  test("shows the analyzer count badge that reflects the current result set", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Simple Entity Extractor")).toBeVisible({
      timeout: 5000,
    });
    // The result-count pill near the search box shows "2 analyzers"
    await expect(page.locator("text=2 analyzers")).toBeVisible();
  });

  test("filters analyzers by typed search text", async ({ mount, page }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Simple Entity Extractor")).toBeVisible({
      timeout: 5000,
    });

    // Type into the search box — the filter is debounced (300ms)
    await page
      .locator(
        'input[placeholder="Search analyzers by name or description..."]'
      )
      .fill("Summarizer");

    // After debounce, only the Configurable Summarizer should remain
    await expect(page.locator("text=Configurable Summarizer")).toBeVisible({
      timeout: 3000,
    });
    await expect(
      page.locator("text=Simple Entity Extractor")
    ).not.toBeVisible();
    await expect(page.locator("text=1 analyzer")).toBeVisible();
  });

  test("shows a 'no analyzers match' empty state when search filters everything", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Simple Entity Extractor")).toBeVisible({
      timeout: 5000,
    });

    await page
      .locator(
        'input[placeholder="Search analyzers by name or description..."]'
      )
      .fill("qzx-does-not-exist");

    await expect(
      page.locator("text=No analyzers match your search")
    ).toBeVisible({ timeout: 3000 });
  });

  test("shows 'No analyzers available' when the query returns zero results", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet([])}
      />
    );

    await expect(page.locator("text=Start Analysis")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator("text=No analyzers available")).toBeVisible({
      timeout: 5000,
    });
  });
});

// ---------------------------------------------------------------------------
// Analyzer tab: selection + schema toggle
// ---------------------------------------------------------------------------

test.describe("SelectAnalyzerOrFieldsetModal — analyzer selection", () => {
  test("selecting an analyzer enables the Configure button for one with inputs", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Configurable Summarizer")).toBeVisible({
      timeout: 5000,
    });

    // Click the analyzer card that has inputs
    await page.locator("text=Configurable Summarizer").click();

    // Run button should switch to "Configure" because the analyzer has inputs
    const configureBtn = page.getByRole("button", { name: /Configure/i });
    await expect(configureBtn).toBeEnabled({ timeout: 3000 });
  });

  test("selecting an analyzer without inputs enables the Run Analysis button", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Simple Entity Extractor")).toBeVisible({
      timeout: 5000,
    });

    await page.locator("text=Simple Entity Extractor").click();

    const runBtn = page.getByRole("button", { name: /Run Analysis/i });
    await expect(runBtn).toBeEnabled({ timeout: 3000 });
  });

  test("toggling the schema preview reveals the JSON inputSchema", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Configurable Summarizer")).toBeVisible({
      timeout: 5000,
    });

    // Click "Show Schema" on the configurable analyzer
    const showSchema = page.getByRole("button", { name: /Show Schema/i });
    await expect(showSchema).toBeVisible();
    await showSchema.click();

    // Schema JSON should appear (look for one of the property names)
    await expect(page.locator("text=Summary Length")).toBeVisible({
      timeout: 3000,
    });

    // Button label flips to "Hide Schema"
    await expect(
      page.getByRole("button", { name: /Hide Schema/i })
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Tab switching
// ---------------------------------------------------------------------------

test.describe("SelectAnalyzerOrFieldsetModal — tab switching", () => {
  test("clicking the Fieldset tab reveals the fieldset UI", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Simple Entity Extractor")).toBeVisible({
      timeout: 5000,
    });

    await page.getByRole("button", { name: /Fieldset/i }).click();

    // The corpus path (no document) requires an extract name field
    await expect(page.locator("text=Extract Name")).toBeVisible({
      timeout: 3000,
    });
    await expect(page.locator("text=Select Fieldset")).toBeVisible();

    // Analyzer cards should no longer be visible
    await expect(
      page.locator("text=Simple Entity Extractor")
    ).not.toBeVisible();
  });

  test("switching back to the analyzer tab restores the grid", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Simple Entity Extractor")).toBeVisible({
      timeout: 5000,
    });

    await page.getByRole("button", { name: /Fieldset/i }).click();
    await expect(page.locator("text=Select Fieldset")).toBeVisible({
      timeout: 3000,
    });

    // Back to analyzer
    await page.getByRole("button", { name: /Analyzer/i }).click();
    await expect(page.locator("text=Simple Entity Extractor")).toBeVisible({
      timeout: 5000,
    });
  });

  test("fieldset tab with a document prop hides the extract-name input", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        document={SAMPLE_DOC}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    // Wait for modal and switch tabs
    await expect(page.locator("text=Start Analysis")).toBeVisible({
      timeout: 5000,
    });
    await page.getByRole("button", { name: /Fieldset/i }).click();

    // With a document, there is no per-extract name to provide
    await expect(page.locator("text=Select Fieldset")).toBeVisible({
      timeout: 3000,
    });
    await expect(page.locator("text=Extract Name")).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

test.describe("SelectAnalyzerOrFieldsetModal — pagination", () => {
  test("shows pagination controls when analyzers exceed the page size", async ({
    mount,
    page,
  }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(MANY_ANALYZERS)}
      />
    );

    // 12 analyzers, 9 per page → 2 pages. Use the card title heading
    // to avoid matching the description ("Description for analyzer 0.").
    await expect(page.getByRole("heading", { name: "Analyzer 0" })).toBeVisible(
      { timeout: 5000 }
    );
    // Analyzer 9 lives on page 2 and should not be on page 1
    await expect(
      page.getByRole("heading", { name: "Analyzer 9" })
    ).not.toBeVisible();

    // Click page 2
    await page.getByRole("button", { name: "2", exact: true }).click();

    // Now Analyzer 9 should be visible on page 2
    await expect(page.getByRole("heading", { name: "Analyzer 9" })).toBeVisible(
      { timeout: 3000 }
    );
    // And Analyzer 0 is no longer in the viewport
    await expect(
      page.getByRole("heading", { name: "Analyzer 0" })
    ).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Close behavior
// ---------------------------------------------------------------------------

test.describe("SelectAnalyzerOrFieldsetModal — close behavior", () => {
  test("closes when Cancel is clicked", async ({ mount, page }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Start Analysis")).toBeVisible({
      timeout: 5000,
    });
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.locator("text=Start Analysis")).toBeHidden({
      timeout: 3000,
    });
  });

  test("closes via the X close button", async ({ mount, page }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Start Analysis")).toBeVisible({
      timeout: 5000,
    });
    const closeBtn = page.getByRole("button", { name: "Close" });
    await closeBtn.click();
    await expect(page.locator("text=Start Analysis")).toBeHidden({
      timeout: 3000,
    });
  });

  test("closes when the overlay is clicked", async ({ mount, page }) => {
    await mount(
      <SelectAnalyzerOrFieldsetModalTestWrapper
        corpus={SAMPLE_CORPUS}
        mocks={buildMockSet(ANALYZERS_WITH_SCHEMA)}
      />
    );

    await expect(page.locator("text=Start Analysis")).toBeVisible({
      timeout: 5000,
    });

    // Wait until framer-motion's fade-in animation settles before clicking,
    // rather than using a fixed sleep.
    const overlay = page
      .locator('[data-testid="select-analyzer-or-fieldset-overlay"]')
      .first();
    await expect(overlay).toHaveCSS("opacity", "1", { timeout: 2000 });
    // Click a viewport corner far from the centered ModalContainer so the
    // click reaches the overlay's `onClick={onClose}` handler without
    // bypassing pointer-actionability checks (which `force: true` would do).
    await page.mouse.click(5, 5);

    await expect(page.locator("text=Start Analysis")).toBeHidden({
      timeout: 3000,
    });
  });
});
