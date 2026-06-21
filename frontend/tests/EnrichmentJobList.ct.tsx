/**
 * Component tests for EnrichmentJobList.
 *
 * EnrichmentJobList is the presentational table that the EnrichmentRunner CT
 * suite only exercises through the RUNNING/COMPLETED happy path. These tests
 * mount it directly with a spread of job shapes so every status variant,
 * result-summary branch, elapsed-time branch and job-label branch is covered:
 *   - statusVariant: completed / failed / running / queued / created / unknown
 *   - jobLabel: reference-enrichment / authority-crawl / unknown task fallback
 *   - parseResultSummary: enrichment / crawl / non-JSON / null message
 *   - elapsedLabel: sub-minute seconds / multi-minute "Nm Ns" / missing / NaN
 *   - truncation note: shown when totalCount exceeds the fetched rows, hidden
 *     when it fits
 *   - loading, error, empty, optimistic-dedup and newest-first sorting
 *
 * Each JSX-component import is in its own import statement (Playwright CT
 * split-import rule, CLAUDE.md #16).
 */
import { test, expect } from "./utils/coverage";

import { EnrichmentJobListWrapper } from "./EnrichmentJobListWrapper";

import type { ApolloError } from "@apollo/client";
import type { EnrichmentAnalysisRow } from "../src/graphql/mutations";

// ---------------------------------------------------------------------------
// Task-name constants (mirror EnrichmentJobList's ENRICHMENT_SUFFIX/CRAWL_SUFFIX)
// ---------------------------------------------------------------------------

const ENRICHMENT_TASK =
  "opencontractserver.tasks.corpus_analysis_tasks.corpus_reference_enrichment";
const CRAWL_TASK =
  "opencontractserver.tasks.corpus_analysis_tasks.crawl_authorities";

// ---------------------------------------------------------------------------
// Fixtures — one per branch under test
// ---------------------------------------------------------------------------

const completedEnrichment: EnrichmentAnalysisRow = {
  id: "QW5hbHlzaXNUeXBlOjE=",
  status: "COMPLETED",
  analysisStarted: "2026-06-15T10:00:00Z",
  analysisCompleted: "2026-06-15T10:00:47Z",
  errorMessage: null,
  resultMessage: JSON.stringify({
    references_created: 42,
    law_references_linked: 38,
  }),
  analyzer: { id: "QW5hbHl6ZXJUeXBlOjE=", taskName: ENRICHMENT_TASK },
};

const failedEnrichment: EnrichmentAnalysisRow = {
  id: "QW5hbHlzaXNUeXBlOjI=",
  status: "FAILED",
  analysisStarted: "2026-06-15T09:00:00Z",
  analysisCompleted: "2026-06-15T09:00:05Z",
  errorMessage: "boom: provider unreachable",
  resultMessage: null,
  analyzer: { id: "QW5hbHl6ZXJUeXBlOjE=", taskName: ENRICHMENT_TASK },
};

const runningCrawl: EnrichmentAnalysisRow = {
  id: "QW5hbHlzaXNUeXBlOjM=",
  status: "RUNNING",
  analysisStarted: "2026-06-15T11:00:00Z",
  analysisCompleted: null, // exercises elapsedLabel "missing completed" → "—"
  errorMessage: null,
  resultMessage: null,
  analyzer: { id: "QW5hbHl6ZXJUeXBlOjI=", taskName: CRAWL_TASK },
};

const completedCrawl: EnrichmentAnalysisRow = {
  id: "QW5hbHlzaXNUeXBlOjQ=",
  status: "COMPLETED",
  analysisStarted: "2026-06-15T08:00:00Z",
  analysisCompleted: "2026-06-15T08:00:12Z",
  errorMessage: null,
  resultMessage: JSON.stringify({ authorities_ingested: 7 }),
  analyzer: { id: "QW5hbHl6ZXJUeXBlOjI=", taskName: CRAWL_TASK },
};

const queuedJob: EnrichmentAnalysisRow = {
  id: "QW5hbHlzaXNUeXBlOjU=",
  status: "QUEUED",
  analysisStarted: "2026-06-15T07:00:00Z",
  analysisCompleted: null,
  errorMessage: null,
  resultMessage: null,
  analyzer: { id: "QW5hbHl6ZXJUeXBlOjE=", taskName: ENRICHMENT_TASK },
};

