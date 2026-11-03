import { test, expect } from "./utils/coverage";
import { DocumentVersionSelectorTestWrapper } from "./DocumentVersionSelectorTestWrapper";
import { DocumentVersionSelector } from "../src/components/documents/DocumentVersionSelector";
import { GET_CORPUS_VERSIONS } from "../src/graphql/queries";

const DOC_ID = "RG9jdW1lbnRUeXBlOjE=";
const CORPUS_ID = "Q29ycHVzVHlwZTox";

const singleVersionMock = {
  request: {
    query: GET_CORPUS_VERSIONS,
    variables: { documentId: DOC_ID, corpusId: CORPUS_ID },
  },
  result: {
    data: {
      document: {
        id: DOC_ID,
        corpusVersions: [
          {
            versionNumber: 1,
            documentId: DOC_ID,
            documentSlug: "test-doc",
            created: "2026-01-01T00:00:00Z",
            isCurrent: true,
          },
        ],
      },
    },
  },
};

const multiVersionMock = {
  request: {
    query: GET_CORPUS_VERSIONS,
    variables: { documentId: DOC_ID, corpusId: CORPUS_ID },
  },
  result: {
    data: {
      document: {
        id: DOC_ID,
        corpusVersions: [
          {
            versionNumber: 1,
            documentId: "RG9jdW1lbnRUeXBlOjE=",
            documentSlug: "test-doc-v1",
            created: "2026-01-01T00:00:00Z",
            isCurrent: false,
          },
          {
            versionNumber: 2,
            documentId: "RG9jdW1lbnRUeXBlOjI=",
            documentSlug: "test-doc-v2",
            created: "2026-01-15T00:00:00Z",
            isCurrent: false,
          },
          {
            versionNumber: 3,
            documentId: "RG9jdW1lbnRUeXBlOjM=",
            documentSlug: "test-doc-v3",
            created: "2026-02-01T00:00:00Z",
            isCurrent: true,
          },
        ],
      },
    },
  },
};

