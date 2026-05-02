import React from "react";
import type { Page, Route } from "@playwright/test";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { CorpusDescriptionEditorTestWrapper } from "./CorpusDescriptionEditorTestWrapper";
import { GET_CORPUS_WITH_HISTORY } from "../src/graphql/queries";
import { UPDATE_CORPUS_DESCRIPTION } from "../src/graphql/mutations";
import { docScreenshot } from "./utils/docScreenshot";

const TEST_CORPUS_ID = "corpus-cde-1";
const MD_URL = "http://localhost/test-md/initial.md";
const INITIAL_MD = "# Initial Description\n\nHello world.";

/* -------------------------------------------------------------------------- */
/* Fixtures                                                                    */
/* -------------------------------------------------------------------------- */

const baseRevision = (overrides: Partial<any> = {}) => ({
  id: "rev-1",
  version: 1,
  author: { id: "u1", email: "alice@example.com" },
  created: "2026-01-01T00:00:00Z",
  diff: "+ Initial",
  snapshot: INITIAL_MD,
  ...overrides,
});

const buildCorpusMock = (overrides: Partial<any> = {}): MockedResponse => ({
  request: {
    query: GET_CORPUS_WITH_HISTORY,
    variables: { id: TEST_CORPUS_ID },
  },
  result: {
    data: {
      corpus: {
        id: TEST_CORPUS_ID,
        slug: "test-corpus",
        title: "Test Corpus",
        description: "Short description",
        mdDescription: MD_URL,
        icon: null,
        created: "2026-01-01T00:00:00Z",
        modified: "2026-01-02T00:00:00Z",
        isPublic: false,
        myPermissions: ["READ", "UPDATE"],
        documentCount: 0,
        license: null,
        licenseLink: null,
        creator: {
          id: "u1",
          email: "alice@example.com",
          slug: "alice",
        },
        labelSet: null,
        descriptionRevisions: [baseRevision()],
        ...overrides,
      },
    },
  },
});

const buildCorpusMockNoMd = (): MockedResponse => ({
  request: {
    query: GET_CORPUS_WITH_HISTORY,
    variables: { id: TEST_CORPUS_ID },
  },
  result: {
    data: {
      corpus: {
        id: TEST_CORPUS_ID,
        slug: "test-corpus",
        title: "Empty Corpus",
        description: "",
        mdDescription: null,
        icon: null,
        created: "2026-01-01T00:00:00Z",
        modified: "2026-01-01T00:00:00Z",
        isPublic: false,
        myPermissions: ["READ", "UPDATE"],
        documentCount: 0,
        license: null,
        licenseLink: null,
        creator: { id: "u1", email: "alice@example.com", slug: "alice" },
        labelSet: null,
        descriptionRevisions: [],
      },
    },
  },
});

const setupMdRoute = async (page: Page, body: string = INITIAL_MD) => {
  await page.route("**/test-md/**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/markdown",
      body,
    });
  });
};

/* -------------------------------------------------------------------------- */
/* Tests                                                                       */
/* -------------------------------------------------------------------------- */

