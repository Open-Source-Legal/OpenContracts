/**
 * Component tests for EnrichmentRunner + EnrichmentJobList.
 *
 * Each JSX component import is in its own import statement (Playwright CT
 * split-import rule). `EnrichmentRunnerWrapperFull` and
 * `BareEnrichmentRunnerWrapper` live in separate files so Playwright CT's
 * babel transform can create a unique importRef for each.
 *
 * WebSocket note: useEnrichmentJobs calls useNotificationWebSocket with
 * requireAuth: true.  In CT tests there is no auth token, so the hook exits
 * the connection effect immediately (shouldConnect = false) and never opens a
 * socket.  The WS path is therefore inert in these tests.
 */
import { test, expect } from "./utils/coverage";

import { EnrichmentRunnerWrapperFull } from "./EnrichmentRunnerWrapperFull";
import { BareEnrichmentRunnerWrapper } from "./EnrichmentRunnerTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

import {
  RUN_CORPUS_ENRICHMENT,
  type EnrichmentAnalysisRow,
} from "../src/graphql/mutations";
import { GET_CORPUS_ANALYSES } from "../src/graphql/queries";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CORPUS_ID = "Q29ycHVzVHlwZTo0Mg==";
const ENRICHMENT_ANALYZER_ID = "QW5hbHl6ZXJUeXBlOjE=";
const ANALYSIS_ID = "QW5hbHlzaXNUeXBlOjE=";
const STARTED_AT = "2026-06-15T10:00:00Z";

// Inline copy of ENRICHMENT_TASK_NAMES from useEnrichmentJobs.ts.
// We cannot import that .ts hook file directly because Playwright CT's
// Node.js module loader evaluates it outside the Vite transform pipeline and
// the transitive get_websockets.ts import triggers "exports is not defined".
const ENRICHMENT_TASK_NAMES = [
  "opencontractserver.tasks.corpus_analysis_tasks.corpus_reference_enrichment",
  "opencontractserver.tasks.corpus_analysis_tasks.crawl_authorities",
];

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RUNNING_ANALYSIS: EnrichmentAnalysisRow = {
  id: ANALYSIS_ID,
  status: "RUNNING",
  analysisStarted: STARTED_AT,
  analysisCompleted: null,
  errorMessage: null,
  resultMessage: null,
  analyzer: {
    id: ENRICHMENT_ANALYZER_ID,
    taskName:
      "opencontractserver.tasks.corpus_analysis_tasks.corpus_reference_enrichment",
  },
};

const COMPLETED_ANALYSIS: EnrichmentAnalysisRow = {
  ...RUNNING_ANALYSIS,
  status: "COMPLETED",
  analysisCompleted: "2026-06-15T10:00:47Z",
  resultMessage: JSON.stringify({
    references_created: 42,
    law_references_linked: 38,
  }),
};

// ---------------------------------------------------------------------------
// GraphQL mocks
// ---------------------------------------------------------------------------

/** Variables that useEnrichmentJobs sends for an unconstrained list. */
const QUERY_VARS = {
  corpusId: CORPUS_ID,
  statusExact: null,
  taskNames: ENRICHMENT_TASK_NAMES,
};

/**
 * Mock for RUN_CORPUS_ENRICHMENT.
 *
 * EnrichmentRunner in default state (compact=true, so advancedOpen=false) sends
 * {corpusId, runEnrichment: true, runCrawl: false} with NO options field:
 * hasOptions is false when only LAW is selected, LLM tier is off, and all
 * advanced bounds are empty.
 */
const RUN_MUTATION_MOCK = {
  request: {
    query: RUN_CORPUS_ENRICHMENT,
    variables: {
      corpusId: CORPUS_ID,
      runEnrichment: true,
      runCrawl: false,
    },
  },
  result: {
    data: {
      runCorpusEnrichment: {
        ok: true,
        message: "SUCCESS",
        analyses: [RUNNING_ANALYSIS],
      },
    },
  },
};

/**
 * Initial empty list (before any run).
 * maxUsageCount=10 guards against double-invocation from Vite HMR or
 * React's internal re-renders consuming the mock before the assertion runs.
 */
