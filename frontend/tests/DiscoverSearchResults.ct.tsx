// Playwright Component Tests for DiscoverSearchResults (cross-content discover search).
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { DiscoverSearchResults } from "../src/views/DiscoverSearchResults";
import { LandingTestWrapper } from "./LandingTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import {
  DISCOVER_DISCUSSIONS,
  DISCOVER_ANNOTATIONS,
  DISCOVER_DOCUMENTS,
  DISCOVER_CORPUSES,
  DISCOVER_NOTES,
} from "../src/graphql/queries";

// Discover queries return flat, relevance-ranked arrays (no Relay edges) and
// take { textSearch, limit }. All-tab previews use limit=5; entity tabs use 25.

const buildEmptyMocks = (textSearch: string, limit = 5): MockedResponse[] => [
  {
    request: { query: DISCOVER_DISCUSSIONS, variables: { textSearch, limit } },
    result: { data: { discoverDiscussions: [] } },
  },
  {
    request: { query: DISCOVER_ANNOTATIONS, variables: { textSearch, limit } },
    result: { data: { discoverAnnotations: [] } },
  },
  {
    request: { query: DISCOVER_DOCUMENTS, variables: { textSearch, limit } },
    result: { data: { discoverDocuments: [] } },
  },
  {
    request: { query: DISCOVER_CORPUSES, variables: { textSearch, limit } },
    result: { data: { discoverCorpuses: [] } },
  },
  {
    request: { query: DISCOVER_NOTES, variables: { textSearch, limit } },
    result: { data: { discoverNotes: [] } },
  },
];

const THREAD_NODE = {
  id: "Q29udjox",
  conversationType: "THREAD",
  title: "Indemnity caps in vendor MSAs",
  description: "How aggressive are folks getting on caps?",
  createdAt: "2026-04-01T12:00:00Z",
  updatedAt: "2026-04-02T12:00:00Z",
  creator: {
    id: "VXNlcjox",
    slug: "alice",
    username: "alice",
    email: "alice@example.com",
  },
  chatWithCorpus: {
    id: "Q29ycHVzOjE=",
    title: "Vendor Agreements",
    slug: "vendor-agreements",
    creator: { id: "VXNlcjox", slug: "alice", username: "alice" },
  },
  chatWithDocument: null,
  chatMessages: { totalCount: 12 },
  isPublic: true,
  myPermissions: ["READ"],
  upvoteCount: 3,
  downvoteCount: 0,
  userVote: null,
  isLocked: false,
  lockedBy: null,
  lockedAt: null,
  isPinned: false,
  pinnedBy: null,
  pinnedAt: null,
  deletedAt: null,
};

