/**
 * Component tests for CorpusEnrichmentCard.
 *
 * The card composes EnrichmentRunner + EnrichmentJobList and is gated on the
 * caller-supplied `canUpdate` permission. Two behaviours are pinned here:
 *   1. Read-only visitors (canUpdate=false) see nothing rendered.
 *   2. Editors (canUpdate=true) see the enrichment card + job list.
 *
 * The data hook lives in an inner component mounted only when canUpdate=true,
 * so read-only visitors never fire GET_CORPUS_ANALYSES — that case supplies no
 * mock, and a regression that fired the query would surface as an unmatched
 * MockedProvider request.
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
  result: { data: { analyses: { totalCount: 0, edges: [] } } },
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
        mocks={[]}
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
