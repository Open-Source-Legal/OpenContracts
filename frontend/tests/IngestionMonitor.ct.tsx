import React from "react";
import { test, expect } from "./utils/coverage";
import { gql } from "@apollo/client";
import { IngestionMonitorTestWrapper } from "./IngestionMonitorTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

// Must match the queries in IngestionMonitor.tsx exactly.
const GET_ADMIN_DOCUMENT_INGESTION = gql`
  query GetAdminDocumentIngestion($status: String, $limit: Int, $offset: Int) {
    adminDocumentIngestion(status: $status, limit: $limit, offset: $offset) {
      totalCount
      limit
      offset
      items {
        id
        title
        creatorUsername
        creatorEmail
        fileType
        pageCount
        sizeBytes
        processingStatus
        processingError
        created
        processingStarted
        processingFinished
        elapsedSeconds
      }
    }
  }
`;

const GET_ADMIN_WORKER_UPLOADS = gql`
  query GetAdminWorkerUploads($status: String, $limit: Int, $offset: Int) {
    adminWorkerUploads(status: $status, limit: $limit, offset: $offset) {
      totalCount
      limit
      offset
      items {
        id
        corpusId
        corpusTitle
        workerAccountName
        status
        errorMessage
        fileName
        sizeBytes
        resultDocumentId
        created
        processingStarted
        processingFinished
        elapsedSeconds
      }
    }
  }
`;

const GET_ADMIN_CORPUS_IMPORTS = gql`
  query GetAdminCorpusImports($status: String, $limit: Int, $offset: Int) {
    adminCorpusImports(status: $status, limit: $limit, offset: $offset) {
      totalCount
      limit
      offset
      items {
        id
        importRunId
        corpusId
        corpusTitle
        creatorUsername
        status
        expectedDocCount
        totalCountDocs
        doneCount
        failedCount
        pendingCount
        percentFailed
        created
        modified
      }
    }
  }
`;

const GET_ADMIN_BULK_IMPORT_SESSIONS = gql`
  query GetAdminBulkImportSessions($status: String, $limit: Int, $offset: Int) {
    adminBulkImportSessions(status: $status, limit: $limit, offset: $offset) {
      totalCount
      limit
      offset
      items {
        id
        kind
        filename
        creatorUsername
        status
        errorMessage
        totalSize
        receivedSize
        receivedParts
        totalChunks
        percentComplete
        targetCorpusId
        created
        modified
      }
    }
  }
`;

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const documentItems = [
  {
    id: "1",
    title: "Broken Contract.pdf",
    creatorUsername: "regular",
    creatorEmail: "regular@example.com",
    fileType: "application/pdf",
    pageCount: 12,
    sizeBytes: 204800,
    processingStatus: "failed",
    processingError: "Parser exploded on page 3",
    created: "2026-01-01T10:00:00Z",
    processingStarted: "2026-01-01T10:00:00Z",
    processingFinished: "2026-01-01T10:00:05Z",
    elapsedSeconds: 5.0,
  },
  {
    id: "2",
    title: "Good Doc.pdf",
    creatorUsername: "admin",
    creatorEmail: "admin@example.com",
    fileType: "application/pdf",
    pageCount: 3,
    sizeBytes: 51200,
    processingStatus: "completed",
    processingError: null,
    created: "2026-01-02T10:00:00Z",
    processingStarted: "2026-01-02T10:00:00Z",
    processingFinished: "2026-01-02T10:00:02Z",
    elapsedSeconds: 2.0,
  },
];

const workerItems = [
  {
    id: "wu-1",
    corpusId: 1,
    corpusTitle: "Pipeline Corpus",
    workerAccountName: "Pipeline Bot",
    status: "FAILED",
    errorMessage: "bad mime type",
    fileName: "contract-batch-3.pdf",
    sizeBytes: 1024,
    resultDocumentId: null,
    created: "2026-01-03T10:00:00Z",
    processingStarted: null,
    processingFinished: null,
    elapsedSeconds: null,
  },
];

const corpusImportItems = [
  {
    id: "1",
    importRunId: "run-abc",
    corpusId: 1,
    corpusTitle: "Imported Corpus",
    creatorUsername: "admin",
    status: "done",
    expectedDocCount: 3,
    totalCountDocs: 3,
    doneCount: 1,
    failedCount: 1,
    pendingCount: 1,
    percentFailed: 33.33,
    created: "2026-01-04T10:00:00Z",
    modified: "2026-01-04T10:05:00Z",
  },
];

const bulkSessionItems = [
  {
    id: "sess-1",
    kind: "documents_zip",
    filename: "batch.zip",
    creatorUsername: "regular",
    status: "PENDING",
    errorMessage: null,
    totalSize: 1000,
    receivedSize: 500,
    receivedParts: 1,
    totalChunks: 2,
    percentComplete: 50,
    targetCorpusId: "Q29ycHVzOjE=",
    created: "2026-01-05T10:00:00Z",
    modified: "2026-01-05T10:01:00Z",
  },
];

const page = (field: string, items: any[]) => ({
  [field]: { totalCount: items.length, limit: 50, offset: 0, items },
});

// The component's initial query shape for every list (status filter "All"
// maps to null; limit is INGESTION_MONITOR_PAGE_SIZE; first page offset 0).
const INITIAL_VARS = { status: null, limit: 50, offset: 0 };

