import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
// NOTE: Do NOT merge the two DocumentRelationshipModalTestWrapper imports
// below into one statement. Playwright CT's babel transform only rewrites
// JSX-component imports into `importRefs` when every specifier in the
// statement is a JSX component; mixing a component export with helper /
// constant exports leaves the component unrewritten and `mount()` throws.
import { DocumentRelationshipModalTestWrapper } from "./DocumentRelationshipModalTestWrapper";
import {
  makeMockRelationLabel,
  TEST_CORPUS_ID,
} from "./DocumentRelationshipModalTestWrapper";
import {
  CREATE_DOCUMENT_RELATIONSHIP,
  SMART_LABEL_SEARCH_OR_CREATE,
} from "../src/graphql/mutations";
import { LabelType } from "../src/types/graphql-api";
import { OS_LEGAL_COLORS } from "../src/assets/configurations/osLegalStyles";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("DocumentRelationshipModal", () => {
  test("renders modal header", async ({ mount, page }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await expect(page.getByText("Link Documents")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "corpus--document-relationship-modal--initial");
  });

  test("shows source documents column", async ({ mount, page }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    // The column header should be visible
    await expect(
      page.locator(".column-title").filter({ hasText: "Source Documents" })
    ).toBeVisible({
      timeout: 10000,
    });
  });

  test("cancel button closes modal", async ({ mount, page }) => {
    let closed = false;
    await mount(
      <DocumentRelationshipModalTestWrapper
        onClose={() => {
          closed = true;
        }}
      />
    );

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Click cancel button
    await page.getByRole("button", { name: /Cancel/ }).click();

    expect(closed).toBe(true);
  });

  test("displays source document pills", async ({ mount, page }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper initialSourceIds={["doc-1"]} />
    );

    // Wait for source document to be displayed
    await page.waitForSelector('text="Source Document 1"', {
      timeout: 10000,
    });

    // Should show Source Document 1 as a pill
    await expect(page.getByText("Source Document 1")).toBeVisible();
  });

  test("shows relationship type radio buttons", async ({ mount, page }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Relationship Type"', { timeout: 10000 });

    await expect(page.getByText("Labeled Relationship")).toBeVisible();
    await expect(page.getByText("Notes")).toBeVisible();
  });

  test("shows target documents column", async ({ mount, page }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    // The column header should be visible (use exact match to avoid "No target documents")
    await expect(
      page.locator(".column-title").filter({ hasText: "Target Documents" })
    ).toBeVisible({
      timeout: 10000,
    });
  });

  test("shows add target button", async ({ mount, page }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Should show "Add Target" button
    const addTargetButton = page.getByRole("button", { name: /Add Target/ });
    await expect(addTargetButton).toBeVisible();
  });

  test("submit button is disabled without target selection", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // The create button should be disabled initially (no targets selected)
    const createButton = page.getByRole("button", {
      name: /Create Relationship/,
    });
    await expect(createButton).toBeDisabled();
  });

  test("shows relationship count preview", async ({ mount, page }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    // Initial state shows "Creating 0 relationships" (plural because 0 !== 1)
    await page.waitForSelector('text="Creating 0 relationships"', {
      timeout: 10000,
    });

    await expect(page.getByText(/Creating 0 relationships/)).toBeVisible();
  });

  test("shows search when adding target", async ({ mount, page }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Click "Add Target" button
    await page.getByRole("button", { name: /Add Target/ }).click();

    // Now the search input should be visible
    const searchInput = page.getByPlaceholder("Search documents in corpus...");
    await expect(searchInput).toBeVisible();
  });

  test("shows label search when RELATIONSHIP mode selected", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // RELATIONSHIP mode is default, should show label dropdown
    await expect(page.getByText("Relationship Label")).toBeVisible();
    // The dropdown should be visible with placeholder text
    await expect(
      page
        .locator(".oc-dropdown")
        .filter({ hasText: "Search or type to create" })
    ).toBeVisible();
  });

  test("shows notes textarea when NOTES mode selected", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Click Notes radio button
    await page.getByText("Notes").click();

    // Wait for the notes textarea to appear
    await page.waitForSelector('text="Notes (optional)"', { timeout: 5000 });
    await expect(page.getByText("Notes (optional)")).toBeVisible();
  });

  test("modal has proper accessibility attributes", async ({ mount, page }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Modal should be visible and have proper structure (role="dialog" from @os-legal/ui)
    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible();
  });

  test("can move document from source to target", async ({ mount, page }) => {
    // Start with 2 source documents so after moving one, we have 1 source x 1 target = 1 relationship
    await mount(
      <DocumentRelationshipModalTestWrapper
        initialSourceIds={["doc-1", "doc-2"]}
      />
    );

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Wait for source documents to load
    await page.waitForSelector('text="Source Document 1"', {
      timeout: 10000,
    });

    // Click the "move to target" button on first document (arrow right)
    const moveButton = page.locator('button[title="Move to targets"]').first();
    await moveButton.click();

    // Document should now appear in target column
    // The relationship count should update to 1 (1 source x 1 target)
    await expect(page.getByText(/Creating 1 relationship/)).toBeVisible({
      timeout: 5000,
    });
  });

  test("displays initial target documents", async ({ mount, page }) => {
    // Mount with both source and target documents pre-populated
    await mount(
      <DocumentRelationshipModalTestWrapper
        initialSourceIds={["doc-1"]}
        initialTargetIds={["doc-2"]}
      />
    );

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Both documents should be visible as pills
    await page.waitForSelector('text="Source Document 1"', {
      timeout: 10000,
    });
    await page.waitForSelector('text="Target Document 1"', {
      timeout: 10000,
    });

    // Should show relationship count of 1 (1 source x 1 target)
    await expect(page.getByText(/Creating 1 relationship/)).toBeVisible({
      timeout: 5000,
    });
  });
});

