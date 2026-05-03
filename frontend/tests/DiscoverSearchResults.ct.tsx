// Playwright Component Tests for DiscoverSearchResults (cross-content discover search).
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { DiscoverSearchResults } from "../src/views/DiscoverSearchResults";
import { LandingTestWrapper } from "./LandingTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import {
  GET_CONVERSATIONS,
  GET_CORPUSES,
  SEARCH_ANNOTATIONS_FOR_MENTION,
  SEARCH_NOTES_FOR_MENTION,
} from "../src/graphql/queries";

const buildEmptyMocks = (textSearch: string): MockedResponse[] => [
  {
    request: {
      query: GET_CONVERSATIONS,
      variables: {
        conversationType: "THREAD",
        title_Contains: textSearch,
        limit: 5,
      },
    },
    result: { data: { conversations: { edges: [], totalCount: 0 } } },
  },
  {
    request: {
      query: SEARCH_ANNOTATIONS_FOR_MENTION,
      variables: { textSearch, first: 5 },
    },
    result: { data: { searchAnnotationsForMention: { edges: [] } } },
  },
  {
    request: {
      query: GET_CORPUSES,
      variables: { textSearch, limit: 5 },
    },
    result: { data: { corpuses: { edges: [] } } },
  },
  {
    request: {
      query: SEARCH_NOTES_FOR_MENTION,
      variables: { textSearch, first: 5 },
    },
    result: { data: { searchNotesForMention: { edges: [] } } },
  },
];