/**
 * One reusable mock per list query.
 *
 * Two Playwright-CT serialization constraints drive this shape (see the same
 * note in Leaderboard.ct.tsx): the `mocks` prop crosses the test/component
 * boundary as JSON, so a `variableMatcher: () => true` function is stripped to
 * `{}` and `maxUsageCount: Infinity` collapses to `null`. We therefore key the
 * mocks to the component's explicit initial `variables` and use a finite
 * `maxUsageCount` so they survive the trip.
 *
 * Reuse is required because the component fetches with
 * `fetchPolicy: "network-only"` behind `skip: !isSuperuser` (which only flips
 * true once the wrapper effect sets `backendUserObj`); combined with React
 * StrictMode's double mount and the Refresh button's `refetch()`, a single
 * query can fire several times.
 */
function buildMocks(opts?: {
  documents?: any[];
  workers?: any[];
  imports?: any[];
  sessions?: any[];
}) {
  const documents = opts?.documents ?? documentItems;
  const workers = opts?.workers ?? workerItems;
  const imports = opts?.imports ?? corpusImportItems;
  const sessions = opts?.sessions ?? bulkSessionItems;
  const pairs: [any, any][] = [
    [GET_ADMIN_DOCUMENT_INGESTION, page("adminDocumentIngestion", documents)],
    [GET_ADMIN_WORKER_UPLOADS, page("adminWorkerUploads", workers)],
    [GET_ADMIN_CORPUS_IMPORTS, page("adminCorpusImports", imports)],
    [GET_ADMIN_BULK_IMPORT_SESSIONS, page("adminBulkImportSessions", sessions)],
  ];
  return pairs.map(([query, data]) => ({
    request: { query, variables: INITIAL_VARS },
    maxUsageCount: 20,
    result: { data },
  }));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("IngestionMonitor", () => {
  test("renders the document ingestion tab with documents and worker queue", async ({
    mount,
    page: pw,
  }) => {
    await mount(<IngestionMonitorTestWrapper mocks={buildMocks()} />);

    await expect(pw.getByText("Ingestion Monitor").first()).toBeVisible({
      timeout: 10000,
    });

    // Document rows
    await expect(pw.getByText("Broken Contract.pdf")).toBeVisible();
    await expect(pw.getByText("regular@example.com")).toBeVisible();
    await expect(pw.getByText("Parser exploded on page 3")).toBeVisible();
    // failed status pill (also appears on the worker row). exact:true so we
    // match the lowercase pill text and not the "Failed" status-filter option.
    await expect(pw.getByText("failed", { exact: true }).first()).toBeVisible();

    // Worker queue section
    await expect(pw.getByText("Worker Upload Queue")).toBeVisible();
    await expect(pw.getByText("Pipeline Bot")).toBeVisible();
    await expect(pw.getByText("bad mime type")).toBeVisible();

    await docScreenshot(pw, "admin--ingestion-monitor--documents");
  });

  test("switches to the import batches tab and shows percent failed", async ({
    mount,
    page: pw,
  }) => {
    await mount(<IngestionMonitorTestWrapper mocks={buildMocks()} />);

    await expect(pw.getByText("Ingestion Monitor").first()).toBeVisible({
      timeout: 10000,
    });

    await pw.getByTestId("tab-imports").click();

    await expect(pw.getByText("Corpus-Export Imports")).toBeVisible({
      timeout: 10000,
    });
    await expect(pw.getByText("Imported Corpus")).toBeVisible();
    await expect(pw.getByText("33.3%")).toBeVisible();

    await expect(pw.getByText("Bulk Document Imports")).toBeVisible();
    await expect(pw.getByText("batch.zip")).toBeVisible();

    await docScreenshot(pw, "admin--ingestion-monitor--imports");
  });

  test("shows empty states when there are no rows", async ({
    mount,
    page: pw,
  }) => {
    await mount(
      <IngestionMonitorTestWrapper
        mocks={buildMocks({ documents: [], workers: [] })}
      />
    );

    // exact:true so the empty-state heading isn't conflated with the longer
    // "No documents match the selected filter." helper line below it.
    await expect(pw.getByText("No documents", { exact: true })).toBeVisible({
      timeout: 10000,
    });
    await expect(
      pw.getByText("No worker uploads", { exact: true })
    ).toBeVisible();
  });

  test("denies access to non-superusers", async ({ mount, page: pw }) => {
    await mount(
      <IngestionMonitorTestWrapper mocks={buildMocks()} superuser={false} />
    );

    await expect(pw.getByText("Access Denied")).toBeVisible({ timeout: 10000 });
    await expect(
      pw.getByText("Only administrators can view the ingestion monitor.")
    ).toBeVisible();
  });

  test("keeps the ingestion table horizontally scrollable on mobile", async ({
    mount,
    page: pw,
  }) => {
    await pw.setViewportSize({ width: 390, height: 844 });

    const component = await mount(
      <IngestionMonitorTestWrapper mocks={buildMocks()} />
    );

    await expect(pw.getByText("Broken Contract.pdf")).toBeVisible({
      timeout: 10000,
    });

    const scroll = pw.getByTestId("documents-table-scroll");
    await expect(scroll).toBeVisible();
    const overflowX = await scroll.evaluate(
      (el) => getComputedStyle(el).overflowX
    );
    expect(overflowX).toBe("auto");

    await component.unmount();
  });
});