const buildPopulatedMocks = (textSearch: string): MockedResponse[] => [
  {
    request: {
      query: DISCOVER_DISCUSSIONS,
      variables: { textSearch, limit: 5 },
    },
    result: { data: { discoverDiscussions: [THREAD_NODE] } },
  },
  {
    request: {
      query: DISCOVER_ANNOTATIONS,
      variables: { textSearch, limit: 5 },
    },
    result: {
      data: {
        discoverAnnotations: [
          {
            id: "QW5uOjE=",
            rawText:
              "Vendor shall indemnify Customer against any third-party claim…",
            page: 4,
            annotationLabel: {
              id: "TGFiOjE=",
              text: "Indemnification",
              color: "#ef4444",
            },
            document: {
              id: "RG9jOjE=",
              title: "Master Services Agreement",
              slug: "msa",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
            corpus: {
              id: "Q29ycHVzOjE=",
              title: "Vendor Agreements",
              slug: "vendor-agreements",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
          },
        ],
      },
    },
  },
  {
    request: { query: DISCOVER_DOCUMENTS, variables: { textSearch, limit: 5 } },
    result: {
      data: {
        discoverDocuments: [
          {
            id: "RG9jOjE=",
            title: "Master Services Agreement",
            slug: "msa",
            description: "The canonical vendor MSA with indemnity terms.",
            fileType: "application/pdf",
            creator: { id: "VXNlcjox", slug: "alice" },
          },
        ],
      },
    },
  },
  {
    request: { query: DISCOVER_CORPUSES, variables: { textSearch, limit: 5 } },
    result: {
      data: {
        discoverCorpuses: [
          {
            id: "Q29ycHVzOjE=",
            slug: "vendor-agreements",
            title: "Vendor Agreements",
            description:
              "Standard vendor agreements with indemnity carve-outs.",
            isPublic: true,
            documentCount: 12,
            creator: { id: "VXNlcjox", slug: "alice" },
          },
        ],
      },
    },
  },
  {
    request: { query: DISCOVER_NOTES, variables: { textSearch, limit: 5 } },
    result: {
      data: {
        discoverNotes: [
          {
            id: "Tm90ZTox",
            title: "Indemnity drafting tips",
            contentPreview:
              "Always **cap** indemnification obligations. See `MSA §12.4`.",
            modified: "2026-04-15T09:00:00Z",
            creator: { id: "VXNlcjox", username: "alice", slug: "alice" },
            document: {
              id: "RG9jOjE=",
              title: "Master Services Agreement",
              slug: "msa",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
            corpus: {
              id: "Q29ycHVzOjE=",
              title: "Vendor Agreements",
              slug: "vendor-agreements",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
          },
        ],
      },
    },
  },
];

test("DiscoverSearchResults — empty prompt is shown before any query is typed", async ({
  mount,
  page,
}) => {
  const component = await mount(
    <LandingTestWrapper mocks={[]}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  await expect(
    component.getByRole("heading", { name: "Search" })
  ).toBeVisible();
  await expect(
    component.getByText("Type to search across content you can access.")
  ).toBeVisible();

  await docScreenshot(page, "discover--search-results--empty-prompt");
});

test("DiscoverSearchResults — typing a query renders all five section headers", async ({
  mount,
  page,
}) => {
  const component = await mount(
    <LandingTestWrapper mocks={buildEmptyMocks("indemnity")}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  // Search box debounces by 250ms.
  const searchBox = component.getByPlaceholder(
    "Search across legal knowledge…"
  );
  await searchBox.fill("indemnity");
  await page.waitForTimeout(400);

  await expect(component.getByText("Discussions").first()).toBeVisible();
  await expect(component.getByText("Annotations").first()).toBeVisible();
  await expect(component.getByText("Documents").first()).toBeVisible();
  await expect(component.getByText("Collections").first()).toBeVisible();
  await expect(component.getByText("Notes").first()).toBeVisible();
});

test("DiscoverSearchResults — populated results render rows for every section", async ({
  mount,
  page,
}) => {
  const component = await mount(
    <LandingTestWrapper mocks={buildPopulatedMocks("indemnity")}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  const searchBox = component.getByPlaceholder(
    "Search across legal knowledge…"
  );
  await searchBox.fill("indemnity");
  // 250ms debounce + Apollo settle
  await page.waitForTimeout(700);

  // Discussion thread surfaced (rendered by ThreadListItem)
  await expect(
    component.getByText("Indemnity caps in vendor MSAs")
  ).toBeVisible();

  // Annotation row — rawText becomes title
  await expect(
    component.getByText(/Vendor shall indemnify Customer/)
  ).toBeVisible();

  // Document row — standalone document result (new category)
  await expect(
    component.getByText(/canonical vendor MSA with indemnity terms/)
  ).toBeVisible();

  // Collection row — title plus document count meta
  await expect(component.getByText("Vendor Agreements").first()).toBeVisible();
  await expect(component.getByText(/12 docs/)).toBeVisible();

  // Note row — title + Markdown-stripped snippet (no `**` or backticks)
  await expect(component.getByText("Indemnity drafting tips")).toBeVisible();
  const noteSnippet = component.getByText(/Always cap indemnification/);
  await expect(noteSnippet).toBeVisible();
  await expect(noteSnippet).not.toContainText("**");
  await expect(noteSnippet).not.toContainText("`");

  // Capture the populated state for documentation.
  await docScreenshot(page, "discover--search-results--with-results");
});

// Tab-switching mocks: All-tab defaults (limit=5) plus the entity-tab notes
// query (limit=25) so the click resolves cleanly.
const buildNotesEntityTabMocks = (textSearch: string): MockedResponse[] => [
  ...buildEmptyMocks(textSearch),
  {
    request: { query: DISCOVER_NOTES, variables: { textSearch, limit: 25 } },
    result: {
      data: {
        discoverNotes: [
          {
            id: "Tm90ZTox",
            title: "Indemnity drafting tips",
            contentPreview: "Plain preview body.",
            modified: "2026-04-15T09:00:00Z",
            creator: { id: "VXNlcjox", username: "alice", slug: "alice" },
            document: {
              id: "RG9jOjE=",
              title: "Master Services Agreement",
              slug: "msa",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
            corpus: {
              id: "Q29ycHVzOjE=",
              title: "Vendor Agreements",
              slug: "vendor-agreements",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
          },
        ],
      },
    },
  },
];

test("DiscoverSearchResults — selecting the Notes tab hides the other sections", async ({
  mount,
  page,
}) => {
  const component = await mount(
    <LandingTestWrapper mocks={buildNotesEntityTabMocks("indemnity")}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  const searchBox = component.getByPlaceholder(
    "Search across legal knowledge…"
  );
  await searchBox.fill("indemnity");

  // FilterTabs renders each entity option as a `.oc-filter-tab` button.
  // Wait for debounce so the All-tab default queries don't intercept the
  // notes-tab variables, then switch tabs.
  await page.waitForTimeout(300);
  await component.locator(".oc-filter-tab", { hasText: "Notes" }).click();
  await page.waitForTimeout(700);

  // Only the Notes section header renders; the other section headers must not.
  await expect(component.locator("text=Indemnity drafting tips")).toBeVisible();
  await expect(component.locator("h2", { hasText: "Notes" })).toBeVisible();
  await expect(component.locator("h2", { hasText: "Discussions" })).toHaveCount(
    0
  );
  await expect(component.locator("h2", { hasText: "Annotations" })).toHaveCount(
    0
  );
  await expect(component.locator("h2", { hasText: "Documents" })).toHaveCount(
    0
  );
  await expect(component.locator("h2", { hasText: "Collections" })).toHaveCount(
    0
  );
});

// ---------------------------------------------------------------------------
// Edge-case mocks — exercise conditional render branches inside each row
// (truncation, missing labels, untitled collection, missing description,
// markdown-empty notes, deletedAt filter on threads).
// ---------------------------------------------------------------------------
const LONG_RAW_TEXT = "a".repeat(180);
const buildEdgeCaseMocks = (textSearch: string): MockedResponse[] => [
  {
    request: {
      query: DISCOVER_DISCUSSIONS,
      variables: { textSearch, limit: 5 },
    },
    result: {
      data: {
        discoverDiscussions: [
          // Live thread — must render.
          {
            ...THREAD_NODE,
            id: "Q29udjpsaXZl",
            title: "Live thread keeps rendering",
            description: null,
            chatWithCorpus: null,
            chatMessages: { totalCount: 0 },
            upvoteCount: 0,
            downvoteCount: 0,
          },
          // Soft-deleted thread — filtered out before render.
          {
            ...THREAD_NODE,
            id: "Q29udjpkZWxldGVk",
            title: "Tombstoned thread should be hidden",
            description: null,
            chatWithCorpus: null,
            chatMessages: { totalCount: 0 },
            upvoteCount: 0,
            downvoteCount: 0,
            deletedAt: "2026-04-15T00:00:00Z",
          },
        ],
      },
    },
  },
  {
    request: {
      query: DISCOVER_ANNOTATIONS,
      variables: { textSearch, limit: 5 },
    },
    result: {
      data: {
        discoverAnnotations: [
          // > 140 chars → truncated with ellipsis.
          {
            id: "QW5uOmxvbmc=",
            rawText: LONG_RAW_TEXT,
            page: 0,
            annotationLabel: {
              id: "TGFiOjE=",
              text: "Indemnification",
              color: "#ef4444",
            },
            document: {
              id: "RG9jOjE=",
              title: "Master Services Agreement",
              slug: "msa",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
            // No corpus context — exercises null-corpus meta branch.
            corpus: null,
          },
          // No rawText → label fallback for title.
          {
            id: "QW5uOmxhYmVs",
            rawText: null,
            page: null,
            annotationLabel: {
              id: "TGFiOjI=",
              text: "Termination",
              color: null,
            },
            document: {
              id: "RG9jOjE=",
              title: "Master Services Agreement",
              slug: "msa",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
            corpus: null,
          },
          // Neither rawText nor label → defaults to "Annotation".
          {
            id: "QW5uOmJhcmU=",
            rawText: null,
            page: null,
            annotationLabel: null,
            document: {
              id: "RG9jOjE=",
              title: "Master Services Agreement",
              slug: "msa",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
            corpus: null,
          },
        ],
      },
    },
  },
  {
    request: { query: DISCOVER_DOCUMENTS, variables: { textSearch, limit: 5 } },
    result: {
      data: {
        discoverDocuments: [
          // No description / no fileType → meta branches collapse.
          {
            id: "RG9jOmJhcmU=",
            title: "Bare Document",
            slug: "bare-doc",
            description: null,
            fileType: null,
            creator: { id: "VXNlcjox", slug: "alice" },
          },
        ],
      },
    },
  },
  {
    request: { query: DISCOVER_CORPUSES, variables: { textSearch, limit: 5 } },
    result: {
      data: {
        discoverCorpuses: [
          // Untitled, no description, no creator.slug, no documentCount,
          // not public — every meta render branch chooses the null path.
          {
            id: "Q29ycHVzOmJhcmU=",
            slug: "vendor-agreements",
            title: null,
            description: null,
            isPublic: false,
            documentCount: null,
            creator: { id: "VXNlcjox", slug: null },
          },
        ],
      },
    },
  },
  {
    request: { query: DISCOVER_NOTES, variables: { textSearch, limit: 5 } },
    result: {
      data: {
        discoverNotes: [
          // No contentPreview → snippet branch resolves to undefined.
          // No corpus and anonymous creator → meta branches collapse.
          {
            id: "Tm90ZTpiYXJl",
            title: "Note with no preview",
            contentPreview: null,
            modified: "2026-04-15T09:00:00Z",
            creator: { id: "VXNlcjox", username: null, slug: "alice" },
            document: {
              id: "RG9jOjE=",
              title: "Master Services Agreement",
              slug: "msa",
              creator: { id: "VXNlcjox", slug: "alice" },
            },
            corpus: null,
          },
        ],
      },
    },
  },
];

test("DiscoverSearchResults — edge-case mocks exercise fallback render branches", async ({
  mount,
  page,
}) => {
  const component = await mount(
    <LandingTestWrapper mocks={buildEdgeCaseMocks("indemnity")}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  await component
    .getByPlaceholder("Search across legal knowledge…")
    .fill("indemnity");
  await page.waitForTimeout(700);

  // Live thread renders; tombstoned one does not.
  await expect(
    component.getByText("Live thread keeps rendering")
  ).toBeVisible();
  await expect(
    component.getByText("Tombstoned thread should be hidden")
  ).toHaveCount(0);

  // Long rawText truncated with an ellipsis.
  await expect(component.getByText(/a{140}…/)).toBeVisible();

  // Title falls back to label when rawText is missing.
  await expect(
    component.getByText("Termination", { exact: true })
  ).toBeVisible();

  // Title falls back to "Annotation" when both are missing.
  await expect(
    component.getByText("Annotation", { exact: true })
  ).toBeVisible();

  // Document with no description still renders its title.
  await expect(component.getByText("Bare Document")).toBeVisible();

  // Untitled collection fallback fires.
  await expect(component.getByText("Untitled collection")).toBeVisible();

  // Note row renders even though contentPreview is null.
  await expect(component.getByText("Note with no preview")).toBeVisible();
});

test("DiscoverSearchResults — clicking each row type navigates to the resolved URL", async ({
  mount,
  page,
}) => {
  // Reset history so the assertion below isn't polluted by a prior test.
  await page.evaluate(() => window.history.replaceState(null, "", "/"));

  const component = await mount(
    <LandingTestWrapper mocks={buildPopulatedMocks("indemnity")}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  await component
    .getByPlaceholder("Search across legal knowledge…")
    .fill("indemnity");
  await page.waitForTimeout(700);

  // Annotation row → /d/<creator>/<corpus>/<doc>?ann=<id>
  await component
    .getByRole("button")
    .filter({ hasText: /Vendor shall indemnify Customer/ })
    .click();
  await expect
    .poll(() => page.url())
    .toContain("/d/alice/vendor-agreements/msa");
  await expect.poll(() => page.url()).toContain("ann=QW5uOjE");

  // Document row → standalone /d/<creator>/<doc-slug>
  await page.evaluate(() => window.history.replaceState(null, "", "/"));
  await component
    .getByRole("button")
    .filter({ hasText: /canonical vendor MSA/ })
    .click();
  await expect.poll(() => page.url()).toContain("/d/alice/msa");

  // Reset and click the corpus row → /c/<creator>/<corpus>
  // Disambiguate from the annotation/note rows (which mention "Vendor
  // Agreements" in their meta) by anchoring on "12 docs" — unique to the
  // corpus card meta.
  await page.evaluate(() => window.history.replaceState(null, "", "/"));
  await component.getByRole("button").filter({ hasText: "12 docs" }).click();
  await expect.poll(() => page.url()).toContain("/c/alice/vendor-agreements");

  // Reset and click the note row → /d/<creator>/<corpus>/<doc>?note=<id>
  await page.evaluate(() => window.history.replaceState(null, "", "/"));
  await component
    .getByRole("button")
    .filter({ hasText: "Indemnity drafting tips" })
    .click();
  await expect
    .poll(() => page.url())
    .toContain("/d/alice/vendor-agreements/msa");
  await expect.poll(() => page.url()).toContain("note=Tm90ZTox");
});

test("DiscoverSearchResults — initial ?q= and ?type= seed local state from the URL", async ({
  mount,
  page,
}) => {
  // Pre-set the URL so useSearchParams + VALID_TABS path are exercised
  // on the first render (before any user interaction).
  await page.evaluate(() =>
    window.history.replaceState(null, "", "/?q=indemnity&type=notes")
  );

  const component = await mount(
    <LandingTestWrapper mocks={buildNotesEntityTabMocks("indemnity")}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  // Initial query is honored — search input reflects ?q= and the notes
  // result resolves without any typing.
  await expect(
    component.getByPlaceholder("Search across legal knowledge…")
  ).toHaveValue("indemnity");
  await page.waitForTimeout(700);
  await expect(component.getByText("Indemnity drafting tips")).toBeVisible();

  // Notes tab is the active one — the other section headers are absent.
  await expect(component.locator("h2", { hasText: "Notes" })).toBeVisible();
  await expect(component.locator("h2", { hasText: "Discussions" })).toHaveCount(
    0
  );
});

test("DiscoverSearchResults — invalid ?type= falls back to the All tab", async ({
  mount,
  page,
}) => {
  // VALID_TABS guard rejects the bogus tab and resets to "all". Pre-seed
  // the URL so the guard is exercised at mount time.
  await page.evaluate(() =>
    window.history.replaceState(null, "", "/?q=indemnity&type=bogus-tab")
  );

  const component = await mount(
    <LandingTestWrapper mocks={buildEmptyMocks("indemnity")}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  await page.waitForTimeout(700);

  // All five section headers visible → "all" tab is active.
  await expect(
    component.locator("h2", { hasText: "Discussions" })
  ).toBeVisible();
  await expect(
    component.locator("h2", { hasText: "Annotations" })
  ).toBeVisible();
  await expect(component.locator("h2", { hasText: "Documents" })).toBeVisible();
  await expect(
    component.locator("h2", { hasText: "Collections" })
  ).toBeVisible();
  await expect(component.locator("h2", { hasText: "Notes" })).toBeVisible();
});

test("DiscoverSearchResults — unrouteable rows render disabled and don't navigate", async ({
  mount,
  page,
}) => {
  // Corpus with no creator slug → getCorpusUrl returns "#".
  // Replace only the corpus mock — keep the other four sections empty.
  const emptyExceptCorpuses = buildEmptyMocks("indemnity").filter(
    (m) => m.request.query !== DISCOVER_CORPUSES
  );
  const unrouteableMocks: MockedResponse[] = [
    ...emptyExceptCorpuses,
    {
      request: {
        query: DISCOVER_CORPUSES,
        variables: { textSearch: "indemnity", limit: 5 },
      },
      result: {
        data: {
          discoverCorpuses: [
            {
              id: "Q29ycHVzOmJyb2tlbg==",
              slug: "vendor-agreements",
              title: "Broken Link Collection",
              // No creator.slug → getCorpusUrl returns "#".
              description: null,
              isPublic: true,
              documentCount: 0,
              creator: { id: "VXNlcjox", slug: null },
            },
          ],
        },
      },
    },
  ];

  await page.evaluate(() => window.history.replaceState(null, "", "/"));

  const component = await mount(
    <LandingTestWrapper mocks={unrouteableMocks}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  await component
    .getByPlaceholder("Search across legal knowledge…")
    .fill("indemnity");
  await page.waitForTimeout(700);

  const row = component
    .getByRole("button")
    .filter({ hasText: "Broken Link Collection" });
  await expect(row).toBeVisible();
  // Native disabled state — Playwright surfaces it via aria-disabled too.
  await expect(row).toBeDisabled();

  // Force-click bypasses the disabled state in the DOM but the React
  // onClick handler is also short-circuited via `disabled`. Either way,
  // the URL must not change to a `#` target or anything else.
  await row.click({ force: true }).catch(() => {});
  await page.waitForTimeout(200);
  expect(new URL(page.url()).pathname).toBe("/");
});

test("DiscoverSearchResults — section error renders the recoverable fallback", async ({
  mount,
  page,
}) => {
  // Erroring mocks for every section so each Section renders its error
  // branch (`error && !data`).
  const errorMocks: MockedResponse[] = [
    DISCOVER_DISCUSSIONS,
    DISCOVER_ANNOTATIONS,
    DISCOVER_DOCUMENTS,
    DISCOVER_CORPUSES,
    DISCOVER_NOTES,
  ].map((query) => ({
    request: { query, variables: { textSearch: "boom", limit: 5 } },
    error: new Error("Service unavailable"),
  }));

  const component = await mount(
    <LandingTestWrapper mocks={errorMocks}>
      <DiscoverSearchResults />
    </LandingTestWrapper>
  );

  await component
    .getByPlaceholder("Search across legal knowledge…")
    .fill("boom");
  await page.waitForTimeout(700);

  // Each Section maps a query error to a stable user-facing message.
  const errorAlerts = component.getByRole("alert");
  await expect(errorAlerts.first()).toBeVisible();
  await expect(errorAlerts.first()).toContainText(
    "We couldn't load these results"
  );
  // All five sections error simultaneously.
  await expect(errorAlerts).toHaveCount(5);
});
