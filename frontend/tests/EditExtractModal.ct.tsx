import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { EditExtractModalTestWrapper } from "./EditExtractModalTestWrapper";
import { REQUEST_GET_EXTRACT } from "../src/graphql/queries";
import {
  REQUEST_START_EXTRACT,
  REQUEST_ADD_DOC_TO_EXTRACT,
  REQUEST_REMOVE_DOC_FROM_EXTRACT,
  REQUEST_DELETE_COLUMN,
  REQUEST_CREATE_COLUMN,
} from "../src/graphql/mutations";
import { ExtractType } from "../src/types/graphql-api";
import { PermissionTypes } from "../src/components/types";

const EXTRACT_ID = "test-extract-1";
const CORPUS_ID = "test-corpus-1";
const DOC_ID = "test-doc-1";
const COLUMN_ID = "test-column-1";

// Mock data
const mockExtract: ExtractType = {
  id: EXTRACT_ID,
  name: "Test Extract",
  corpus: {
    id: CORPUS_ID,
    title: "Test Corpus",
    icon: undefined,
    description: "Test corpus description",
    labelSet: undefined,
    documents: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: "",
        endCursor: "",
      },
    },
    analyses: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: "",
        endCursor: "",
      },
    },
    isPublic: false,
    creator: { id: "user-1", email: "test@example.com" },
    backendLock: false,
    myPermissions: [PermissionTypes.CAN_READ, PermissionTypes.CAN_UPDATE],
  },
  creator: {
    id: "user-1",
    email: "test@example.com",
    username: "testuser",
  },
  created: new Date().toISOString(),
  started: null,
  finished: null,
  error: null,
  fieldset: {
    id: "fieldset-1",
    name: "Test Fieldset",
    description: "Test fieldset description",
    inUse: false,
    creator: {
      id: "user-1",
      email: "test@example.com",
      username: "testuser",
    },
    columns: {
      edges: [
        {
          node: {
            id: COLUMN_ID,
            name: "Test Column",
            query: "test query",
            outputType: "text",
            extractIsList: false,
            limitToLabel: undefined,
            instructions: undefined,
            taskName: "test_task",
            matchText: undefined,
          },
        },
      ],
    },
    fullColumnList: [
      {
        id: COLUMN_ID,
        name: "Test Column",
        query: "test query",
        outputType: "text",
        extractIsList: false,
        limitToLabel: undefined,
        instructions: undefined,
        taskName: "test_task",
        matchText: undefined,
      },
    ],
  },
  fullDocumentList: [
    {
      id: DOC_ID,
      title: "Test Document",
      description: "Test document description",
      pageCount: 10,
      fileType: "application/pdf",
      icon: undefined,
      pdfFile: undefined,
      txtExtractFile: undefined,
      pawlsParseFile: undefined,
      backendLock: false,
      isPublic: false,
      myPermissions: [PermissionTypes.CAN_READ, PermissionTypes.CAN_UPDATE],
    },
  ],
  fullDatacellList: [
    {
      id: "datacell-1",
      column: {
        id: COLUMN_ID,
        name: "Test Column",
        outputType: "text",
        taskName: "test_task",
      },
      document: {
        id: DOC_ID,
        title: "Test Document",
        fileType: "application/pdf",
      },
      extract: {
        id: EXTRACT_ID,
      } as ExtractType,
      data: { value: "Test data" },
      dataDefinition: "text",
      started: null,
      completed: null,
      failed: null,
      correctedData: null,
      rejectedBy: null,
      approvedBy: null,
      fullSourceList: [],
    },
  ],
};