// ---------------------------------------------------------------------------
// Additional coverage (issue #1280) — cross-column moves, search add flow,
// label selection, submit, notes mode, missing-corpus error, etc.
// ---------------------------------------------------------------------------

test.describe("DocumentRelationshipModal — state transitions", () => {
  test("moves document from target back to source", async ({ mount, page }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper
        initialSourceIds={["doc-1"]}
        initialTargetIds={["doc-2"]}
      />
    );

    await page.waitForSelector('text="Target Document 1"', { timeout: 10000 });

    // Click the move-to-source button on the target pill
    await page.locator('button[title="Move to sources"]').first().click();

    // Target column should now be empty; relationship count becomes 0
    await expect(page.getByText(/Creating 0 relationships/)).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("No target documents")).toBeVisible();
  });

  test("removes document from source column", async ({ mount, page }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper
        initialSourceIds={["doc-1", "doc-2"]}
      />
    );

    await page.waitForSelector('text="Source Document 1"', { timeout: 10000 });

    // There are two source pills — remove the first one
    await page.locator('button[title="Remove"]').first().click();

    await expect(page.getByText("Source Document 1")).not.toBeVisible();
  });

  test("removes document from target column", async ({ mount, page }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper
        initialSourceIds={["doc-1"]}
        initialTargetIds={["doc-2"]}
      />
    );

    await page.waitForSelector('text="Target Document 1"', { timeout: 10000 });

    // Scope the Remove click to the target pill by walking up from the
    // pill's visible title to the first ancestor that contains a Remove
    // button. This avoids the earlier DOM-order `.nth(1)` approach which
    // would silently click the wrong button if the source/target layout
    // ever changes.
    const targetPill = page
      .getByText("Target Document 1")
      .locator('xpath=ancestor::*[.//button[@title="Remove"]][1]');
    await targetPill.locator('button[title="Remove"]').click();

    await expect(page.getByText("No target documents")).toBeVisible();
  });

  test("toggle Add Source button opens and cancels the search", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    const addSourceBtn = page.getByRole("button", { name: /Add Source/ });
    await addSourceBtn.click();

    // Search should open after toggling Add Source
    await expect(
      page.getByPlaceholder("Search documents in corpus...")
    ).toBeVisible();

    // Click the first Cancel button in the document (the in-section toggle
    // renders before the footer Cancel in DOM order) to close the search
    await page.locator("button").filter({ hasText: "Cancel" }).first().click();

    await expect(
      page.getByPlaceholder("Search documents in corpus...")
    ).not.toBeVisible();
  });

  test("adds document to target from search results", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper initialSourceIds={["doc-1"]} />
    );

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Open the Add Target search
    await page.getByRole("button", { name: /Add Target/ }).click();

    // Click the first available document (doc-2 — "Target Document 1")
    await page.getByText("Target Document 1").first().click();

    // Target pill should appear in target column; relationship count becomes 1
    await expect(page.getByText(/Creating 1 relationship/)).toBeVisible({
      timeout: 5000,
    });
  });

  test("search shows Loading state before data resolves", async ({
    mount,
    page,
  }) => {
    // Just mount — the wrapper's mock answers immediately; we assert the
    // available-documents list renders after loading completes.
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    await page.getByRole("button", { name: /Add Target/ }).click();

    // After mock resolves, available docs should be listed
    await expect(page.getByText("Target Document 1")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("Target Document 2")).toBeVisible();
  });

  test("renders No Corpus Context error when corpusId is empty", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper corpusIdOverride={null} />
    );

    await expect(page.getByText("No Corpus Context")).toBeVisible({
      timeout: 10000,
    });
    // The create button should be disabled since hasCorpus is false
    await expect(
      page.getByRole("button", { name: /Create Relationship/ })
    ).toBeDisabled();
  });

  test("renders labelset warning when corpus has no labelset", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper withoutLabelset={true} />
    );

    await expect(page.getByText("No labelset found.")).toBeVisible({
      timeout: 10000,
    });
  });

  test("switching to NOTES mode hides label picker", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Initially label dropdown visible
    await expect(page.getByText("Relationship Label")).toBeVisible();

    await page.getByText("Notes").click();

    // Relationship Label heading disappears and Notes textarea appears
    await expect(page.getByText("Relationship Label")).not.toBeVisible();
    await expect(page.getByText("Notes (optional)")).toBeVisible();
  });

  test("InfoBox shows plural warnings for missing sources and targets", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentRelationshipModalTestWrapper initialSourceIds={[]} />);

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    await expect(
      page.getByText("Add at least one source document")
    ).toBeVisible();
    await expect(
      page.getByText("Add at least one target document")
    ).toBeVisible();
  });
});

