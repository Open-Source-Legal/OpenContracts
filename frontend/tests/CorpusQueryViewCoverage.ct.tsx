/**
 * Direct-mount coverage tests for the extracted CorpusQueryView component.
 *
 * Drives the navigation-header, VIEW state, and null-corpus branches without
 * the heavyweight Corpuses harness — those code paths aren't reached by the
 * tab-navigation tests in CorpusTabs.ct.tsx because that suite never sets
 * `showQueryViewState("VIEW")` ahead of mount.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { CorpusQueryViewTestWrapper } from "./CorpusQueryViewTestWrapper";
import { CorpusType } from "../src/types/graphql-api";
import { showQueryViewState } from "../src/graphql/cache";
import { docScreenshot } from "./utils/docScreenshot";

const buildCorpus = (overrides: Partial<CorpusType> = {}): CorpusType =>
  ({
    id: "CORPUS_QV_1",
    title: "Query View Corpus",
    icon: null,
    isPublic: false,
    description: "",
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    creator: {
      id: "U1",
      email: "u@x.test",
      username: "tester",
      slug: "tester",
      __typename: "UserType",
    },
    labelSet: null,
    parent: null,
    allowComments: true,
    preferredEmbedder: null,
    appliedAnalyzerIds: [],
    myPermissions: ["read_corpus"] as unknown as string[],
    analyses: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo",
      },
      totalCount: 0,
      __typename: "AnalysisTypeConnection",
    },
    annotations: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo",
      },
      totalCount: 0,
      __typename: "AnnotationTypeConnection",
    },
    documents: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo",
      },
      totalCount: 0,
      __typename: "DocumentTypeConnection",
    },
    __typename: "CorpusType",
    ...overrides,
  } as unknown as CorpusType);

test.describe("CorpusQueryView - direct mount", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test.afterEach(() => {
    showQueryViewState("ASK");
  });

  test("renders 'No corpus selected' placeholder when opened_corpus is null", async ({
    mount,
    page,
  }) => {
    await mount(<CorpusQueryViewTestWrapper opened_corpus={null} />);
    await expect(page.getByText("No corpus selected")).toBeVisible({
      timeout: 5000,
    });
  });

  test("VIEW state renders 'Conversation History' navigation header on desktop", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusQueryViewTestWrapper
        opened_corpus={buildCorpus()}
        initialQueryViewState="VIEW"
      />
    );
    await expect(page.getByText("Conversation History").first()).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Back to Dashboard").first()).toBeVisible();

    await docScreenshot(page, "corpus--query-view--conversation-history");
  });

  test("clicking Back to Dashboard in VIEW state switches reactive var to ASK", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusQueryViewTestWrapper
        opened_corpus={buildCorpus()}
        initialQueryViewState="VIEW"
      />
    );
    const back = page.getByText("Back to Dashboard").first();
    await expect(back).toBeVisible({ timeout: 10000 });
    await back.click();
    // The header should disappear once state flips to ASK (and chatExpanded
    // remains false).
    await expect(page.getByText("Conversation History")).not.toBeVisible({
      timeout: 5000,
    });
  });

  test("VIEW state offers a Home action button to return to Dashboard", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusQueryViewTestWrapper
        opened_corpus={buildCorpus()}
        initialQueryViewState="VIEW"
      />
    );
    // Both action buttons in the VIEW header are titled — assert the Dashboard
    // one is present (renders the lucide Home icon path).
    await expect(page.locator('[title="Return to Dashboard"]')).toBeVisible({
      timeout: 10000,
    });
  });

  test("clicking Home button in VIEW state flips reactive var to ASK", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusQueryViewTestWrapper
        opened_corpus={buildCorpus()}
        initialQueryViewState="VIEW"
      />
    );
    const homeBtn = page.locator('[title="Return to Dashboard"]');
    await expect(homeBtn).toBeVisible({ timeout: 10000 });
    await homeBtn.click();
    // After click, the VIEW header text disappears (reactive var flipped to
    // ASK and the dashboard branch renders instead).
    await expect(page.getByText("Conversation History")).not.toBeVisible({
      timeout: 5000,
    });
  });

  test("ASK state with a corpus renders the dashboard container", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusQueryViewTestWrapper
        opened_corpus={buildCorpus()}
        initialQueryViewState="ASK"
      />
    );
    // Dashboard branch renders a container with id="corpus-dashboard-container".
    await expect(page.locator("#corpus-dashboard-container")).toBeVisible({
      timeout: 10000,
    });
  });
});

test.describe("CorpusQueryView - mobile viewport", () => {
  test.use({ viewport: { width: 375, height: 667 } });
  test.setTimeout(30000);

  test.afterEach(() => {
    showQueryViewState("ASK");
  });

  test("VIEW state navigation header is suppressed on mobile", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusQueryViewTestWrapper
        opened_corpus={buildCorpus()}
        initialQueryViewState="VIEW"
      />
    );
    // CorpusChat owns its own header on mobile, so the outer
    // "Conversation History" wrapper should not render.
    await expect(page.getByText("Conversation History")).not.toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("Back to Dashboard")).not.toBeVisible({
      timeout: 5000,
    });
  });
});
