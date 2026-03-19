import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { gql } from "@apollo/client";
import { WorkerTokensSectionTestWrapper } from "./WorkerTokensSectionTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

// ---------------------------------------------------------------------------
// GraphQL operations (must match the component's queries/mutations exactly)
// ---------------------------------------------------------------------------

const GET_CORPUS_ACCESS_TOKENS = gql`
  query GetCorpusAccessTokens($corpusId: Int!) {
    corpusAccessTokens(corpusId: $corpusId) {
      id
      keyPrefix
      workerAccountId
      workerAccountName
      isActive
      expiresAt
      rateLimitPerMinute
      created
      uploadCountPending
      uploadCountCompleted
      uploadCountFailed
    }
  }
`;

const GET_WORKER_ACCOUNTS_FOR_TOKENS = gql`
  query GetWorkerAccountsForTokens {
    workerAccounts(isActive: true) {
      id
      name
    }
  }
`;

const CREATE_CORPUS_ACCESS_TOKEN = gql`
  mutation CreateCorpusAccessToken(
    $workerAccountId: Int!
    $corpusId: Int!
    $expiresAt: DateTime
    $rateLimitPerMinute: Int
  ) {
    createCorpusAccessToken(
      workerAccountId: $workerAccountId
      corpusId: $corpusId
      expiresAt: $expiresAt
      rateLimitPerMinute: $rateLimitPerMinute
    ) {
      ok
      token {
        id
        key
        workerAccountName
        corpusId
        expiresAt
        rateLimitPerMinute
        created
      }
    }
  }
`;

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const mockTokens = [
  {
    id: 1,
    keyPrefix: "a1b2c3d4",
    workerAccountId: 1,
    workerAccountName: "Pipeline Uploader",
    isActive: true,
    expiresAt: "2027-06-15T00:00:00Z",
    rateLimitPerMinute: 60,
    created: "2025-12-01T10:00:00Z",
    uploadCountPending: 2,
    uploadCountCompleted: 150,
    uploadCountFailed: 3,
  },
  {
    id: 2,
    keyPrefix: "e5f6g7h8",
    workerAccountId: 2,
    workerAccountName: "OCR Service",
    isActive: false,
    expiresAt: null,
    rateLimitPerMinute: 0,
    created: "2025-11-15T14:00:00Z",
    uploadCountPending: 0,
    uploadCountCompleted: 42,
    uploadCountFailed: 0,
  },
];

const mockWorkerAccounts = [
  { id: 1, name: "Pipeline Uploader" },
  { id: 2, name: "OCR Service" },
];

// ---------------------------------------------------------------------------
// Reusable mocks
// ---------------------------------------------------------------------------

const tokenQueryMock = {
  request: {
    query: GET_CORPUS_ACCESS_TOKENS,
    variables: { corpusId: 46 },
  },
  result: {
    data: { corpusAccessTokens: mockTokens },
  },
};