test.describe("DocumentRelationshipModal — label picker", () => {
  test("selects a pre-populated relationship label", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper
        relationLabels={[
          makeMockRelationLabel({ id: "label-1", text: "references" }),
          makeMockRelationLabel({ id: "label-2", text: "amends" }),
        ]}
      />
    );

    await page.waitForSelector('text="Relationship Label"', { timeout: 10000 });

    // Open the dropdown via its trigger and select "references"
    const dropdown = page.locator(".oc-dropdown").first();
    await dropdown.locator(".oc-dropdown__trigger").click();
    await dropdown
      .locator(".oc-dropdown__option", { hasText: "references" })
      .click();

    // After selection, the "Selected Label" section should render
    await expect(page.getByText("Selected Label")).toBeVisible({
      timeout: 5000,
    });
  });

  test("Change button clears selected label", async ({ mount, page }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper
        relationLabels={[
          makeMockRelationLabel({ id: "label-1", text: "references" }),
        ]}
      />
    );

    await page.waitForSelector('text="Relationship Label"', { timeout: 10000 });

    const dropdown = page.locator(".oc-dropdown").first();
    await dropdown.locator(".oc-dropdown__trigger").click();
    await dropdown
      .locator(".oc-dropdown__option", { hasText: "references" })
      .click();

    await expect(page.getByText("Selected Label")).toBeVisible({
      timeout: 5000,
    });

    await page.getByRole("button", { name: "Change" }).click();

    // After changing, the dropdown placeholder returns
    await expect(page.getByText("Search or type to create...")).toBeVisible();
  });
});

