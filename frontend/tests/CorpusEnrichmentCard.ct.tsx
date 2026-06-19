/**
 * Component tests for CorpusEnrichmentCard.
 *
 * The card composes EnrichmentRunner + EnrichmentJobList and is gated on the
 * caller-supplied `canUpdate` permission. Two behaviours are pinned here:
 *   1. Read-only visitors (canUpdate=false) see nothing rendered.
 *   2. Editors (canUpdate=true) see the enrichment card + job list.
 *
 * useEnrichmentJobs fires GET_CORPUS_ANALYSES on mount *regardless* of
 * canUpdate (the early `return null` happens after the hook call), so both
 * cases supply the list mock.
 *
 * The JSX wrapper import is kept in its own statement, separate from the helper
 * imports below, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";

import { CorpusEnrichmentCardWrapper } from "./CorpusEnrichmentCardWrapper";

import { docScreenshot } from "./utils/docScreenshot";
import { GET_CORPUS_ANALYSES } from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTo0Mg==";

// Inline copy of ENRICHMENT_TASK_NAMES (see EnrichmentRunner.ct.tsx for why the
// hook module cannot be imported directly from a CT test file).
const ENRICHMENT_TASK_NAMES = [
  "opencontractserver.tasks.corpus_analysis_tasks.corpus_reference_enrichment",
  "opencontractserver.tasks.corpus_analysis_tasks.crawl_authorities",
];

const QUERY_VARS = {
  corpusId: CORPUS_ID,
  statusExact: null,
  taskNames: ENRICHMENT_TASK_NAMES,
};

/** Empty job list — useEnrichmentJobs' on-mount fetch. */
const EMPTY_QUERY_MOCK = {
  request: { query: GET_CORPUS_ANALYSES, variables: QUERY_VARS },
  result: { data: { analyses: { edges: [] } } },
  maxUsageCount: 10,
};

test.describe("CorpusEnrichmentCard", () => {
  test("renders nothing for read-only visitors (canUpdate=false)", async ({
    mount,
  }) => {
    const component = await mount(
      <CorpusEnrichmentCardWrapper
        corpusId={CORPUS_ID}
        canUpdate={false}
        mocks={[EMPTY_QUERY_MOCK]}
      />
    );
    await expect(component.getByTestId("corpus-enrichment-card")).toHaveCount(
      0
    );
  });

  test("renders the enrichment card for editors (canUpdate=true)", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusEnrichmentCardWrapper
        corpusId={CORPUS_ID}
        canUpdate={true}
        mocks={[EMPTY_QUERY_MOCK]}
      />
    );
    const card = component.getByTestId("corpus-enrichment-card");
    await expect(card).toBeVisible();
    await expect(card).toContainText("Reference enrichment");

    await docScreenshot(page, "corpus--enrichment-card--editor");
  });
});