const buildPopulatedMocks = (textSearch: string): MockedResponse[] => [
  {
    request: {
      query: GET_CONVERSATIONS,
      variables: {
        conversationType: "THREAD",
        title_Contains: textSearch,
        limit: 5,
      },
    },
    result: {
      data: {
        conversations: {
          edges: [
            {
              node: {
                id: "Q29udjox",
                conversationType: "THREAD",
                title: "Indemnity caps in vendor MSAs",
                description: "How aggressive are folks getting on caps?",
                createdAt: "2026-04-01T12:00:00Z",
                updatedAt: "2026-04-02T12:00:00Z",
                creator: {
                  id: "VXNlcjox",
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
              },
            },
          ],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
          },
          totalCount: 1,
        },
      },
    },
  },
  {
    request: {
      query: SEARCH_ANNOTATIONS_FOR_MENTION,
      variables: { textSearch, first: 5 },
    },
    result: {
      data: {
        searchAnnotationsForMention: {
          edges: [
            {
              node: {
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
            },
          ],
        },
      },
    },
  },
  {
    request: {
      query: GET_CORPUSES,
      variables: { textSearch, limit: 5 },
    },
    result: {
      data: {
        corpuses: {
          edges: [
            {
              node: {
                id: "Q29ycHVzOjE=",
                slug: "vendor-agreements",
                icon: null,
                title: "Vendor Agreements",
                creator: { email: "alice@example.com", slug: "alice" },
                description:
                  "Standard vendor agreements with indemnity carve-outs.",
                isPublic: true,
                isPersonal: false,
                myPermissions: ["READ"],
                documentCount: 12,
                parent: null,
                labelSet: null,
                categories: [],
                license: null,
                licenseLink: null,
              },
            },
          ],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
          },
        },
      },
    },
  },
  {
    request: {
      query: SEARCH_NOTES_FOR_MENTION,
      variables: { textSearch, first: 5 },
    },
    result: {
      data: {
        searchNotesForMention: {
          edges: [
            {
              node: {
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
            },
          ],
        },
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

test("DiscoverSearchResults — typing a query renders all four section headers", async ({
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

// Tab-switching mocks: All-tab defaults (first/limit=5) plus the entity-tab
// notes query (first=25) so the click resolves cleanly.
const buildNotesEntityTabMocks = (textSearch: string): MockedResponse[] => [
  ...buildEmptyMocks(textSearch),
  {
    request: {
      query: SEARCH_NOTES_FOR_MENTION,
      variables: { textSearch, first: 25 },
    },
    result: {
      data: {
        searchNotesForMention: {
          edges: [
            {
              node: {
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
            },
          ],
        },
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

  // Only the Notes section header renders; Discussions/Annotations/
  // Collections section headers must not appear.
  await expect(component.locator("text=Indemnity drafting tips")).toBeVisible();
  // SectionTitle "Notes" lives inside an h2 — assert it's mounted.
  await expect(component.locator("h2", { hasText: "Notes" })).toBeVisible();
  await expect(component.locator("h2", { hasText: "Discussions" })).toHaveCount(
    0
  );
  await expect(component.locator("h2", { hasText: "Annotations" })).toHaveCount(
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
      query: GET_CONVERSATIONS,
      variables: {
        conversationType: "THREAD",
        title_Contains: textSearch,
        limit: 5,
      },
    },
    result: {
      data: {
        conversations: {
          edges: [
            // Live thread — must render.
            {
              node: {
                id: "Q29udjpsaXZl",
                conversationType: "THREAD",
                title: "Live thread keeps rendering",
                description: null,
                createdAt: "2026-04-01T12:00:00Z",
                updatedAt: "2026-04-02T12:00:00Z",
                creator: {
                  id: "VXNlcjox",
                  username: "alice",
                  email: "alice@example.com",
                },
                chatWithCorpus: null,
                chatWithDocument: null,
                chatMessages: { totalCount: 0 },
                isPublic: true,
                myPermissions: ["READ"],
                upvoteCount: 0,
                downvoteCount: 0,
                userVote: null,
                isLocked: false,
                lockedBy: null,
                lockedAt: null,
                isPinned: false,
                pinnedBy: null,
                pinnedAt: null,
                deletedAt: null,
              },
            },
            // Soft-deleted thread — filtered out before render.
            {
              node: {
                id: "Q29udjpkZWxldGVk",
                conversationType: "THREAD",
                title: "Tombstoned thread should be hidden",
                description: null,
                createdAt: "2026-04-01T12:00:00Z",
                updatedAt: "2026-04-02T12:00:00Z",
                creator: {
                  id: "VXNlcjox",
                  username: "alice",
                  email: "alice@example.com",
                },
                chatWithCorpus: null,
                chatWithDocument: null,
                chatMessages: { totalCount: 0 },
                isPublic: true,
                myPermissions: ["READ"],
                upvoteCount: 0,
                downvoteCount: 0,
                userVote: null,
                isLocked: false,
                lockedBy: null,
                lockedAt: null,
                isPinned: false,
                pinnedBy: null,
                pinnedAt: null,
                deletedAt: "2026-04-15T00:00:00Z",
              },
            },
          ],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
          },
          totalCount: 2,
        },
      },
    },
  },
  {
    request: {
      query: SEARCH_ANNOTATIONS_FOR_MENTION,
      variables: { textSearch, first: 5 },
    },
    result: {
      data: {
        searchAnnotationsForMention: {
          edges: [
            // > 140 chars → truncated with ellipsis.
            {
              node: {
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
            },
            // No rawText → label fallback for title.
            {
              node: {
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
            },
            // Neither rawText nor label → defaults to "Annotation".
            {
              node: {
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
            },
          ],
        },
      },
    },
  },
  {
    request: {
      query: GET_CORPUSES,
      variables: { textSearch, limit: 5 },
    },
    result: {
      data: {
        corpuses: {
          edges: [
            // Untitled, no description, no creator.slug, no documentCount,
            // not public — every meta render branch chooses the null path.
            {
              node: {
                id: "Q29ycHVzOmJhcmU=",
                slug: "vendor-agreements",
                icon: null,
                title: null,
                creator: { email: "alice@example.com", slug: null },
                description: null,
                isPublic: false,
                isPersonal: false,
                myPermissions: ["READ"],
                documentCount: null,
                parent: null,
                labelSet: null,
                categories: [],
                license: null,
                licenseLink: null,
              },
            },
          ],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
          },
        },
      },
    },
  },
  {
    request: {
      query: SEARCH_NOTES_FOR_MENTION,
      variables: { textSearch, first: 5 },
    },
    result: {
      data: {
        searchNotesForMention: {
          edges: [
            // No contentPreview → snippet branch resolves to undefined.
            // No corpus and anonymous creator → meta branches collapse.
            {
              node: {
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
            },
          ],
        },
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
  // Each row is a <button>; click the button containing the rawText title.
  await component
    .getByRole("button")
    .filter({ hasText: /Vendor shall indemnify Customer/ })
    .click();
  await expect
    .poll(() => page.url())
    .toContain("/d/alice/vendor-agreements/msa");
  await expect.poll(() => page.url()).toContain("ann=QW5uOjE");

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

  // All four section headers visible → "all" tab is active.
  await expect(
    component.locator("h2", { hasText: "Discussions" })
  ).toBeVisible();
  await expect(
    component.locator("h2", { hasText: "Annotations" })
  ).toBeVisible();
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
  // Replace only the corpus mock — keep the other three sections empty so
  // we don't conflict with buildEmptyMocks's GET_CORPUSES entry.
  const emptyExceptCorpuses = buildEmptyMocks("indemnity").filter(
    (m) => m.request.query !== GET_CORPUSES
  );
  const unrouteableMocks: MockedResponse[] = [
    ...emptyExceptCorpuses,
    {
      request: {
        query: GET_CORPUSES,
        variables: { textSearch: "indemnity", limit: 5 },
      },
      result: {
        data: {
          corpuses: {
            edges: [
              {
                node: {
                  id: "Q29ycHVzOmJyb2tlbg==",
                  slug: "vendor-agreements",
                  icon: null,
                  title: "Broken Link Collection",
                  // No creator.slug → getCorpusUrl returns "#".
                  creator: { email: "alice@example.com", slug: null },
                  description: null,
                  isPublic: true,
                  isPersonal: false,
                  myPermissions: ["READ"],
                  documentCount: 0,
                  parent: null,
                  labelSet: null,
                  categories: [],
                  license: null,
                  licenseLink: null,
                },
              },
            ],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
            },
          },
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
    {
      request: {
        query: GET_CONVERSATIONS,
        variables: {
          conversationType: "THREAD",
          title_Contains: "boom",
          limit: 5,
        },
      },
      error: new Error("Conversations service unavailable"),
    },
    {
      request: {
        query: SEARCH_ANNOTATIONS_FOR_MENTION,
        variables: { textSearch: "boom", first: 5 },
      },
      error: new Error("Annotations service unavailable"),
    },
    {
      request: {
        query: GET_CORPUSES,
        variables: { textSearch: "boom", limit: 5 },
      },
      error: new Error("Corpuses service unavailable"),
    },
    {
      request: {
        query: SEARCH_NOTES_FOR_MENTION,
        variables: { textSearch: "boom", first: 5 },
      },
      error: new Error("Notes service unavailable"),
    },
  ];

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
  // All four sections error simultaneously.
  await expect(errorAlerts).toHaveCount(4);
});