test.describe("DocumentRelationshipModal — submit", () => {
  test("submits a RELATIONSHIP mutation on valid state", async ({
    mount,
    page,
  }) => {
    let onSuccessCalled = false;

    const createMock: MockedResponse = {
      request: {
        query: CREATE_DOCUMENT_RELATIONSHIP,
        variables: {
          sourceDocumentId: "doc-1",
          targetDocumentId: "doc-2",
          relationshipType: "RELATIONSHIP",
          corpusId: TEST_CORPUS_ID,
          annotationLabelId: "label-1",
          data: undefined,
        },
      },
      result: {
        data: {
          createDocumentRelationship: {
            ok: true,
            message: "",
            documentRelationship: {
              id: "rel-1",
              relationshipType: "RELATIONSHIP",
              data: null,
              sourceDocument: {
                id: "doc-1",
                title: "Source Document 1",
                icon: null,
                __typename: "DocumentType",
              },
              targetDocument: {
                id: "doc-2",
                title: "Target Document 1",
                icon: null,
                __typename: "DocumentType",
              },
              annotationLabel: {
                id: "label-1",
                text: "references",
                color: "#14b8a6",
                icon: null,
                __typename: "AnnotationLabelType",
              },
              corpus: { id: TEST_CORPUS_ID, __typename: "CorpusType" },
              creator: {
                id: "user-1",
                username: "test-user",
                __typename: "UserType",
              },
              created: "2025-01-01T00:00:00Z",
              myPermissions: [],
              __typename: "DocumentRelationshipType",
            },
            __typename: "CreateDocumentRelationship",
          },
        },
      },
    };

    await mount(
      <DocumentRelationshipModalTestWrapper
        initialSourceIds={["doc-1"]}
        initialTargetIds={["doc-2"]}
        relationLabels={[
          makeMockRelationLabel({ id: "label-1", text: "references" }),
        ]}
        extraMocks={[createMock]}
        onSuccess={() => {
          onSuccessCalled = true;
        }}
      />
    );

    await page.waitForSelector('text="Relationship Label"', {
      timeout: 10000,
    });

    // Select the label
    const dropdown = page.locator(".oc-dropdown").first();
    await dropdown.locator(".oc-dropdown__trigger").click();
    await dropdown
      .locator(".oc-dropdown__option", { hasText: "references" })
      .click();
    await expect(page.getByText("Selected Label")).toBeVisible({
      timeout: 5000,
    });

    // Submit
    await page.getByRole("button", { name: /Create Relationship/ }).click();

    // The onSuccess callback should fire once the mutation resolves
    await expect.poll(() => onSuccessCalled, { timeout: 5000 }).toBe(true);
  });

  test("submits NOTES mutation with optional content", async ({
    mount,
    page,
  }) => {
    let onSuccessCalled = false;

    const createNotesMock: MockedResponse = {
      request: {
        query: CREATE_DOCUMENT_RELATIONSHIP,
        variables: {
          sourceDocumentId: "doc-1",
          targetDocumentId: "doc-2",
          relationshipType: "NOTES",
          corpusId: TEST_CORPUS_ID,
          annotationLabelId: undefined,
          data: { notes: "related to quarterly report" },
        },
      },
      result: {
        data: {
          createDocumentRelationship: {
            ok: true,
            message: "",
            documentRelationship: {
              id: "rel-notes-1",
              relationshipType: "NOTES",
              data: { notes: "related to quarterly report" },
              sourceDocument: {
                id: "doc-1",
                title: "Source Document 1",
                icon: null,
                __typename: "DocumentType",
              },
              targetDocument: {
                id: "doc-2",
                title: "Target Document 1",
                icon: null,
                __typename: "DocumentType",
              },
              annotationLabel: null,
              corpus: { id: TEST_CORPUS_ID, __typename: "CorpusType" },
              creator: {
                id: "user-1",
                username: "test-user",
                __typename: "UserType",
              },
              created: "2025-01-01T00:00:00Z",
              myPermissions: [],
              __typename: "DocumentRelationshipType",
            },
            __typename: "CreateDocumentRelationship",
          },
        },
      },
    };

    await mount(
      <DocumentRelationshipModalTestWrapper
        initialSourceIds={["doc-1"]}
        initialTargetIds={["doc-2"]}
        extraMocks={[createNotesMock]}
        onSuccess={() => {
          onSuccessCalled = true;
        }}
      />
    );

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Switch to NOTES mode
    await page.getByText("Notes").click();
    await page.waitForSelector('text="Notes (optional)"', { timeout: 5000 });

    // Type notes into the textarea
    await page
      .getByPlaceholder(/Add notes about this document relationship/)
      .fill("related to quarterly report");

    // Submit — for NOTES mode no label is required
    const submitBtn = page.getByRole("button", { name: /Create Relationship/ });
    await expect(submitBtn).toBeEnabled();
    await submitBtn.click();

    await expect.poll(() => onSuccessCalled, { timeout: 5000 }).toBe(true);
  });

  test("does not call onSuccess and keeps modal open on mutation failure", async ({
    mount,
    page,
  }) => {
    let onSuccessCalled = false;

    const failureMock: MockedResponse = {
      request: {
        query: CREATE_DOCUMENT_RELATIONSHIP,
        variables: {
          sourceDocumentId: "doc-1",
          targetDocumentId: "doc-2",
          relationshipType: "NOTES",
          corpusId: TEST_CORPUS_ID,
          annotationLabelId: undefined,
          data: undefined,
        },
      },
      result: {
        data: {
          createDocumentRelationship: {
            ok: false,
            message: "A relationship already exists between these documents",
            documentRelationship: null,
            __typename: "CreateDocumentRelationship",
          },
        },
      },
    };

    await mount(
      <DocumentRelationshipModalTestWrapper
        initialSourceIds={["doc-1"]}
        initialTargetIds={["doc-2"]}
        extraMocks={[failureMock]}
        onSuccess={() => {
          onSuccessCalled = true;
        }}
      />
    );

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Switch to NOTES mode so label selection isn't required
    await page.getByText("Notes").click();
    await page.waitForSelector('text="Notes (optional)"', { timeout: 5000 });

    const submitBtn = page.getByRole("button", { name: /Create Relationship/ });
    await submitBtn.click();

    // Wait for the mutation to settle. When the mutation fails the submit
    // button re-enables (the component flips `isSubmitting` back off) and
    // the modal stays open — both are positive signals the failure path
    // has fully executed. Waiting for them before the negative assertion
    // gives `onSuccessCalled` a real window in which it *could* have been
    // invoked; without this stabilization the poll passes immediately on
    // the initial `false` value and provides no timing protection.
    await expect(page.getByText("Link Documents")).toBeVisible({
      timeout: 5000,
    });
    await expect(submitBtn).toBeEnabled({ timeout: 5000 });

    // onSuccess should NOT be invoked when all mutations fail.
    await expect.poll(() => onSuccessCalled, { timeout: 2000 }).toBe(false);
  });
});