const createdJob: EnrichmentAnalysisRow = {
  id: "QW5hbHlzaXNUeXBlOjY=",
  status: "CREATED",
  analysisStarted: "2026-06-15T06:00:00Z",
  analysisCompleted: null,
  errorMessage: null,
  resultMessage: null,
  analyzer: { id: "QW5hbHl6ZXJUeXBlOjE=", taskName: ENRICHMENT_TASK },
};

/** Unknown status + unknown task + non-JSON result + NaN timestamps. */
const oddballJob: EnrichmentAnalysisRow = {
  id: "QW5hbHlzaXNUeXBlOjc=",
  status: null, // statusVariant → neutral; StatusBadge → "unknown"
  analysisStarted: "not-a-date", // elapsedLabel → NaN → null → "—"
  analysisCompleted: "also-not-a-date",
  errorMessage: null,
  resultMessage: "{not valid json", // parseResultSummary catch → null → "—"
  analyzer: {
    id: "QW5hbHl6ZXJUeXBlOjk=",
    taskName: "opencontractserver.tasks.corpus_analysis_tasks.some_other_task",
  },
};

/** Long crawl: 10:00:00 → 10:02:07 = 127s → "2m 7s" (multi-minute format). */
const longCrawl: EnrichmentAnalysisRow = {
  id: "QW5hbHlzaXNUeXBlOjEw",
  status: "COMPLETED",
  analysisStarted: "2026-06-15T10:00:00Z",
  analysisCompleted: "2026-06-15T10:02:07Z",
  errorMessage: null,
  resultMessage: JSON.stringify({ authorities_ingested: 3 }),
  analyzer: { id: "QW5hbHl6ZXJUeXBlOjI=", taskName: CRAWL_TASK },
};