const EMPTY_QUERY_MOCK = {
  request: { query: GET_CORPUS_ANALYSES, variables: QUERY_VARS },
  result: { data: { analyses: { edges: [] } } },
  maxUsageCount: 10,
};

/** Second fetch — backend echoes the running job. */
const RUNNING_QUERY_MOCK = {
  request: { query: GET_CORPUS_ANALYSES, variables: QUERY_VARS },
  result: {
    data: {
      analyses: {
        edges: [{ node: RUNNING_ANALYSIS }],
      },
    },
  },
  maxUsageCount: 10,
};

/** Third fetch — job completes. */
const COMPLETED_QUERY_MOCK = {
  request: { query: GET_CORPUS_ANALYSES, variables: QUERY_VARS },
  result: {
    data: {
      analyses: {
        edges: [{ node: COMPLETED_ANALYSIS }],
      },
    },
  },
  maxUsageCount: 10,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("EnrichmentRunner", () => {
  test("renders the job list in empty state on mount", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <EnrichmentRunnerWrapperFull
        corpusId={CORPUS_ID}
        mocks={[EMPTY_QUERY_MOCK, RUNNING_QUERY_MOCK, COMPLETED_QUERY_MOCK]}
      />
    );

    // Run button is visible and enabled
    const runBtn = page.locator('[data-testid="enrichment-run-button"]');
    await expect(runBtn).toBeVisible({ timeout: 10000 });
    await expect(runBtn).toBeEnabled();

    // EnrichmentJobList transitions through LoadingState then renders the
    // job-list container once the Apollo query resolves.
    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toBeVisible({ timeout: 15000 });

    // Empty state — no runs yet
    await expect(
      page.locator('[data-testid="enrichment-job-row"]')
    ).toHaveCount(0);
    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toContainText("No enrichment runs yet.");

    await component.unmount();
  });

  test("clicking Run fires mutation and shows optimistic RUNNING row", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <EnrichmentRunnerWrapperFull
        corpusId={CORPUS_ID}
        mocks={[
          EMPTY_QUERY_MOCK,
          RUN_MUTATION_MOCK,
          RUNNING_QUERY_MOCK,
          COMPLETED_QUERY_MOCK,
        ]}
      />
    );

    // Wait for job list to appear after initial query
    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toBeVisible({ timeout: 15000 });

    // Fire the mutation
    const runBtn = page.locator('[data-testid="enrichment-run-button"]');
    await expect(runBtn).toBeEnabled();
    await runBtn.click();

    // Optimistic RUNNING row appears (onRan → extraJobs)
    const rows = page.locator('[data-testid="enrichment-job-row"]');
    await expect(rows).toHaveCount(1, { timeout: 10000 });

    // Status badge shows "running"
    const statusBadge = page.locator('[data-testid="enrichment-job-status"]');
    await expect(statusBadge).toBeVisible();
    await expect(statusBadge).toContainText("running");

    // Job label shows the human-readable task name
    await expect(rows.first()).toContainText("Reference enrichment");

    // Run button becomes disabled while a running job exists
    await expect(runBtn).toBeDisabled();

    await docScreenshot(page, "enrichment--runner-and-jobs--with-data");

    await component.unmount();
  });

  test("Run button is disabled when runningJobExists is pre-set", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <BareEnrichmentRunnerWrapper
        corpusId={CORPUS_ID}
        runningJobExists={true}
      />
    );

    const runBtn = page.locator('[data-testid="enrichment-run-button"]');
    await expect(runBtn).toBeVisible({ timeout: 10000 });
    await expect(runBtn).toBeDisabled();

    await component.unmount();
  });

  test("deduplicates optimistic row once backend echoes the same id", async ({
    mount,
    page,
  }) => {
    // After the mutation returns an optimistic row, the query refetch returns
    // the same id.  EnrichmentJobList.extraIds dedup must show exactly one row.
    const component = await mount(
      <EnrichmentRunnerWrapperFull
        corpusId={CORPUS_ID}
        mocks={[
          EMPTY_QUERY_MOCK,
          RUN_MUTATION_MOCK,
          RUNNING_QUERY_MOCK,
          COMPLETED_QUERY_MOCK,
        ]}
      />
    );

    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toBeVisible({ timeout: 15000 });

    await page.locator('[data-testid="enrichment-run-button"]').click();

    // After the optimistic row appears, exactly one row (not two)
    await expect(
      page.locator('[data-testid="enrichment-job-row"]')
    ).toHaveCount(1, { timeout: 10000 });

    await component.unmount();
  });

  // -------------------------------------------------------------------------
  // Fix-A: optimistic row replaced by real fetched row (RUNNING → COMPLETED)
  // -------------------------------------------------------------------------

  test("fetched RUNNING row supersedes optimistic copy — count stays at 1", async ({
    mount,
    page,
  }) => {
    // Fix-A regression test: after the mutation returns an optimistic RUNNING
    // row AND the refetch echoes the same id (still RUNNING), the pruning
    // effect in the wrapper removes the optimistic copy so that
    // EnrichmentJobList shows exactly one row — not two.
    // (Status RUNNING→COMPLETED transition requires a WS notification which is
    // not available in CT; that path is covered by the integration test suite.)
    const component = await mount(
      <EnrichmentRunnerWrapperFull
        corpusId={CORPUS_ID}
        mocks={[
          EMPTY_QUERY_MOCK,
          RUN_MUTATION_MOCK,
          RUNNING_QUERY_MOCK,
          COMPLETED_QUERY_MOCK,
        ]}
      />
    );

    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toBeVisible({ timeout: 15000 });

    // Click Run — optimistic row set from mutation response
    await page.locator('[data-testid="enrichment-run-button"]').click();

    // The fetched RUNNING row supersedes the optimistic one → still one row
    await expect(
      page.locator('[data-testid="enrichment-job-row"]')
    ).toHaveCount(1, { timeout: 10000 });

    // The displayed status is "running" (from the real fetched row)
    await expect(
      page.locator('[data-testid="enrichment-job-status"]')
    ).toContainText("running");

    await component.unmount();
  });

  // -------------------------------------------------------------------------
  // Fix-B: CREATED status (not just RUNNING/QUEUED) disables the run button
  // -------------------------------------------------------------------------

  test("Run button stays disabled when a CREATED job is present in fetched list", async ({
    mount,
    page,
  }) => {
    const CREATED_ANALYSIS: EnrichmentAnalysisRow = {
      ...RUNNING_ANALYSIS,
      status: "CREATED",
    };

    const CREATED_QUERY_MOCK = {
      request: { query: GET_CORPUS_ANALYSES, variables: QUERY_VARS },
      result: {
        data: {
          analyses: {
            edges: [{ node: CREATED_ANALYSIS }],
          },
        },
      },
      maxUsageCount: 10,
    };

    const component = await mount(
      <EnrichmentRunnerWrapperFull
        corpusId={CORPUS_ID}
        mocks={[CREATED_QUERY_MOCK]}
      />
    );

    // Wait for the job list to reflect the CREATED row
    await expect(
      page.locator('[data-testid="enrichment-job-status"]')
    ).toContainText("created", { timeout: 10000 });

    // Run button must be disabled because CREATED is in ACTIVE_STATUSES
    const runBtn = page.locator('[data-testid="enrichment-run-button"]');
    await expect(runBtn).toBeDisabled();

    await component.unmount();
  });

  test("Run button stays disabled immediately after click (optimistic ACTIVE guard)", async ({
    mount,
    page,
  }) => {
    // Verify that the run button is disabled while the optimistic row is still
    // in RUNNING state — even before the refetch resolves.
    const component = await mount(
      <EnrichmentRunnerWrapperFull
        corpusId={CORPUS_ID}
        mocks={[
          EMPTY_QUERY_MOCK,
          RUN_MUTATION_MOCK,
          RUNNING_QUERY_MOCK,
          COMPLETED_QUERY_MOCK,
        ]}
      />
    );

    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toBeVisible({ timeout: 15000 });

    const runBtn = page.locator('[data-testid="enrichment-run-button"]');
    await expect(runBtn).toBeEnabled();

    await runBtn.click();

    // Optimistic row is RUNNING — button must be disabled immediately
    await expect(runBtn).toBeDisabled({ timeout: 5000 });

    await component.unmount();
  });
});
