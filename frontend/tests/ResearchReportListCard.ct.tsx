import React from "react";
import { test, expect } from "./utils/coverage";
import { MemoryRouter } from "react-router-dom";
import { JobStatus, ResearchReportListItem } from "../src/types/graphql-api";
import { toGlobalId } from "../src/utils/idValidation";
import { docScreenshot } from "./utils/docScreenshot";
// Component import kept in its own statement (Playwright CT split-import rule,
// CLAUDE.md pitfall #16) so the babel transform rewrites the JSX reference.
import { ResearchReportListCard } from "../src/components/research/ResearchReportListCard";

/** Minimal list-item fixture; override fields for other states. */
function makeListItem(
  overrides: Partial<ResearchReportListItem> = {}
): ResearchReportListItem {
  return {
    id: toGlobalId("ResearchReportType", 1),
    title: "Indemnification Review",
    slug: "indemnification-review",
    status: JobStatus.Completed,
    durationSeconds: 125,
    stepCount: 12,
    maxSteps: 60,
    created: "2026-05-28T12:00:00Z",
    corpus: {
      id: toGlobalId("CorpusType", 1),
      slug: "cases",
      creator: { id: toGlobalId("UserType", 1), slug: "john" },
    },
    ...overrides,
  } as ResearchReportListItem;
}

test.describe("ResearchReportListCard", () => {
  test("renders a completed report's title, status, and run duration", async ({
    mount,
    page,
  }) => {
    await mount(
      <MemoryRouter>
        <ResearchReportListCard report={makeListItem()} />
      </MemoryRouter>
    );

    await expect(page.getByText("Indemnification Review")).toBeVisible();
    // Completed reports surface a "Ran <duration>" stat (not a step counter).
    await expect(page.getByText(/Ran /)).toBeVisible();

    await docScreenshot(page, "research--report-list-card--completed");
  });

  test("running report shows a step counter instead of duration", async ({
    mount,
    page,
  }) => {
    await mount(
      <MemoryRouter>
        <ResearchReportListCard
          report={makeListItem({
            status: JobStatus.Running,
            stepCount: 3,
            maxSteps: 60,
          })}
        />
      </MemoryRouter>
    );

    await expect(page.getByText("Step 3 of 60")).toBeVisible();
  });
});
