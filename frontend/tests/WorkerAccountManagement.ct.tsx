import React from "react";
import { test, expect } from "./utils/coverage";
import { gql } from "@apollo/client";
import { WorkerAccountManagementTestWrapper } from "./WorkerAccountManagementTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

// Must match the query in WorkerAccountManagement.tsx exactly
const GET_WORKER_ACCOUNTS = gql`
  query GetWorkerAccounts {
    workerAccounts {
      id
      name
      description
      isActive
      tokenCount
      creatorName
      created
    }
  }
`;

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const mockWorkerAccounts = [
  {
    id: 1,
    name: "Pipeline Uploader",
    description: "Automated document ingestion service",
    isActive: true,
    tokenCount: 3,
    creatorName: "admin",
    created: "2025-11-01T10:00:00Z",
  },
  {
    id: 2,
    name: "CI Integration Bot",
    description: "Continuous integration worker for nightly imports",
    isActive: true,
    tokenCount: 1,
    creatorName: "admin",
    created: "2025-12-15T14:30:00Z",
  },
  {
    id: 3,
    name: "Legacy Importer",
    description: null,
    isActive: false,
    tokenCount: 0,
    creatorName: "jdoe",
    created: "2025-06-20T08:00:00Z",
  },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("WorkerAccountManagement", () => {
  test("renders worker account list", async ({ mount, page }) => {
    const mocks = [
      {
        request: { query: GET_WORKER_ACCOUNTS },
        variableMatcher: () => true,
        result: {
          data: {
            workerAccounts: mockWorkerAccounts,
          },
        },
      },
    ];

    await mount(<WorkerAccountManagementTestWrapper mocks={mocks} />);

    // Wait for the query to resolve and the table to render
    await expect(page.getByText("Worker Accounts").first()).toBeVisible({
      timeout: 10000,
    });

    // Verify all three accounts are shown
    await expect(page.getByText("Pipeline Uploader")).toBeVisible();
    await expect(page.getByText("CI Integration Bot")).toBeVisible();
    await expect(page.getByText("Legacy Importer")).toBeVisible();

    // Verify status badges render
    await expect(page.getByText("Active").first()).toBeVisible();
    await expect(page.getByText("Inactive")).toBeVisible();

    // Verify creator names
    await expect(page.getByText("admin").first()).toBeVisible();
    await expect(page.getByText("jdoe")).toBeVisible();

    // Verify action buttons
    await expect(page.getByText("Deactivate").first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Activate", exact: true })
    ).toBeVisible();

    // Verify the Create Account button
    await expect(
      page.getByRole("button", { name: "Create Account" })
    ).toBeVisible();

    await docScreenshot(page, "admin--worker-accounts--list-view");
  });

  test("renders empty state", async ({ mount, page }) => {
    const mocks = [
      {
        request: { query: GET_WORKER_ACCOUNTS },
        variableMatcher: () => true,
        result: {
          data: {
            workerAccounts: [],
          },
        },
      },
    ];

    await mount(<WorkerAccountManagementTestWrapper mocks={mocks} />);

    // Wait for query to resolve
    await expect(page.getByText("Worker Accounts").first()).toBeVisible({
      timeout: 10000,
    });

    // Verify the empty state message
    await expect(page.getByText("No Worker Accounts")).toBeVisible();
    await expect(
      page.getByText(
        "Create your first worker account to enable automated document upload pipelines."
      )
    ).toBeVisible();

    // Create Account button should still be visible
    await expect(
      page.getByRole("button", { name: "Create Account" })
    ).toBeVisible();

    await docScreenshot(page, "admin--worker-accounts--empty");
  });

  test("shows back link to admin settings", async ({ mount, page }) => {
    const mocks = [
      {
        request: { query: GET_WORKER_ACCOUNTS },
        variableMatcher: () => true,
        result: {
          data: {
            workerAccounts: [],
          },
        },
      },
    ];

    await mount(<WorkerAccountManagementTestWrapper mocks={mocks} />);

    await expect(page.getByText("Back to Admin Settings")).toBeVisible({
      timeout: 10000,
    });
  });

  test("opens create account modal", async ({ mount, page }) => {
    const mocks = [
      {
        request: { query: GET_WORKER_ACCOUNTS },
        variableMatcher: () => true,
        result: {
          data: {
            workerAccounts: [],
          },
        },
      },
    ];

    await mount(<WorkerAccountManagementTestWrapper mocks={mocks} />);

    // Wait for the page to load
    await expect(page.getByText("Worker Accounts").first()).toBeVisible({
      timeout: 10000,
    });

    // Click the Create Account button
    await page.getByRole("button", { name: "Create Account" }).click();

    // Verify modal opens with form fields
    await expect(page.getByText("Create Worker Account").first()).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("Name")).toBeVisible();
    await expect(page.getByText("Description")).toBeVisible();

    // Verify the Create Account button in the modal is disabled when name is empty
    const modalCreateButton = page
      .locator(".oc-modal-footer")
      .getByRole("button", { name: "Create Account" });
    await expect(modalCreateButton).toBeDisabled();

    await docScreenshot(page, "admin--worker-accounts--create-modal");
  });

  test("clicking Activate fires the reactivate mutation", async ({
    mount,
    page,
  }) => {
    // Covers the inactive branch of handleToggleActive (calls reactivateAccount
    // directly without opening a confirm modal). Tests previously only asserted
    // the buttons rendered, not their click handlers, leaving the toggle paths
    // uncovered in codecov.
    let reactivateCalled = false;
    const REACTIVATE_WORKER_ACCOUNT = gql`
      mutation ReactivateWorkerAccount($workerAccountId: Int!) {
        reactivateWorkerAccount(workerAccountId: $workerAccountId) {
          ok
        }
      }
    `;
    const mocks = [
      {
        request: { query: GET_WORKER_ACCOUNTS },
        variableMatcher: () => true,
        result: {
          data: {
            workerAccounts: mockWorkerAccounts,
          },
        },
      },
      {
        request: {
          query: REACTIVATE_WORKER_ACCOUNT,
          variables: { workerAccountId: 3 },
        },
        result: () => {
          reactivateCalled = true;
          return {
            data: {
              reactivateWorkerAccount: {
                ok: true,
                __typename: "ReactivateWorkerAccount",
              },
            },
          };
        },
      },
      // Refetch after reactivate
      {
        request: { query: GET_WORKER_ACCOUNTS },
        variableMatcher: () => true,
        result: {
          data: { workerAccounts: mockWorkerAccounts },
        },
      },
    ];

    await mount(<WorkerAccountManagementTestWrapper mocks={mocks} />);

    await expect(page.getByText("Legacy Importer")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("button", { name: "Activate", exact: true }).click();

    // Give Apollo a moment to dispatch the mutation
    await expect.poll(() => reactivateCalled, { timeout: 5000 }).toBe(true);
  });

  test("clicking Deactivate opens the confirm modal", async ({
    mount,
    page,
  }) => {
    // Covers the active branch of handleToggleActive (opens accountToDeactivate
    // state, surfacing the confirm modal). Without this test the active branch
    // is never executed in tests.
    const mocks = [
      {
        request: { query: GET_WORKER_ACCOUNTS },
        variableMatcher: () => true,
        result: {
          data: { workerAccounts: mockWorkerAccounts },
        },
      },
    ];

    await mount(<WorkerAccountManagementTestWrapper mocks={mocks} />);

    await expect(page.getByText("Pipeline Uploader")).toBeVisible({
      timeout: 10000,
    });

    // Click the first Deactivate button (Pipeline Uploader is active)
    await page.getByRole("button", { name: "Deactivate" }).first().click();

    // Confirm modal should appear
    await expect(page.getByText("Confirm Deactivation").first()).toBeVisible({
      timeout: 5000,
    });
  });

  test("keeps the worker account table horizontally scrollable on mobile", async ({
    mount,
    page,
  }) => {
    // Regression guard for issue #1749: the wide worker-account table must
    // scroll horizontally on small viewports rather than crush its columns.
    await page.setViewportSize({ width: 390, height: 844 });

    const mocks = [
      {
        request: { query: GET_WORKER_ACCOUNTS },
        variableMatcher: () => true,
        result: {
          data: {
            workerAccounts: mockWorkerAccounts,
          },
        },
      },
    ];

    const component = await mount(
      <WorkerAccountManagementTestWrapper mocks={mocks} />
    );

    await expect(page.getByText("Pipeline Uploader")).toBeVisible({
      timeout: 10000,
    });

    const scroll = page.getByTestId("worker-accounts-table-scroll");
    await expect(scroll).toBeVisible();
    const overflowX = await scroll.evaluate(
      (el) => getComputedStyle(el).overflowX
    );
    expect(overflowX).toBe("auto");
    const scrolls = await scroll.evaluate(
      (el) => el.scrollWidth > el.clientWidth
    );
    expect(scrolls).toBe(true);

    await component.unmount();
  });
});