// GraphQL mocks
const mocks = [
  // Get Extract query
  {
    request: {
      query: REQUEST_GET_EXTRACT,
      variables: { id: EXTRACT_ID },
    },
    result: {
      data: {
        extract: mockExtract,
      },
    },
  },
  // Refetch for polling
  {
    request: {
      query: REQUEST_GET_EXTRACT,
      variables: { id: EXTRACT_ID },
    },
    result: {
      data: {
        extract: mockExtract,
      },
    },
  },
  // Start Extract mutation
  {
    request: {
      query: REQUEST_START_EXTRACT,
      variables: { extractId: EXTRACT_ID },
    },
    result: {
      data: {
        startExtract: {
          ok: true,
          msg: "Extract started",
          obj: {
            ...mockExtract,
            started: new Date().toISOString(),
          },
        },
      },
    },
  },
  // Add Document mutation
  {
    request: {
      query: REQUEST_ADD_DOC_TO_EXTRACT,
      variables: {
        extractId: EXTRACT_ID,
        documentIds: ["new-doc-1"],
      },
    },
    result: {
      data: {
        addDocsToExtract: {
          ok: true,
          msg: "Documents added",
          objs: [
            {
              id: "new-doc-1",
              title: "New Document",
              description: "New document description",
              pageCount: 5,
              fileType: "application/pdf",
              icon: undefined,
              pdfFile: undefined,
              txtExtractFile: undefined,
              pawlsParseFile: undefined,
              backendLock: false,
              isPublic: false,
              myPermissions: [
                PermissionTypes.CAN_READ,
                PermissionTypes.CAN_UPDATE,
              ],
            },
          ],
        },
      },
    },
  },
  // Remove Document mutation
  {
    request: {
      query: REQUEST_REMOVE_DOC_FROM_EXTRACT,
      variables: {
        extractId: EXTRACT_ID,
        documentIdsToRemove: [DOC_ID],
      },
    },
    result: {
      data: {
        removeDocsFromExtract: {
          ok: true,
          msg: "Documents removed",
          idsRemoved: [DOC_ID],
        },
      },
    },
  },
  // Delete Column mutation
  {
    request: {
      query: REQUEST_DELETE_COLUMN,
      variables: { id: COLUMN_ID },
    },
    result: {
      data: {
        deleteColumn: {
          ok: true,
          msg: "Column deleted",
          deletedId: COLUMN_ID,
        },
      },
    },
  },
  // Create Column mutation
  {
    request: {
      query: REQUEST_CREATE_COLUMN,
      variables: {
        fieldsetId: "fieldset-1",
        name: "New Column",
        query: "new query",
        outputType: "text",
        extractIsList: false,
      },
    },
    result: {
      data: {
        createColumn: {
          ok: true,
          msg: "Column created",
          obj: {
            id: "new-column-1",
            name: "New Column",
            query: "new query",
            outputType: "text",
            extractIsList: false,
            limitToLabel: undefined,
            instructions: undefined,
            taskName: undefined,
            matchText: undefined,
          },
        },
      },
    },
  },
];