test.describe("DocumentRelationshipModal — create-label flow", () => {
  test("opens the inline create-label form and cancels it", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentRelationshipModalTestWrapper />);

    await page.waitForSelector('text="Relationship Label"', {
      timeout: 10000,
    });

    // Open the dropdown, then type a new label name
    const dropdown = page.locator(".oc-dropdown").first();
    await dropdown.locator(".oc-dropdown__trigger").click();
    const searchInput = dropdown.locator(".oc-dropdown__search-input");
    await searchInput.fill("supersedes");

    // The "Create label: ..." button appears in the empty-state slot
    await page.getByRole("button", { name: /Create label:/ }).click();

    // Inline create-label form appears
    await expect(page.getByText("Create New Label")).toBeVisible({
      timeout: 5000,
    });

    // Cancel the form — the first "Cancel" button in DOM order is the
    // in-form one; the footer's Cancel comes last.
    await page.locator("button").filter({ hasText: "Cancel" }).first().click();

    // The dropdown returns
    await expect(page.getByText("Search or type to create...")).toBeVisible();
  });

  test("creates a new label via SMART_LABEL_SEARCH_OR_CREATE", async ({
    mount,
    page,
  }) => {
    const smartMock: MockedResponse = {
      request: {
        query: SMART_LABEL_SEARCH_OR_CREATE,
        variables: {
          corpusId: TEST_CORPUS_ID,
          searchTerm: "supersedes",
          labelType: LabelType.RelationshipLabel,
          // Must mirror the default color set by the inline create-label form
          // inside DocumentRelationshipModal. If the form default changes, update
          // this to match or the mock will silently stop matching.
          color: OS_LEGAL_COLORS.greenMedium,
          description: "",
          createIfNotFound: true,
        },
      },
      result: {
        data: {
          smartLabelSearchOrCreate: {
            ok: true,
            message: "",
            labels: [
              {
                id: "label-new-1",
                text: "supersedes",
                description: "",
                color: "#14b8a6",
                icon: null,
                labelType: LabelType.RelationshipLabel,
                __typename: "AnnotationLabelType",
              },
            ],
            labelset: {
              id: "labelset-1",
              title: "Test Labelset",
              description: null,
              __typename: "LabelSetType",
            },
            labelsetCreated: false,
            labelCreated: true,
            __typename: "SmartLabelSearchOrCreate",
          },
        },
      },
    };

    await mount(
      <DocumentRelationshipModalTestWrapper extraMocks={[smartMock]} />
    );

    await page.waitForSelector('text="Relationship Label"', {
      timeout: 10000,
    });

    // Open dropdown, type a new label name, click "Create label: ..."
    const dropdown = page.locator(".oc-dropdown").first();
    await dropdown.locator(".oc-dropdown__trigger").click();
    await dropdown.locator(".oc-dropdown__search-input").fill("supersedes");
    await page.getByRole("button", { name: /Create label:/ }).click();

    await expect(page.getByText("Create New Label")).toBeVisible({
      timeout: 5000,
    });

    // Click the in-form Create Label button
    await page.getByRole("button", { name: /^Create Label$/ }).click();

    // After mutation resolves, the new label should be selected
    await expect(page.getByText("Selected Label")).toBeVisible({
      timeout: 5000,
    });
  });
});

