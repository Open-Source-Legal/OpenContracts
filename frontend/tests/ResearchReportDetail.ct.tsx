/**
 * Playwright component tests for the deep-research report detail view.
 *
 * Mounts ResearchReportDetail through ResearchReportDetailTestWrapper, which
 * seeds the openedResearchReport reactive var (as CentralRouteManager would)
 * and provides MockedProvider + Jotai + MemoryRouter. Terminal states only —
 * a running report would enable the completion WebSocket + polling, which the
 * wrapper intentionally avoids exercising here.
 */
import { test, expect } from "./utils/coverage";
import { ResearchReportDetailTestWrapper } from "./ResearchReportDetailTestWrapper";
import { buildMockReport } from "./ResearchReportDetailTestWrapper";
import { JobStatus } from "../src/types/graphql-api";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("ResearchReportDetail", () => {
  test("renders a completed report: title, status, stats, and body", async ({
    mount,
    page,
  }) => {
    const report = buildMockReport();
    await mount(<ResearchReportDetailTestWrapper report={report} />);

    await expect(
      page.locator("text=Indemnification Review").first()
    ).toBeVisible({ timeout: 15000 });
    // Status chip
    await expect(page.locator("text=Completed").first()).toBeVisible();
    // Stat tiles
    await expect(page.locator("text=Citations").first()).toBeVisible();
    await expect(page.locator("text=Sources").first()).toBeVisible();
    // Default Report tab renders the markdown body
    await expect(
      page.locator("text=several indemnification clauses").first()
    ).toBeVisible();

    await docScreenshot(page, "research--report-detail--completed");
  });

  test("citations tab lists the cited source text", async ({ mount, page }) => {
    const report = buildMockReport();
    await mount(<ResearchReportDetailTestWrapper report={report} />);

    await expect(
      page.locator("text=Indemnification Review").first()
    ).toBeVisible({ timeout: 15000 });

    // Switch to the Citations tab (label carries the count; the stat tile does not)
    await page.locator("text=Citations (1)").first().click();
    await expect(
      page.locator("text=indemnify and hold harmless").first()
    ).toBeVisible({ timeout: 10000 });
  });

  test("renders a failed report with its error message", async ({
    mount,
    page,
  }) => {
    const report = buildMockReport({
      status: JobStatus.Failed,
      content: "",
      errorMessage: "Model timed out",
    });
    await mount(<ResearchReportDetailTestWrapper report={report} />);

    await expect(page.locator("text=Research failed").first()).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator("text=Model timed out").first()).toBeVisible();
  });
});