test.describe("DocumentVersionSelector", () => {
  test("switches per-version slugs and returns from a pinned citation to the latest version", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[multiVersionMock]}
        initialRoute="/d/testuser/test-corpus/test-doc-v1?v=1&tab=annotations"
      >
        <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
      </DocumentVersionSelectorTestWrapper>
    );
    await page
      .getByRole("button", { name: /click to switch versions/ })
      .click();
    await page.getByRole("option", { name: /Version 3/ }).click();
    await expect(page.getByLabel("Current route")).toHaveText(
      "/d/testuser/test-corpus/test-doc-v3?tab=annotations"
    );
    await page
      .getByRole("button", { name: /click to switch versions/ })
      .click();
    await page.getByRole("option", { name: /Version 2/ }).click();
    await expect(page.getByLabel("Current route")).toHaveText(
      "/d/testuser/test-corpus/test-doc-v2?tab=annotations&v=2"
    );
  });

  test("renders non-interactive pill for single-version document", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[singleVersionMock, singleVersionMock]}
      >
        <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
      </DocumentVersionSelectorTestWrapper>
    );

    // Wait for the pill to render with "v1"
    await expect(page.getByText("v1")).toBeVisible();

    // No listbox should exist (no dropdown for single version)
    await expect(page.getByRole("listbox")).not.toBeVisible();

    // The pill should NOT have aria-haspopup (single-version path renders without it)
    const pill = page.getByText("v1");
    await expect(pill).not.toHaveAttribute("aria-haspopup");
  });

  test("renders interactive pill with version count for multi-version document", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[multiVersionMock, multiVersionMock]}
      >
        <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
      </DocumentVersionSelectorTestWrapper>
    );

    // Wait for the current version number to appear
    await expect(page.getByText("v3")).toBeVisible();

    // Wait for the version count display
    await expect(page.getByText("/ 3")).toBeVisible();

    // The pill button should have aria-haspopup="listbox"
    const pill = page.locator("button[aria-haspopup='listbox']");
    await expect(pill).toBeVisible();
  });

  test("opens dropdown showing all versions when clicked", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[multiVersionMock, multiVersionMock]}
      >
        <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
      </DocumentVersionSelectorTestWrapper>
    );

    // Wait for the pill to appear
    const pill = page.locator("button[aria-haspopup='listbox']");
    await expect(pill).toBeVisible();

    // Click to open dropdown
    await pill.click();

    // Verify the listbox appears
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();

    // Verify 3 options exist
    const options = page.getByRole("option");
    await expect(options).toHaveCount(3);

    // Verify version labels are visible
    await expect(page.getByText("Version 1")).toBeVisible();
    await expect(page.getByText("Version 2")).toBeVisible();
    await expect(page.getByText("Version 3")).toBeVisible();

    // Verify the "Latest" tag is shown for the current version
    await expect(page.getByText("Latest")).toBeVisible();
  });

  test("closes dropdown on Escape key", async ({ mount, page }) => {
    const component = await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[multiVersionMock, multiVersionMock]}
      >
        <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
      </DocumentVersionSelectorTestWrapper>
    );

    // Wait for the pill to appear and click it
    const pill = page.locator("button[aria-haspopup='listbox']");
    await expect(pill).toBeVisible();
    await pill.click();

    // Verify the listbox is visible
    await expect(page.getByRole("listbox")).toBeVisible();

    // Press Escape
    await page.keyboard.press("Escape");

    // Verify the listbox is no longer visible
    await expect(page.getByRole("listbox")).not.toBeVisible();
  });

  test("closes dropdown when clicking outside", async ({ mount, page }) => {
    const component = await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[multiVersionMock, multiVersionMock]}
      >
        <div>
          <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
          <div data-testid="outside" style={{ padding: "20px" }}>
            Outside element
          </div>
        </div>
      </DocumentVersionSelectorTestWrapper>
    );

    // Wait for the pill to appear and click it
    const pill = page.locator("button[aria-haspopup='listbox']");
    await expect(pill).toBeVisible();
    await pill.click();

    // Verify the listbox is visible
    await expect(page.getByRole("listbox")).toBeVisible();

    // Click outside element
    await page.getByTestId("outside").click();

    // Verify the listbox is no longer visible
    await expect(page.getByRole("listbox")).not.toBeVisible();
  });

  test("navigates options with arrow keys", async ({ mount, page }) => {
    const component = await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[multiVersionMock, multiVersionMock]}
      >
        <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
      </DocumentVersionSelectorTestWrapper>
    );

    // Wait for the pill to appear and click to open
    const pill = page.locator("button[aria-haspopup='listbox']");
    await expect(pill).toBeVisible();
    await pill.click();

    // Listbox should open with the current version (v3) focused.
    // Sorted descending: [v3, v2, v1] → index 0 = v3
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();

    // The pill should reference the active descendant
    await expect(pill).toHaveAttribute(
      "aria-activedescendant",
      "version-option-3"
    );

    // Press ArrowDown to move focus to v2
    await page.keyboard.press("ArrowDown");
    await expect(pill).toHaveAttribute(
      "aria-activedescendant",
      "version-option-2"
    );

    // Press ArrowDown again to move to v1
    await page.keyboard.press("ArrowDown");
    await expect(pill).toHaveAttribute(
      "aria-activedescendant",
      "version-option-1"
    );

    // ArrowDown at the end should stay on v1
    await page.keyboard.press("ArrowDown");
    await expect(pill).toHaveAttribute(
      "aria-activedescendant",
      "version-option-1"
    );

    // ArrowUp should move back to v2
    await page.keyboard.press("ArrowUp");
    await expect(pill).toHaveAttribute(
      "aria-activedescendant",
      "version-option-2"
    );
  });

  test("Home and End keys jump to first and last options", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[multiVersionMock, multiVersionMock]}
      >
        <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
      </DocumentVersionSelectorTestWrapper>
    );

    const pill = page.locator("button[aria-haspopup='listbox']");
    await expect(pill).toBeVisible();
    await pill.click();
    await expect(page.getByRole("listbox")).toBeVisible();

    // End key should focus the last option (v1 at index 2)
    await page.keyboard.press("End");
    await expect(pill).toHaveAttribute(
      "aria-activedescendant",
      "version-option-1"
    );

    // Home key should focus the first option (v3 at index 0)
    await page.keyboard.press("Home");
    await expect(pill).toHaveAttribute(
      "aria-activedescendant",
      "version-option-3"
    );
  });

  test("Enter key selects the focused option", async ({ mount, page }) => {
    const component = await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[multiVersionMock, multiVersionMock]}
      >
        <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
      </DocumentVersionSelectorTestWrapper>
    );

    const pill = page.locator("button[aria-haspopup='listbox']");
    await expect(pill).toBeVisible();
    await pill.click();
    await expect(page.getByRole("listbox")).toBeVisible();

    // Navigate down to v2 and press Enter
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");

    // Dropdown should close after selection
    await expect(page.getByRole("listbox")).not.toBeVisible();
  });

  test("Space key selects the focused option", async ({ mount, page }) => {
    const component = await mount(
      <DocumentVersionSelectorTestWrapper
        mocks={[multiVersionMock, multiVersionMock]}
      >
        <DocumentVersionSelector documentId={DOC_ID} corpusId={CORPUS_ID} />
      </DocumentVersionSelectorTestWrapper>
    );

    const pill = page.locator("button[aria-haspopup='listbox']");
    await expect(pill).toBeVisible();
    await pill.click();
    await expect(page.getByRole("listbox")).toBeVisible();

    // Navigate down to v2 and press Space
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press(" ");

    // Dropdown should close after selection
    await expect(page.getByRole("listbox")).not.toBeVisible();
  });
});