test.describe("EditExtractModal", () => {
  test("renders modal with extract details", async ({ mount, page }) => {
    await mount(
      <EditExtractModalTestWrapper
        mocks={mocks}
        open={true}
        ext={mockExtract}
        toggleModal={() => {}}
      />
    );

    // Check modal is visible
    await expect(page.locator("#edit-extract-modal")).toBeVisible({
      timeout: 10000,
    });

    // Check extract name is displayed
    await expect(page.locator("#extract-name")).toContainText("Test Extract");

    // Check creator info
    await expect(page.locator("#extract-meta")).toContainText(
      "test@example.com"
    );

    // Check status is not started
    await expect(page.locator("#status-not-started")).toBeVisible();

    // Check document count
    await expect(page.locator("#docs-count")).toContainText("1");

    // Check column count
    await expect(page.locator("#cols-count")).toContainText("1");

    // Check corpus info
    await expect(page.locator("#corpus-title")).toContainText("Test Corpus");
  });

  test("can start extract", async ({ mount, page }) => {
    await mount(
      <EditExtractModalTestWrapper
        mocks={mocks}
        open={true}
        ext={mockExtract}
        toggleModal={() => {}}
      />
    );

    // Wait for modal to be visible
    await expect(page.locator("#edit-extract-modal")).toBeVisible({
      timeout: 10000,
    });

    // Click start button
    const startButton = page.locator("#start-extract-button");
    await expect(startButton).toBeVisible();
    await startButton.click();

    // Wait for mutation to complete (in real app, status would update)
    await page.waitForTimeout(1000);
  });

  test("shows loading state", async ({ mount, page }) => {
    const loadingMocks = [
      {
        request: {
          query: REQUEST_GET_EXTRACT,
          variables: { id: EXTRACT_ID },
        },
        delay: 2000, // Delay to show loading state
        result: {
          data: {
            extract: mockExtract,
          },
        },
      },
    ];

    await mount(
      <EditExtractModalTestWrapper
        mocks={loadingMocks}
        open={true}
        ext={{ ...mockExtract, id: EXTRACT_ID } as ExtractType}
        toggleModal={() => {}}
      />
    );

    // Check loading dimmer is visible
    await expect(page.locator("#loading-dimmer")).toBeVisible();
  });

  test("shows processing status", async ({ mount, page }) => {
    const processingExtract = {
      ...mockExtract,
      started: new Date().toISOString(),
      finished: null,
    };

    const processingMocks = [
      {
        request: {
          query: REQUEST_GET_EXTRACT,
          variables: { id: EXTRACT_ID },
        },
        result: {
          data: {
            extract: processingExtract,
          },
        },
      },
    ];

    await mount(
      <EditExtractModalTestWrapper
        mocks={processingMocks}
        open={true}
        ext={processingExtract}
        toggleModal={() => {}}
      />
    );

    // Check processing status is visible
    await expect(page.locator("#status-processing")).toBeVisible({
      timeout: 10000,
    });
  });

  test("shows completed status", async ({ mount, page }) => {
    const completedExtract = {
      ...mockExtract,
      started: new Date().toISOString(),
      finished: new Date().toISOString(),
    };

    const completedMocks = [
      {
        request: {
          query: REQUEST_GET_EXTRACT,
          variables: { id: EXTRACT_ID },
        },
        result: {
          data: {
            extract: completedExtract,
          },
        },
      },
    ];

    await mount(
      <EditExtractModalTestWrapper
        mocks={completedMocks}
        open={true}
        ext={completedExtract}
        toggleModal={() => {}}
      />
    );

    // Check completed status is visible
    await expect(page.locator("#status-completed")).toBeVisible({
      timeout: 10000,
    });
  });

  test("shows failed status", async ({ mount, page }) => {
    const failedExtract = {
      ...mockExtract,
      started: new Date().toISOString(),
      error: "Something went wrong",
    };

    const failedMocks = [
      {
        request: {
          query: REQUEST_GET_EXTRACT,
          variables: { id: EXTRACT_ID },
        },
        result: {
          data: {
            extract: failedExtract,
          },
        },
      },
    ];

    await mount(
      <EditExtractModalTestWrapper
        mocks={failedMocks}
        open={true}
        ext={failedExtract}
        toggleModal={() => {}}
      />
    );

    // Check failed status is visible
    await expect(page.locator("#status-failed")).toBeVisible({
      timeout: 10000,
    });
  });

  test("can close modal", async ({ mount, page }) => {
    let modalClosed = false;
    const handleClose = () => {
      modalClosed = true;
    };

    await mount(
      <EditExtractModalTestWrapper
        mocks={mocks}
        open={true}
        ext={mockExtract}
        toggleModal={handleClose}
      />
    );

    // Click close button
    const closeButton = page.locator("#close-button");
    await expect(closeButton).toBeVisible();
    await closeButton.click();

    // Check modal was closed
    expect(modalClosed).toBe(true);
  });

  test("shows export CSV button", async ({ mount, page }) => {
    await mount(
      <EditExtractModalTestWrapper
        mocks={mocks}
        open={true}
        ext={mockExtract}
        toggleModal={() => {}}
      />
    );

    // Check export button is visible
    const exportButton = page.locator("#export-csv-button");
    await expect(exportButton).toBeVisible({
      timeout: 10000,
    });
  });

  test("renders data grid", async ({ mount, page }) => {
    await mount(
      <EditExtractModalTestWrapper
        mocks={mocks}
        open={true}
        ext={mockExtract}
        toggleModal={() => {}}
      />
    );

    // Check data grid container is visible
    await expect(page.locator("#data-grid-container")).toBeVisible({
      timeout: 10000,
    });
  });
});