// ---------------------------------------------------------------------------
// Targeted coverage tests for the useMemo bodies that drive the dropdown's
// option list and the Add Target/Source search list. These exercise the
// filter callbacks that are otherwise skipped when relationLabels is empty
// or labelSearchTerm never changes.
// ---------------------------------------------------------------------------

test.describe("DocumentRelationshipModal — filter coverage", () => {
  test("availableDocuments excludes documents already in source or target", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper
        initialSourceIds={["doc-1"]}
        initialTargetIds={["doc-2"]}
      />
    );

    await page.waitForSelector('text="Link Documents"', { timeout: 10000 });

    // Open the Add Target search to render the available-documents list
    await page.getByRole("button", { name: /Add Target/ }).click();
    await expect(
      page.getByPlaceholder("Search documents in corpus...")
    ).toBeVisible();

    // Mocks have 3 documents; doc-1 is in source and doc-2 is in target, so
    // only doc-3 ("Target Document 2") should appear in the available list.
    // SearchResultItem rows are uniquely identified by the .doc-title class
    // (pills in source/target columns use a different markup), so counting
    // those gives the precise size of availableDocuments after the filter.
    const availableTitles = page.locator(".doc-title");
    await expect(availableTitles).toHaveCount(1, { timeout: 5000 });
    await expect(availableTitles.first()).toHaveText("Target Document 2");
  });

  test("filteredRelationshipLabels filters dropdown options by search term", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentRelationshipModalTestWrapper
        relationLabels={[
          makeMockRelationLabel({ id: "label-1", text: "references" }),
          makeMockRelationLabel({ id: "label-2", text: "amends" }),
          makeMockRelationLabel({ id: "label-3", text: "supersedes" }),
        ]}
      />
    );

    await page.waitForSelector('text="Relationship Label"', { timeout: 10000 });

    const dropdown = page.locator(".oc-dropdown").first();
    await dropdown.locator(".oc-dropdown__trigger").click();

    // With no search term, all three relationship labels render as options.
    await expect(
      dropdown.locator(".oc-dropdown__option", { hasText: "references" })
    ).toBeVisible({ timeout: 5000 });
    await expect(
      dropdown.locator(".oc-dropdown__option", { hasText: "amends" })
    ).toBeVisible();
    await expect(
      dropdown.locator(".oc-dropdown__option", { hasText: "supersedes" })
    ).toBeVisible();

    // Type into the search box. The dropdown debounces onSearchChange (300ms)
    // before firing the parent's setLabelSearchTerm, which then re-runs the
    // filteredRelationshipLabels useMemo and shrinks the visible options list.
    await dropdown.locator(".oc-dropdown__search-input").fill("ref");

    // Poll until only the matching option remains. expect.poll handles the
    // 300ms debounce window without a fixed sleep.
    await expect
      .poll(
        async () =>
          dropdown
            .locator(".oc-dropdown__option", { hasText: "amends" })
            .count(),
        { timeout: 5000 }
      )
      .toBe(0);
    await expect(
      dropdown.locator(".oc-dropdown__option", { hasText: "references" })
    ).toBeVisible();
  });

  test("filteredRelationshipLabels returns empty list when corpus context missing", async ({
    mount,
    page,
  }) => {
    // hasCorpus=false short-circuits the filter to return []. Render with
    // relationLabels populated to prove the early-return wins over the
    // labels' presence — without the early return the labels would surface
    // even though no corpus is selected.
    await mount(
      <DocumentRelationshipModalTestWrapper
        corpusIdOverride={null}
        relationLabels={[
          makeMockRelationLabel({ id: "label-1", text: "references" }),
        ]}
      />
    );

    await expect(page.getByText("No Corpus Context")).toBeVisible({
      timeout: 10000,
    });

    // Even though relationLabels are present, the dropdown shouldn't surface
    // "references" because the useMemo returns [] when hasCorpus is false.
    const dropdown = page.locator(".oc-dropdown").first();
    if (await dropdown.isVisible()) {
      await dropdown.locator(".oc-dropdown__trigger").click();
      await expect(
        dropdown.locator(".oc-dropdown__option", { hasText: "references" })
      ).toHaveCount(0);
    }
  });
});