const accountsQueryMock = {
  request: {
    query: GET_WORKER_ACCOUNTS_FOR_TOKENS,
  },
  variableMatcher: () => true,
  result: {
    data: { workerAccounts: mockWorkerAccounts },
  },
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("WorkerTokensSection", () => {
  test("renders token list with status and upload stats", async ({
    mount,
    page,
  }) => {
    await mount(
      <WorkerTokensSectionTestWrapper
        mocks={[tokenQueryMock, accountsQueryMock]}
      />
    );

    // Wait for tokens to load
    await expect(page.getByText("Worker Access Tokens")).toBeVisible({
      timeout: 10000,
    });

    // Verify token data renders
    await expect(page.getByText("a1b2c3d4...")).toBeVisible();
    await expect(page.getByText("Pipeline Uploader").first()).toBeVisible();
    await expect(page.getByText("e5f6g7h8...")).toBeVisible();
    await expect(page.getByText("OCR Service")).toBeVisible();

    // Verify status badges
    await expect(page.getByText("Active")).toBeVisible();
    await expect(page.getByText("Revoked")).toBeVisible();

    // Verify upload stats chips
    await expect(page.getByText("150 done")).toBeVisible();
    await expect(page.getByText("2 pending")).toBeVisible();
    await expect(page.getByText("3 failed")).toBeVisible();

    // Verify revoke button only on active token
    const revokeButtons = page.getByRole("button", { name: "Revoke" });
    await expect(revokeButtons).toHaveCount(1);

    await docScreenshot(page, "corpus--worker-tokens--list-view");
  });

  test("renders empty state for tokens", async ({ mount, page }) => {
    const emptyMock = {
      request: {
        query: GET_CORPUS_ACCESS_TOKENS,
        variables: { corpusId: 46 },
      },
      result: {
        data: { corpusAccessTokens: [] },
      },
    };

    await mount(
      <WorkerTokensSectionTestWrapper mocks={[emptyMock, accountsQueryMock]} />
    );

    await expect(page.getByText("No Access Tokens")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Create a token to allow")).toBeVisible();

    await docScreenshot(page, "corpus--worker-tokens--empty");
  });

  test("opens create token modal with worker account dropdown", async ({
    mount,
    page,
  }) => {
    const emptyMock = {
      request: {
        query: GET_CORPUS_ACCESS_TOKENS,
        variables: { corpusId: 46 },
      },
      result: {
        data: { corpusAccessTokens: [] },
      },
    };

    await mount(
      <WorkerTokensSectionTestWrapper
        mocks={[emptyMock, accountsQueryMock]}
        isSuperuser={true}
      />
    );

    await expect(page.getByText("Worker Access Tokens")).toBeVisible({
      timeout: 10000,
    });

    // Click create button
    await page.getByRole("button", { name: "Create Token" }).click();

    // Verify modal opens
    await expect(page.getByText("Create Access Token")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("Worker Account *")).toBeVisible();
    await expect(page.getByText("Expiry Date (optional)")).toBeVisible();
    await expect(
      page.getByText("Rate Limit (requests/min, 0 = unlimited)")
    ).toBeVisible();

    // Create button in modal footer should be disabled without worker account selected
    const modalButtons = page.getByRole("button", { name: "Create Token" });
    // The second "Create Token" button is the one inside the modal
    const createButton = modalButtons.nth(1);
    await expect(createButton).toBeDisabled();

    await docScreenshot(page, "corpus--worker-tokens--create-modal");
  });

  test("shows create button for non-superuser corpus creator", async ({
    mount,
    page,
  }) => {
    await mount(
      <WorkerTokensSectionTestWrapper
        mocks={[tokenQueryMock, accountsQueryMock]}
        isSuperuser={false}
        isCreator={true}
      />
    );

    await expect(page.getByText("Worker Access Tokens")).toBeVisible({
      timeout: 10000,
    });

    // Token list should still render
    await expect(page.getByText("a1b2c3d4...")).toBeVisible();

    // Corpus creators can create tokens
    await expect(
      page.getByRole("button", { name: "Create Token" })
    ).toBeVisible();
  });

  test("hides create button for non-superuser non-creator", async ({
    mount,
    page,
  }) => {
    await mount(
      <WorkerTokensSectionTestWrapper
        mocks={[tokenQueryMock]}
        isSuperuser={false}
        isCreator={false}
      />
    );

    await expect(page.getByText("Worker Access Tokens")).toBeVisible({
      timeout: 10000,
    });

    // Token list should still render
    await expect(page.getByText("a1b2c3d4...")).toBeVisible();

    // Non-creator, non-superuser should not see Create Token button
    await expect(
      page.getByRole("button", { name: "Create Token" })
    ).not.toBeVisible();
  });

  test("shows one-time key display modal after token creation", async ({
    mount,
    page,
  }) => {
    const emptyTokensMock = {
      request: {
        query: GET_CORPUS_ACCESS_TOKENS,
        variables: { corpusId: 46 },
      },
      result: {
        data: { corpusAccessTokens: [] },
      },
    };

    // Refetch mock (called after mutation succeeds)
    const refetchTokensMock = {
      request: {
        query: GET_CORPUS_ACCESS_TOKENS,
        variables: { corpusId: 46 },
      },
      result: {
        data: { corpusAccessTokens: mockTokens },
      },
    };

    const createMutationMock = {
      request: {
        query: CREATE_CORPUS_ACCESS_TOKEN,
        variables: {
          workerAccountId: 1,
          corpusId: 46,
        },
      },
      result: {
        data: {
          createCorpusAccessToken: {
            ok: true,
            token: {
              id: 99,
              key: "wk_test1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
              workerAccountName: "Pipeline Uploader",
              corpusId: 46,
              expiresAt: null,
              rateLimitPerMinute: 0,
              created: "2026-02-25T10:00:00Z",
            },
          },
        },
      },
    };

    await mount(
      <WorkerTokensSectionTestWrapper
        mocks={[
          emptyTokensMock,
          accountsQueryMock,
          createMutationMock,
          refetchTokensMock,
        ]}
        isSuperuser={true}
      />
    );

    // Wait for page load
    await expect(page.getByText("No Access Tokens")).toBeVisible({
      timeout: 10000,
    });

    // Open create modal
    await page.getByRole("button", { name: "Create Token" }).click();
    await expect(page.getByText("Create Access Token")).toBeVisible({
      timeout: 5000,
    });

    // Select worker account from @os-legal/ui Dropdown
    await page.getByText("Select a worker account").click();
    await page.getByRole("option", { name: "Pipeline Uploader" }).click();

    // Click Create Token button in modal footer (second instance)
    const createBtns = page.getByRole("button", { name: "Create Token" });
    const createBtn = createBtns.nth(1);
    await createBtn.click();

    // One-time key modal should appear
    await expect(page.getByText("Access Token Created")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("This key will only be shown")).toBeVisible();

    // The key should be displayed
    const keyInput = page.locator("input[readonly]");
    await expect(keyInput).toHaveValue(
      "wk_test1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab"
    );

    await docScreenshot(page, "corpus--worker-tokens--key-display");
  });
});