const ALL_JOBS = [
  completedEnrichment,
  failedEnrichment,
  runningCrawl,
  completedCrawl,
  queuedJob,
  createdJob,
  oddballJob,
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("EnrichmentJobList", () => {
  test("renders the loading state", async ({ mount, page }) => {
    const component = await mount(
      <EnrichmentJobListWrapper jobs={[]} loading={true} />
    );
    await expect(page.getByText("Loading enrichment jobs…")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toHaveCount(0);
    await component.unmount();
  });

  test("renders the error state", async ({ mount, page }) => {
    const error = { message: "GraphQL exploded" } as ApolloError;
    const component = await mount(
      <EnrichmentJobListWrapper jobs={[]} error={error} />
    );
    await expect(page.getByText("Error loading enrichment jobs")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("GraphQL exploded")).toBeVisible();
    await component.unmount();
  });

  test("renders the empty state when there are no jobs", async ({
    mount,
    page,
  }) => {
    const component = await mount(<EnrichmentJobListWrapper jobs={[]} />);
    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toContainText("No enrichment runs yet.");
    await expect(
      page.locator('[data-testid="enrichment-job-row"]')
    ).toHaveCount(0);
    await component.unmount();
  });

  test("renders every status / result / label / elapsed branch", async ({
    mount,
    page,
  }) => {
    const component = await mount(<EnrichmentJobListWrapper jobs={ALL_JOBS} />);

    const rows = page.locator('[data-testid="enrichment-job-row"]');
    await expect(rows).toHaveCount(ALL_JOBS.length, { timeout: 10000 });

    const list = page.locator('[data-testid="enrichment-job-list"]');

    // jobLabel branches: enrichment, crawl, and the raw-taskName fallback.
    await expect(list).toContainText("Reference enrichment");
    await expect(list).toContainText("Authority crawl");
    await expect(list).toContainText("some_other_task");

    // statusVariant / StatusBadge text branches (lower-cased; null → "unknown").
    const badges = page.locator('[data-testid="enrichment-job-status"]');
    const badgeTexts = (await badges.allInnerTexts()).map((t) =>
      t.trim().toLowerCase()
    );
    for (const expected of [
      "completed",
      "failed",
      "running",
      "queued",
      "created",
      "unknown",
    ]) {
      expect(badgeTexts).toContain(expected);
    }

    // parseResultSummary: enrichment branch + crawl branch.
    await expect(list).toContainText("42 refs · 38 linked");
    await expect(list).toContainText("7 ingested");

    // isFailed && errorMessage → ErrorCell renders the message.
    await expect(list).toContainText("boom: provider unreachable");

    // elapsedLabel computed-seconds branch (10:00:00 → 10:00:47 = 47s).
    await expect(list).toContainText("47s");
    // crawl completed in 12s.
    await expect(list).toContainText("12s");

    await component.unmount();
  });

  test("deduplicates optimistic rows already present in the fetched list", async ({
    mount,
    page,
  }) => {
    // completedEnrichment appears in both fetched jobs and extraJobs; the
    // fetched id wins, so only one row renders for it (one fetched + the
    // distinct optimistic runningCrawl = 2 rows total).
    const optimisticDuplicate: EnrichmentAnalysisRow = {
      ...completedEnrichment,
      status: "RUNNING",
    };
    const component = await mount(
      <EnrichmentJobListWrapper
        jobs={[completedEnrichment]}
        extraJobs={[optimisticDuplicate, runningCrawl]}
      />
    );

    const rows = page.locator('[data-testid="enrichment-job-row"]');
    await expect(rows).toHaveCount(2, { timeout: 10000 });

    // The fetched COMPLETED copy supersedes the optimistic RUNNING duplicate.
    const list = page.locator('[data-testid="enrichment-job-list"]');
    await expect(list).toContainText("completed");
    await expect(list).toContainText("Authority crawl");
    await component.unmount();
  });

  test("sorts rows newest-first by analysisStarted", async ({
    mount,
    page,
  }) => {
    // completedCrawl started 08:00, completedEnrichment started 10:00 → the
    // enrichment row must render before the crawl row.
    const component = await mount(
      <EnrichmentJobListWrapper jobs={[completedCrawl, completedEnrichment]} />
    );
    const rows = page.locator('[data-testid="enrichment-job-row"]');
    await expect(rows).toHaveCount(2, { timeout: 10000 });
    await expect(rows.first()).toContainText("Reference enrichment");
    await expect(rows.last()).toContainText("Authority crawl");
    await component.unmount();
  });

  test("formats multi-minute elapsed as 'Nm Ns' (not raw seconds)", async ({
    mount,
    page,
  }) => {
    // A 127-second crawl must read as "2m 7s", never the unscannable "127s".
    const component = await mount(
      <EnrichmentJobListWrapper jobs={[longCrawl]} />
    );
    const list = page.locator('[data-testid="enrichment-job-list"]');
    await expect(list).toBeVisible({ timeout: 10000 });
    await expect(list).toContainText("2m 7s");
    await expect(list).not.toContainText("127s");
    await component.unmount();
  });

  test("shows a truncation note when totalCount exceeds the fetched rows", async ({
    mount,
    page,
  }) => {
    // 1 fetched row but 73 total server-side → the older runs are truncated.
    const component = await mount(
      <EnrichmentJobListWrapper jobs={[completedEnrichment]} totalCount={73} />
    );
    const note = page.locator('[data-testid="enrichment-job-truncation"]');
    await expect(note).toBeVisible({ timeout: 10000 });
    await expect(note).toContainText("Showing the 1 most recent of 73 runs");
    await component.unmount();
  });

  test("hides the truncation note when totalCount fits the fetched rows", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <EnrichmentJobListWrapper
        jobs={[completedEnrichment, completedCrawl]}
        totalCount={2}
      />
    );
    await expect(
      page.locator('[data-testid="enrichment-job-list"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator('[data-testid="enrichment-job-truncation"]')
    ).toHaveCount(0);
    await component.unmount();
  });

  test("truncation count includes optimistic rows so it matches rendered rows", async ({
    mount,
    page,
  }) => {
    // 1 fetched + 1 distinct optimistic row → 2 rows rendered. The note must
    // count the rendered rows (2), not just the fetched ones (1), so "N most
    // recent" matches what the user sees on screen.
    const component = await mount(
      <EnrichmentJobListWrapper
        jobs={[completedEnrichment]}
        extraJobs={[runningCrawl]}
        totalCount={73}
      />
    );
    await expect(
      page.locator('[data-testid="enrichment-job-row"]')
    ).toHaveCount(2, { timeout: 10000 });
    const note = page.locator('[data-testid="enrichment-job-truncation"]');
    await expect(note).toContainText("Showing the 2 most recent of 73 runs");
    await component.unmount();
  });
});
