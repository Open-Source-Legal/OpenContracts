// Playwright Component Test for BatchRunCorpusActionModal
// Tests the confirmation modal that batch-runs an agent corpus action across
// every eligible document in the corpus.
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { BatchRunCorpusActionModal } from "../src/components/corpuses/BatchRunCorpusActionModal";
import { START_CORPUS_ACTION_BATCH_RUN } from "../src/graphql/mutations";
import { docScreenshot } from "./utils/docScreenshot";

const ACTION_ID = "Q29ycHVzQWN0aW9uVHlwZTox";
const ACTION_NAME = "Auto-Summarize Documents";

const successMock = {
  request: {
    query: START_CORPUS_ACTION_BATCH_RUN,
    variables: { corpusActionId: ACTION_ID },
  },
  result: {
    data: {
      startCorpusActionBatchRun: {
        ok: true,
        message: "Queued 5 document(s) for processing; skipped 2 already-run.",
        queuedCount: 5,
        skippedAlreadyRunCount: 2,
        totalActiveDocuments: 7,
        executions: [
          {
            id: "exec-1",
            status: "QUEUED",
            document: { id: "doc-1", title: "Contract.pdf" },
          },
        ],
      },
    },
  },
};

const noEligibleMock = {
  request: {
    query: START_CORPUS_ACTION_BATCH_RUN,
    variables: { corpusActionId: ACTION_ID },
  },
  result: {
    data: {
      startCorpusActionBatchRun: {
        ok: true,
        message:
          "No eligible documents — every active document in this corpus has already been run through this action (3 skipped).",
        queuedCount: 0,
        skippedAlreadyRunCount: 3,
        totalActiveDocuments: 3,
        executions: [],
      },
    },
  },
};

const failureMock = {
  request: {
    query: START_CORPUS_ACTION_BATCH_RUN,
    variables: { corpusActionId: ACTION_ID },
  },
  result: {
    data: {
      startCorpusActionBatchRun: {
        ok: false,
        message: "This action is disabled. Re-enable it before batch-running.",
        queuedCount: 0,
        skippedAlreadyRunCount: 0,
        totalActiveDocuments: 0,
        executions: [],
      },
    },
  },
};

test.describe("BatchRunCorpusActionModal - Rendering", () => {
  test("shows confirmation copy explaining skip-already-run semantics", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <BatchRunCorpusActionModal
          open={true}
          actionId={ACTION_ID}
          actionName={ACTION_NAME}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    await expect(page.locator("text=Run on every document")).toBeVisible();
    await expect(page.locator(`text=${ACTION_NAME}`)).toBeVisible();
    await expect(
      page.locator("text=will run against every active document in this corpus")
    ).toBeVisible();
    await expect(
      page.locator("text=Failed runs will be retried")
    ).toBeVisible();
    await expect(
      page.locator("text=This dispatches one agent run per document")
    ).toBeVisible();

    await expect(page.locator('button:has-text("Cancel")')).toBeVisible();
    await expect(
      page.locator('button:has-text("Run on all documents")')
    ).toBeVisible();

    await docScreenshot(page, "corpus-actions--batch-run-modal--confirmation");

    await component.unmount();
  });

  test("calls onClose when Cancel is clicked", async ({ mount, page }) => {
    let closeCalled = false;

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <BatchRunCorpusActionModal
          open={true}
          actionId={ACTION_ID}
          actionName={ACTION_NAME}
          onClose={() => {
            closeCalled = true;
          }}
        />
      </MockedProvider>
    );

    await page.locator('button:has-text("Cancel")').click();
    expect(closeCalled).toBe(true);

    await component.unmount();
  });
});

test.describe("BatchRunCorpusActionModal - Behavior", () => {
  test("dispatches batch-run mutation and closes on success", async ({
    mount,
    page,
  }) => {
    let closeCalled = false;
    let queuedCalled = false;

    const component = await mount(
      <MockedProvider mocks={[successMock]} addTypename={false}>
        <BatchRunCorpusActionModal
          open={true}
          actionId={ACTION_ID}
          actionName={ACTION_NAME}
          onClose={() => {
            closeCalled = true;
          }}
          onQueued={() => {
            queuedCalled = true;
          }}
        />
      </MockedProvider>
    );

    await page.locator('button:has-text("Run on all documents")').click();
    // Apollo cache settle + onClose firing inside the mutation .then
    await page.waitForTimeout(1000);

    expect(queuedCalled).toBe(true);
    expect(closeCalled).toBe(true);

    await component.unmount();
  });

  test("keeps the modal open and surfaces the message when server reports ok=false", async ({
    mount,
    page,
  }) => {
    let closeCalled = false;

    const component = await mount(
      <MockedProvider mocks={[failureMock]} addTypename={false}>
        <BatchRunCorpusActionModal
          open={true}
          actionId={ACTION_ID}
          actionName={ACTION_NAME}
          onClose={() => {
            closeCalled = true;
          }}
        />
      </MockedProvider>
    );

    await page.locator('button:has-text("Run on all documents")').click();
    await page.waitForTimeout(1000);

    // Server reports failure → onClose is NOT called; modal stays open so the
    // user can see the toast and dismiss it themselves.
    expect(closeCalled).toBe(false);
    await expect(page.locator("text=Run on every document")).toBeVisible();

    await component.unmount();
  });

  test("treats queuedCount=0 with ok=true as success and closes the modal", async ({
    mount,
    page,
  }) => {
    let closeCalled = false;

    const component = await mount(
      <MockedProvider mocks={[noEligibleMock]} addTypename={false}>
        <BatchRunCorpusActionModal
          open={true}
          actionId={ACTION_ID}
          actionName={ACTION_NAME}
          onClose={() => {
            closeCalled = true;
          }}
        />
      </MockedProvider>
    );

    await page.locator('button:has-text("Run on all documents")').click();
    await page.waitForTimeout(1000);

    expect(closeCalled).toBe(true);

    await component.unmount();
  });
});