test.describe("CorpusDescriptionEditor", () => {
  test("renders nothing when isOpen is false (no query fired)", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);
    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[]}
        corpusId={TEST_CORPUS_ID}
        isOpen={false}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).not.toBeVisible();

    await component.unmount();
  });

  test("loads markdown content into editor", async ({ mount, page }) => {
    await setupMdRoute(page);

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock()]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    // Header
    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });

    // Title from query
    await expect(page.getByText("Test Corpus", { exact: true })).toBeVisible();

    // Editor should have the fetched markdown content
    const textarea = page.locator(
      'textarea[placeholder="Write your corpus description in Markdown..."]'
    );
    await expect(textarea).toHaveValue(INITIAL_MD, { timeout: 10000 });

    await docScreenshot(page, "corpus--description-editor--loaded");

    await component.unmount();
  });

  test("shows empty editor when corpus has no mdDescription", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMockNoMd()]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });

    const textarea = page.locator(
      'textarea[placeholder="Write your corpus description in Markdown..."]'
    );
    await expect(textarea).toHaveValue("", { timeout: 10000 });

    // Save button is disabled when there are no changes
    await expect(
      page.getByRole("button", { name: /Save Changes/ })
    ).toBeDisabled();

    await component.unmount();
  });

  test("editing content surfaces 'Unsaved changes' indicator", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock()]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    const textarea = page.locator(
      'textarea[placeholder="Write your corpus description in Markdown..."]'
    );
    await expect(textarea).toHaveValue(INITIAL_MD, { timeout: 20000 });

    await textarea.fill(INITIAL_MD + "\n\nNew paragraph.");

    await expect(page.getByText("Unsaved changes")).toBeVisible({
      timeout: 5000,
    });

    // Save button is no longer disabled
    await expect(
      page.getByRole("button", { name: /Save Changes/ })
    ).toBeEnabled();

    await component.unmount();
  });

  test("toggling history panel reveals the Version History header", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock()]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });

    // Initially history is hidden
    await expect(page.getByText("Version History")).not.toBeVisible();

    // Click Show History
    await page
      .getByRole("button", { name: /Show History/, exact: false })
      .click();

    await expect(page.getByText("Version History")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByTestId("version-number")).toContainText("Version 1");

    // Hide again
    await page
      .getByRole("button", { name: /Hide History/, exact: false })
      .click();
    await expect(page.getByText("Version History")).not.toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("clicking a version shows snapshot and reapply / edit-from controls", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock()]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });

    await page
      .getByRole("button", { name: /Show History/, exact: false })
      .click();

    const versionNumber = page.getByTestId("version-number");
    await expect(versionNumber).toContainText("Version 1", { timeout: 5000 });

    // Click the version row to expand details
    await versionNumber.first().click();

    await expect(page.getByText("Version 1 snapshot")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByRole("button", { name: /Reapply as New Version/ })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Edit from This Version/ })
    ).toBeVisible();

    await component.unmount();
  });

  test("save mutation persists edited content", async ({ mount, page }) => {
    await setupMdRoute(page);
    let onUpdateCalled = false;

    const newContent = INITIAL_MD + "\n\nAdditional content.";
    const updateMock: MockedResponse = {
      request: {
        query: UPDATE_CORPUS_DESCRIPTION,
        variables: {
          corpusId: TEST_CORPUS_ID,
          newContent,
        },
      },
      result: {
        data: {
          updateCorpusDescription: {
            ok: true,
            message: "Saved",
            version: 2,
            obj: {
              id: TEST_CORPUS_ID,
              title: "Test Corpus",
              description: "Short description",
              mdDescription: MD_URL,
              descriptionRevisions: [
                baseRevision(),
                {
                  id: "rev-2",
                  version: 2,
                  author: { id: "u1", email: "alice@example.com" },
                  created: "2026-01-03T00:00:00Z",
                  diff: "+ Additional",
                  snapshot: newContent,
                },
              ],
            },
          },
        },
      },
    };

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[
          buildCorpusMock(),
          updateMock,
          // refetch after mutation
          buildCorpusMock({
            descriptionRevisions: [
              baseRevision(),
              {
                id: "rev-2",
                version: 2,
                author: { id: "u1", email: "alice@example.com" },
                created: "2026-01-03T00:00:00Z",
                diff: "+ Additional",
                snapshot: newContent,
              },
            ],
          }),
        ]}
        corpusId={TEST_CORPUS_ID}
        onUpdate={() => {
          onUpdateCalled = true;
        }}
      />
    );

    const textarea = page.locator(
      'textarea[placeholder="Write your corpus description in Markdown..."]'
    );
    await expect(textarea).toHaveValue(INITIAL_MD, { timeout: 20000 });

    await textarea.fill(newContent);
    await expect(page.getByText("Unsaved changes")).toBeVisible({
      timeout: 5000,
    });

    await page.getByRole("button", { name: /Save Changes/ }).click();

    await expect.poll(() => onUpdateCalled, { timeout: 10000 }).toBe(true);
    // Toast confirms version
    await expect(
      page.getByText(/Description updated! Now at version 2/)
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("reapplying a version triggers update mutation", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const reapplyMock: MockedResponse = {
      request: {
        query: UPDATE_CORPUS_DESCRIPTION,
        variables: {
          corpusId: TEST_CORPUS_ID,
          newContent: INITIAL_MD,
        },
      },
      result: {
        data: {
          updateCorpusDescription: {
            ok: true,
            message: "Reapplied",
            version: 3,
            obj: {
              id: TEST_CORPUS_ID,
              title: "Test Corpus",
              description: "Short description",
              mdDescription: MD_URL,
              descriptionRevisions: [baseRevision()],
            },
          },
        },
      },
    };

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock(), reapplyMock, buildCorpusMock()]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });

    await page
      .getByRole("button", { name: /Show History/, exact: false })
      .click();
    const versionNumber = page.getByTestId("version-number");
    await expect(versionNumber).toContainText("Version 1", { timeout: 5000 });
    await versionNumber.first().click();

    await page.getByRole("button", { name: /Reapply as New Version/ }).click();

    await expect(
      page.getByText(/Version 1 reapplied as new version 3/)
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("close button calls onClose when there are no unsaved changes", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);
    let onCloseCalled = false;

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock()]}
        corpusId={TEST_CORPUS_ID}
        onClose={() => {
          onCloseCalled = true;
        }}
      />
    );

    const textarea = page.locator(
      'textarea[placeholder="Write your corpus description in Markdown..."]'
    );
    await expect(textarea).toHaveValue(INITIAL_MD, { timeout: 20000 });

    // Close button in the action bar
    await page.getByRole("button", { name: /^Close/ }).click();

    await expect.poll(() => onCloseCalled, { timeout: 5000 }).toBe(true);

    await component.unmount();
  });

  test("edit-from-version pre-fills editor and shows badge", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock()]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });

    await page
      .getByRole("button", { name: /Show History/, exact: false })
      .click();
    const versionNumber = page.getByTestId("version-number");
    await expect(versionNumber).toContainText("Version 1", { timeout: 5000 });
    await versionNumber.first().click();

    await page.getByRole("button", { name: /Edit from This Version/ }).click();

    // Editing-from badge should appear in the header
    await expect(page.getByText(/Editing from v1/)).toBeVisible({
      timeout: 5000,
    });

    // The "Cancel Version Edit" button appears
    await expect(
      page.getByRole("button", { name: /Cancel Version Edit/ })
    ).toBeVisible();

    await component.unmount();
  });

  test("save mutation failure (ok: false) shows toast error", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const newContent = INITIAL_MD + "\n\nExtra.";
    const failingSaveMock: MockedResponse = {
      request: {
        query: UPDATE_CORPUS_DESCRIPTION,
        variables: {
          corpusId: TEST_CORPUS_ID,
          newContent,
        },
      },
      result: {
        data: {
          updateCorpusDescription: {
            ok: false,
            message: "Validation failed on server",
            version: null,
            obj: null,
          },
        },
      },
    };

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock(), failingSaveMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    const textarea = page.locator(
      'textarea[placeholder="Write your corpus description in Markdown..."]'
    );
    await expect(textarea).toHaveValue(INITIAL_MD, { timeout: 20000 });

    await textarea.fill(newContent);

    await page.getByRole("button", { name: /Save Changes/ }).click();

    await expect(page.getByText("Validation failed on server")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("save mutation network error surfaces generic error toast", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const newContent = INITIAL_MD + "\n\nExtra.";
    const networkErrorMock: MockedResponse = {
      request: {
        query: UPDATE_CORPUS_DESCRIPTION,
        variables: {
          corpusId: TEST_CORPUS_ID,
          newContent,
        },
      },
      error: new Error("Boom"),
    };

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock(), networkErrorMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    const textarea = page.locator(
      'textarea[placeholder="Write your corpus description in Markdown..."]'
    );
    await expect(textarea).toHaveValue(INITIAL_MD, { timeout: 20000 });

    await textarea.fill(newContent);
    await page.getByRole("button", { name: /Save Changes/ }).click();

    await expect(
      page.getByText("Failed to update corpus description")
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("reapplying a version without a snapshot surfaces an error toast", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[
          buildCorpusMock({
            descriptionRevisions: [
              baseRevision({
                id: "rev-empty",
                version: 1,
                snapshot: null,
              }),
            ],
          }),
        ]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });

    await page
      .getByRole("button", { name: /Show History/, exact: false })
      .click();

    const versionNumber = page.getByTestId("version-number");
    await expect(versionNumber).toContainText("Version 1", { timeout: 5000 });
    await versionNumber.first().click();

    // No Reapply button is shown when snapshot is null — the error ErrorMessage
    // renders instead.
    await expect(
      page.getByText("This version does not have a snapshot available")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("clicking the same version twice collapses the details", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock()]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });

    await page
      .getByRole("button", { name: /Show History/, exact: false })
      .click();

    const versionNumber = page.getByTestId("version-number");
    await expect(versionNumber).toContainText("Version 1", { timeout: 5000 });

    // Expand
    await versionNumber.first().click();
    await expect(page.getByText("Version 1 snapshot")).toBeVisible({
      timeout: 5000,
    });

    // Collapse by clicking again
    await versionNumber.first().click();
    await expect(page.getByText("Version 1 snapshot")).not.toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("Cancel Version Edit resets content and hides the badge", async ({
    mount,
    page,
  }) => {
    await setupMdRoute(page);

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[
          buildCorpusMock({
            descriptionRevisions: [
              baseRevision({
                id: "rev-1",
                version: 1,
                snapshot: "# Much older content",
              }),
              baseRevision({
                id: "rev-2",
                version: 2,
                snapshot: INITIAL_MD,
              }),
            ],
          }),
        ]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    const textarea = page.locator(
      'textarea[placeholder="Write your corpus description in Markdown..."]'
    );
    await expect(textarea).toHaveValue(INITIAL_MD, { timeout: 20000 });

    await page
      .getByRole("button", { name: /Show History/, exact: false })
      .click();

    // Expand the OLDER version (v1) — not the current one
    const versionRows = page.getByTestId("version-number");
    const olderRow = versionRows.filter({ hasText: "Version 1" }).first();
    await olderRow.click();

    await page.getByRole("button", { name: /Edit from This Version/ }).click();

    await expect(page.getByText(/Editing from v1/)).toBeVisible({
      timeout: 5000,
    });

    // Click Cancel Version Edit — editor reverts to current content, badge gone
    await page.getByRole("button", { name: /Cancel Version Edit/ }).click();

    await expect(page.getByText(/Editing from v1/)).not.toBeVisible({
      timeout: 5000,
    });
    await expect(textarea).toHaveValue(INITIAL_MD, { timeout: 5000 });

    await component.unmount();
  });

  test("fetching mdDescription URL failure falls back to empty editor", async ({
    mount,
    page,
  }) => {
    // Abort the network request so the fetch promise rejects and the
    // component's .catch() branch (setCurrentContent("")) runs.
    await page.route("**/test-md/**", async (route: Route) => {
      await route.abort("failed");
    });

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[buildCorpusMock()]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });

    const textarea = page.locator(
      'textarea[placeholder="Write your corpus description in Markdown..."]'
    );
    await expect(textarea).toBeVisible({ timeout: 5000 });
    // The catch branch resets content to empty string; pin that contract.
    await expect(textarea).toHaveValue("", { timeout: 5000 });

    await component.unmount();
  });

  test("version count label pluralizes correctly", async ({ mount, page }) => {
    await setupMdRoute(page);

    const component = await mount(
      <CorpusDescriptionEditorTestWrapper
        mocks={[
          buildCorpusMock({
            descriptionRevisions: [
              baseRevision({ id: "rev-a", version: 1 }),
              baseRevision({ id: "rev-b", version: 2 }),
              baseRevision({ id: "rev-c", version: 3 }),
            ],
          }),
        ]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Edit Corpus Description")).toBeVisible({
      timeout: 20000,
    });
    await page
      .getByRole("button", { name: /Show History/, exact: false })
      .click();

    // Count line says "3 versions" (plural)
    await expect(page.getByText(/3 versions/)).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});
