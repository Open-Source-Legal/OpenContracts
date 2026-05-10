import React from "react";
import { test, expect } from "./utils/coverage";
import { SidebarTabsHarness } from "./SidebarTabsTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import { AnalysisType, ExtractType } from "../src/types/graphql-api";

const fakeAnalysis = {
  id: "analysis-1",
  analysisStarted: null,
  analysisCompleted: null,
  status: "COMPLETED",
} as unknown as AnalysisType;

const fakeExtract = {
  id: "extract-1",
  name: "Demo Extract",
  started: null,
  finished: null,
} as unknown as ExtractType;

test.describe("DesktopSidebarTabs", () => {
  test("renders Index, Chat, Feed and Discussions when no analysis/extract selected", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SidebarTabsHarness variant="desktop" panelOpen={false} />
    );

    await expect(page.getByTestId("view-mode-index")).toBeVisible();
    await expect(page.getByTestId("view-mode-chat")).toBeVisible();
    await expect(page.getByTestId("view-mode-feed")).toBeVisible();
    await expect(page.getByTestId("view-mode-discussions")).toBeVisible();
    // Extract / Analysis tabs hidden when neither is selected.
    await expect(page.getByTestId("view-mode-extract")).toHaveCount(0);
    await expect(page.getByTestId("view-mode-analysis")).toHaveCount(0);

    await docScreenshot(page, "knowledge-base--desktop-sidebar-tabs--default");

    await component.unmount();
  });

  test("shows Extract and Analysis tabs only when selectedExtract / selectedAnalysis are set", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SidebarTabsHarness
        variant="desktop"
        panelOpen={true}
        selectedAnalysis={fakeAnalysis}
        selectedExtract={fakeExtract}
        threadCount={3}
      />
    );

    await expect(page.getByTestId("view-mode-extract")).toBeVisible();
    await expect(page.getByTestId("view-mode-analysis")).toBeVisible();

    // Discussion badge renders when threadCount > 0.
    const discussions = page.getByTestId("view-mode-discussions");
    await expect(discussions).toContainText("3");

    await docScreenshot(
      page,
      "knowledge-base--desktop-sidebar-tabs--with-extract-analysis"
    );

    await component.unmount();
  });

  test("clicking a tab while panel is closed switches view and opens the panel", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SidebarTabsHarness variant="desktop" panelOpen={false} />
    );

    await expect(page.getByTestId("active-mode")).toHaveText("index");
    await expect(page.getByTestId("panel-open")).toHaveText("closed");

    await page.getByTestId("view-mode-chat").click();

    await expect(page.getByTestId("active-mode")).toHaveText("chat");
    await expect(page.getByTestId("panel-open")).toHaveText("open");

    await component.unmount();
  });

  test("clicking the active tab while panel is open closes the panel", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SidebarTabsHarness
        variant="desktop"
        panelOpen={true}
        initialMode="index"
        initialShowRightPanel={true}
      />
    );

    await expect(page.getByTestId("panel-open")).toHaveText("open");

    await page.getByTestId("view-mode-index").click();

    await expect(page.getByTestId("panel-open")).toHaveText("closed");
    await expect(page.getByTestId("active-mode")).toHaveText("index");

    await component.unmount();
  });
});

test.describe("MobileSidebarTabs", () => {
  // MobileTabBar is hidden by CSS (`display: none`) above 768px viewport.
  test.use({ viewport: { width: 480, height: 800 } });

  test("renders mobile tab bar with default view-mode tabs", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SidebarTabsHarness variant="mobile" initialShowRightPanel={true} />
    );

    await expect(page.getByTestId("mobile-view-mode-index")).toBeVisible();
    await expect(page.getByTestId("mobile-view-mode-chat")).toBeVisible();
    await expect(page.getByTestId("mobile-view-mode-feed")).toBeVisible();

    await docScreenshot(page, "knowledge-base--mobile-sidebar-tabs--default");

    await component.unmount();
  });

  test("threadCount > 0 surfaces the count in the discussions label", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SidebarTabsHarness
        variant="mobile"
        initialShowRightPanel={true}
        threadCount={5}
      />
    );

    const discussions = page.locator('[aria-label="Document discussions"]');
    await expect(discussions).toContainText("(5)");

    await component.unmount();
  });

  test("clicking inactive tab switches view (panel stays as-is)", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SidebarTabsHarness
        variant="mobile"
        initialMode="index"
        initialShowRightPanel={true}
      />
    );

    await page.getByTestId("mobile-view-mode-feed").click();
    await expect(page.getByTestId("active-mode")).toHaveText("feed");

    await component.unmount();
  });
});
