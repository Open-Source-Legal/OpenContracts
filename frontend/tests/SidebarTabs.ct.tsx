import React from "react";
import { test, expect } from "./utils/coverage";
import {
  RightEdgeRailHarness,
  SidebarTabsHarness,
} from "./SidebarTabsTestWrapper";
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

  test("each tab carries an accessible name and tooltip data", async ({
    mount,
    page,
  }) => {
    await mount(
      <SidebarTabsHarness
        variant="desktop"
        panelOpen={false}
        selectedAnalysis={fakeAnalysis}
        selectedExtract={fakeExtract}
        threadCount={2}
      />
    );

    // Every tab must announce something to screen readers and carry the
    // tooltip data attribute (replacing the rotated text labels called out
    // in issue #1734). `data-tooltip` powers the CSS-only hover popup.
    const expected: Array<[string, string, string]> = [
      ["view-mode-index", "Document index", "Index"],
      ["view-mode-chat", "Chat with this document", "Chat"],
      ["view-mode-feed", "Annotation feed", "Feed"],
      ["view-mode-extract", "Extract results", "Extract"],
      ["view-mode-analysis", "Analysis results", "Analysis"],
      [
        "view-mode-discussions",
        "Document discussions, 2 threads",
        "Discussions (2)",
      ],
    ];

    for (const [testId, ariaLabel, tooltip] of expected) {
      const tab = page.getByTestId(testId);
      await expect(tab).toBeVisible();
      await expect(tab).toHaveAttribute("aria-label", ariaLabel);
      await expect(tab).toHaveAttribute("data-tooltip", tooltip);
    }
  });

  test("discussions tab uses the singular thread form when threadCount is 1", async ({
    mount,
    page,
  }) => {
    // Pluralization edge case: threadCount={1} should announce "1 thread"
    // not "1 threads". Pinned as its own test so the conditional in
    // SidebarTabs.tsx stays a regression-guarded path.
    await mount(<SidebarTabsHarness variant="desktop" threadCount={1} />);

    const tab = page.getByTestId("view-mode-discussions");
    await expect(tab).toHaveAttribute(
      "aria-label",
      "Document discussions, 1 thread"
    );
    await expect(tab).toHaveAttribute("data-tooltip", "Discussions (1)");
  });

  test("tab labels are visually hidden but in the DOM for screen readers", async ({
    mount,
    page,
  }) => {
    await mount(<SidebarTabsHarness variant="desktop" panelOpen={false} />);

    // The .tab-label spans must remain so screen readers and string-matching
    // tests still see "Index", "Chat", etc., but they must NOT be visible —
    // the visible affordance is the icon + tooltip. This guards against a
    // regression where someone re-introduces the rotated text rail.
    const indexTab = page.getByTestId("view-mode-index");
    const label = indexTab.locator(".tab-label");

    // The span is in the DOM with the expected text…
    await expect(label).toHaveText("Index");
    // …and the surrounding tab does not visibly display it (its bounding box
    // collapses to the 1x1 clipped sr-only style).
    const labelBox = await label.boundingBox();
    expect(labelBox).not.toBeNull();
    expect((labelBox?.width ?? 0) <= 2).toBe(true);
    expect((labelBox?.height ?? 0) <= 2).toBe(true);
  });
});

/**
 * Visual coverage for the unified right-edge rail (issue #1734) — navigation
 * tabs + document tool pills consolidated into one coherent vertical column
 * with consistent affordances and no rotated text.
 */
test.describe("RightEdgeRail (issue #1734)", () => {
  test("renders the consolidated navigation tabs + tool pills in one column", async ({
    mount,
    page,
  }) => {
    await mount(<RightEdgeRailHarness threadCount={2} />);

    // The rail contains all four navigation tabs…
    await expect(page.getByTestId("view-mode-index")).toBeVisible();
    await expect(page.getByTestId("view-mode-chat")).toBeVisible();
    await expect(page.getByTestId("view-mode-feed")).toBeVisible();
    await expect(page.getByTestId("view-mode-discussions")).toBeVisible();

    // …and the four document-tool pills, all rendered inside the same rail.
    const rail = page.getByTestId("right-edge-rail");
    await expect(
      rail.getByRole("button", { name: "Annotation filters" })
    ).toBeVisible();
    await expect(
      rail.getByRole("button", { name: "View extracts" })
    ).toBeVisible();
    await expect(
      rail.getByRole("button", { name: "View analyses" })
    ).toBeVisible();
    await expect(
      rail.getByRole("button", { name: "Start new analysis" })
    ).toBeVisible();

    await docScreenshot(page, "knowledge-base--right-edge-rail--unified");
  });

  test("rail extends to include Extract + Analysis when selections are active", async ({
    mount,
    page,
  }) => {
    await mount(<RightEdgeRailHarness withSelections threadCount={5} />);

    await expect(page.getByTestId("view-mode-extract")).toBeVisible();
    await expect(page.getByTestId("view-mode-analysis")).toBeVisible();
    await expect(page.getByTestId("view-mode-discussions")).toContainText("5");

    await docScreenshot(
      page,
      "knowledge-base--right-edge-rail--with-extract-analysis"
    );
  });

  test("read-only flavor: rail structural contract hides create pill (harness, not FloatingDocumentControls gating)", async ({
    mount,
    page,
  }) => {
    // NOTE: this exercises the harness's structural rendering, not the real
    // FloatingDocumentControls permission gate (canCreateAnalysis && !readOnly
    // && selectedCorpus). The harness avoids Apollo/Jotai setup; production
    // permission gating is covered by FloatingDocumentControls.ct.tsx.
    await mount(<RightEdgeRailHarness canCreateAnalysis={false} />);

    const rail = page.getByTestId("right-edge-rail");
    await expect(
      rail.getByRole("button", { name: "Start new analysis" })
    ).toHaveCount(0);

    // The other tools remain reachable so view-only users can still inspect
    // existing analyses / extracts.
    await expect(
      rail.getByRole("button", { name: "View extracts" })
    ).toBeVisible();
    await expect(
      rail.getByRole("button", { name: "View analyses" })
    ).toBeVisible();

    await docScreenshot(page, "knowledge-base--right-edge-rail--read-only");
  });
});
