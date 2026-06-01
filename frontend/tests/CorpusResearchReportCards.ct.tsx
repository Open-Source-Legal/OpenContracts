/**
 * Playwright component test for the corpus "Research" tab list
 * (CorpusResearchReportCards).
 *
 * Smoke-level: mounts the component with the openedCorpus reactive var seeded
 * (as CentralRouteManager would) and a MockedProvider for the GET_RESEARCH_REPORTS
 * connection, then asserts the query wires up and the empty state renders.
 *
 * A populated-list assertion was intentionally NOT added here: the component's
 * `network-only` query re-fires across re-renders, which MockedProvider can't
 * serve deterministically in isolation (the mock bucket drains and the query
 * resolves empty). The card visuals are covered directly by
 * ResearchReportListCard.ct.tsx (with its own docScreenshot), so the meaningful
 * UI unit is already exercised + captured.
 */
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
// Component import isolated (Playwright CT split-import rule, CLAUDE.md #16).
import { CorpusResearchReportCardsTestWrapper } from "./CorpusResearchReportCardsTestWrapper";

test.describe("CorpusResearchReportCards", () => {
  test("mounts and shows the empty state when the corpus has no reports", async ({
    mount,
    page,
  }) => {
    await mount(<CorpusResearchReportCardsTestWrapper nodes={[]} />);

    await expect(page.getByText("No research yet")).toBeVisible({
      timeout: 15000,
    });

    await docScreenshot(page, "research--corpus-report-cards--empty");
  });
});
