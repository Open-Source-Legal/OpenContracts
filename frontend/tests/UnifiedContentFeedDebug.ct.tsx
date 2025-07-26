import { test, expect } from "@playwright/experimental-ct-react";
import { UnifiedContentFeedTestWrapper } from "./UnifiedContentFeedTestWrapper";
import {
  ContentFilters,
  ContentItemType,
} from "../src/components/knowledge_base/document/unified_feed/types";
import React from "react";
import {
  DebugComponentForFilters,
  UnifiedContentFeedWithDebugAtoms,
  TestComponentWithRenderTracking,
  UnifiedContentFeedWithDebugFilters,
} from "./UnifiedContentFeedDebug.story";

test.describe("UnifiedContentFeed - Debug", () => {
  test("debug atom initialization", async ({ mount, page }) => {
    // Enable console logging
    page.on("console", (msg) => {
      if (msg.text().includes("DEBUG")) {
        console.log(msg.text());
      }
    });

    const mockAnnotations = [
      {
        id: "ann-1",
        page: 1,
        text_extraction: { text: "Test annotation text" },
        annotation_label: { text: "Important", color: "#ff0000" },
        created: new Date().toISOString(),
        __typename: "ServerTokenAnnotation",
      },
    ];

    const component = await mount(
      <UnifiedContentFeedWithDebugAtoms
        notes={[]}
        mockAnnotations={mockAnnotations}
      />
    );

    // Wait for component to render and atoms to initialize
    await page.waitForTimeout(1000);

    // Check if annotation text appears
    const annotationVisible = await page
      .locator("text=Test annotation text")
      .isVisible()
      .catch(() => false);

    console.log("Annotation visible:", annotationVisible);

    // Check console logs for atom values
    expect(true).toBe(true); // Dummy assertion - check console output
  });

  test("debug filter timing", async ({ mount, page }) => {
    const component = await mount(<TestComponentWithRenderTracking />);

    // Wait for renders
    await page.waitForTimeout(500);

    // Check if note appears
    const noteVisible = await page
      .locator("text=Test Note 1")
      .isVisible()
      .catch(() => false);

    console.log("Note visible:", noteVisible);

    // Get render count from the DOM element
    const renderCountElement = await page
      .locator('[data-testid="render-count"]')
      .textContent();
    console.log("Total renders:", renderCountElement);
  });

  test("debug filter application", async ({ mount, page }) => {
    // Enable console logging
    page.on("console", (msg) => {
      console.log("Browser:", msg.text());
    });

    const notesOnlyFilters: ContentFilters = {
      contentTypes: new Set<ContentItemType>(["note"]),
      annotationFilters: {
        showStructural: false,
      },
      relationshipFilters: {
        showStructural: false,
      },
      searchQuery: "",
    };

    const notes = [
      {
        id: "1",
        title: "Test Note 1",
        content: "This is the first test note",
        created: new Date().toISOString(),
        creator: {
          email: "test@example.com",
        },
      },
    ];

    const component = await mount(
      <UnifiedContentFeedWithDebugFilters
        notes={notes}
        filters={notesOnlyFilters}
      />
    );

    // Wait for initialization
    await page.waitForTimeout(1000);

    // Check what's rendered - either feed or empty state
    const feedVisible = await page
      .locator('[data-testid="unified-content-feed"]')
      .isVisible()
      .catch(() => false);

    const emptyVisible = await page
      .locator('[data-testid="unified-content-feed-empty"]')
      .isVisible()
      .catch(() => false);

    console.log("Feed visible:", feedVisible);
    console.log("Empty state visible:", emptyVisible);

    // If feed is visible, check content
    if (feedVisible) {
      const feedContent = await page
        .locator('[data-testid="unified-content-feed"]')
        .textContent();
      console.log("Feed content:", feedContent);
    }

    // Check if note is visible
    const noteVisible = await page
      .locator("text=Test Note 1")
      .isVisible()
      .catch(() => false);

    console.log("Note visible:", noteVisible);

    // Log the entire page content to debug
    const bodyContent = await page.locator("body").innerHTML();
    console.log(
      "Body contains Test Note 1:",
      bodyContent.includes("Test Note 1")
    );
    console.log(
      "Body contains empty state:",
      bodyContent.includes("No content found")
    );
  });

  test("minimal test with custom filters", async ({ mount, page }) => {
    // Enable error logging
    page.on("pageerror", (error) => {
      console.error("Page error:", error.message);
      console.error("Stack:", error.stack);
    });

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        console.error("Console error:", msg.text());
      }
    });

    try {
      // Try mounting with custom filters
      const component = await mount(
        <UnifiedContentFeedTestWrapper
          filters={{
            contentTypes: new Set(["note"]),
            annotationFilters: {
              showStructural: false,
            },
            relationshipFilters: {
              showStructural: false,
            },
            searchQuery: "",
          }}
        />
      );

      // Wait a bit
      await page.waitForTimeout(500);

      // Check if anything rendered
      const rootContent = await page.locator("#root").innerHTML();
      console.log("Root content:", rootContent);

      const bodyContent = await page.locator("body").innerHTML();
      console.log(
        "Body contains UnifiedContentFeed:",
        bodyContent.includes("unified-content-feed")
      );
    } catch (error) {
      console.error("Mount error:", error);
    }
  });

  test("debug what filters are received", async ({ mount, page }) => {
    const filters = {
      contentTypes: new Set(["note"]),
      annotationFilters: {
        showStructural: false,
      },
      relationshipFilters: {
        showStructural: false,
      },
      searchQuery: "",
    };

    console.log("Filters before mount:", filters);
    console.log("contentTypes before mount:", filters.contentTypes);

    await mount(<DebugComponentForFilters filters={filters} />);

    await page.waitForTimeout(100);
  });
});
