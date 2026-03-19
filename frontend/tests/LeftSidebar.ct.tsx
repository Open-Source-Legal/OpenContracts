import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import {
  TabsColumn,
  TabButton,
} from "../src/components/knowledge_base/document/styled/LeftSidebar";
import { FileText, MessageSquare, Tag, Search } from "lucide-react";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("LeftSidebar styled components", () => {
  test("TabsColumn renders expanded state", async ({ mount, page }) => {
    const component = await mount(
      <TabsColumn collapsed={false}>
        <TabButton $collapsed={false} $tabKey="document" $active={true}>
          <FileText />
          <span>Document</span>
        </TabButton>
        <TabButton $collapsed={false} $tabKey="chat" $active={false}>
          <MessageSquare />
          <span>Chat</span>
        </TabButton>
        <TabButton $collapsed={false} $tabKey="annotations" $active={false}>
          <Tag />
          <span>Annotations</span>
        </TabButton>
        <TabButton $collapsed={false} $tabKey="search" $active={false}>
          <Search />
          <span>Search</span>
        </TabButton>
      </TabsColumn>
    );

    // Tab text should be visible in expanded mode
    await expect(page.locator("text=Document")).toBeVisible();
    await expect(page.locator("text=Chat")).toBeVisible();
    await expect(page.locator("text=Annotations")).toBeVisible();
    await expect(page.locator("text=Search")).toBeVisible();

    await docScreenshot(page, "sidebar--tabs-column--expanded", {
      element: component,
    });

    await component.unmount();
  });

  test("TabsColumn renders collapsed state", async ({ mount, page }) => {
    const component = await mount(
      <TabsColumn collapsed={true}>
        <TabButton $collapsed={true} $tabKey="document" $active={true}>
          <FileText />
          <span>Document</span>
        </TabButton>
        <TabButton $collapsed={true} $tabKey="chat" $active={false}>
          <MessageSquare />
          <span>Chat</span>
        </TabButton>
      </TabsColumn>
    );

    // In collapsed mode, text should have opacity 0
    const docSpan = page.locator("span").filter({ hasText: "Document" });
    await expect(docSpan).toHaveCSS("opacity", "0");

    await docScreenshot(page, "sidebar--tabs-column--collapsed", {
      element: component,
    });

    await component.unmount();
  });

  test("TabButton shows active indicator", async ({ mount, page }) => {
    const component = await mount(
      <div style={{ width: "280px" }}>
        <TabButton $collapsed={false} $tabKey="document" $active={true}>
          <FileText />
          <span>Document</span>
        </TabButton>
        <TabButton $collapsed={false} $tabKey="chat" $active={false}>
          <MessageSquare />
          <span>Chat</span>
        </TabButton>
      </div>
    );

    // Active tab should have a different background
    const activeButton = page.locator("button").first();
    const bgColor = await activeButton.evaluate(
      (el) => window.getComputedStyle(el).background
    );
    // Active button should have a tinted background
    expect(bgColor).not.toBe("rgba(0, 0, 0, 0)");

    await docScreenshot(page, "sidebar--tab-button--active", {
      element: component,
    });

    await component.unmount();
  });

  test("TabButton responds to click", async ({ mount, page }) => {
    let clicked = false;
    const component = await mount(
      <div style={{ width: "280px" }}>
        <TabButton
          $collapsed={false}
          $tabKey="document"
          $active={false}
          onClick={() => {
            clicked = true;
          }}
        >
          <FileText />
          <span>Document</span>
        </TabButton>
      </div>
    );

    await page.locator("button").click();
    expect(clicked).toBe(true);

    await component.unmount();
  });
});
