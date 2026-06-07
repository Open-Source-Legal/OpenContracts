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
import { toGlobalId } from "../src/utils/idValidation";
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

    // The citation deep-link must carry the annotation's canonical global ID
    // (ServerAnnotationType, from fullSourceAnnotationList), NOT a reconstructed
    // "AnnotationType" id — otherwise the annotation deep-link resolves to the
    // wrong entity. Regression guard for the typename-mismatch fix.
    const citationLink = page
      .locator("a", { hasText: "indemnify and hold harmless" })
      .first();
    const href = await citationLink.getAttribute("href");
    expect(href).toBeTruthy();
    const annParam = new URL(
      href as string,
      "http://localhost"
    ).searchParams.get("ann");
    expect(annParam).toBe(toGlobalId("ServerAnnotationType", 10));

    await docScreenshot(page, "research--report-detail--citations");
  });

  test("report-body footnotes deep-link to the cited source", async ({
    mount,
    page,
  }) => {
    const report = buildMockReport();
    await mount(<ResearchReportDetailTestWrapper report={report} />);

    await expect(
      page.locator("text=Indemnification Review").first()
    ).toBeVisible({ timeout: 15000 });

    // The default Report tab renders the markdown body, whose ``## Sources``
    // footnote definition (``[^1]: Doc A page 2``) must become a click-to-source
    // target. Clicking it navigates to the cited document with the cited
    // annotation selected (``?ann=<canonical global id>``).
    const footnote = page.locator('li[id="user-content-fn-1"]');
    await expect(footnote).toBeVisible({ timeout: 10000 });
    await expect(footnote).toHaveAttribute("role", "link");

    await footnote.click();

    // MemoryRouter doesn't touch window.location, so read the navigated path
    // from the wrapper's hidden location probe.
    const probe = page.getByTestId("router-location");
    await expect
      .poll(async () => {
        const loc = (await probe.textContent()) ?? "";
        return new URL(loc, "http://localhost").pathname;
      })
      .toBe("/d/john/cases/doc-a");
    const loc = (await probe.textContent()) ?? "";
    const annParam = new URL(loc, "http://localhost").searchParams.get("ann");
    expect(annParam).toBe(toGlobalId("ServerAnnotationType", 10));
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
