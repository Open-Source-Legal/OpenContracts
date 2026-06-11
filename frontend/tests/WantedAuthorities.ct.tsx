/**
 * Component tests for WantedAuthoritiesLive — the Apollo-wired shell that
 * fetches GET_WANTED_AUTHORITIES and renders the presentational
 * WantedAuthoritiesCard (the missing-law backlog behind the governance
 * graph's ghost nodes). The live wrapper is deliberately silent (renders
 * nothing) while loading, on error, and when the backlog is empty.
 *
 * NOTE: each JSX-component import is kept in its own ``import`` statement,
 * separate from all other imports, per the Playwright CT split-import rule.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { WantedAuthoritiesLive } from "../src/components/corpuses/CorpusHome/intelligence/WantedAuthoritiesLive";
import { docScreenshot } from "./utils/docScreenshot";
import { GET_WANTED_AUTHORITIES } from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

const BACKLOG = [
  {
    authority: "exchange-act",
    mentionCount: 41,
    keyCount: 7,
    corpusCount: 1,
    topKeys: [
      { canonicalKey: "exchange-act:16", mentionCount: 21, corpusCount: 1 },
      { canonicalKey: "exchange-act:13", mentionCount: 9, corpusCount: 1 },
      { canonicalKey: "exchange-act:12", mentionCount: 5, corpusCount: 1 },
    ],
  },
  {
    authority: "dgcl",
    mentionCount: 18,
    keyCount: 4,
    corpusCount: 1,
    topKeys: [
      { canonicalKey: "dgcl:262", mentionCount: 11, corpusCount: 1 },
      { canonicalKey: "dgcl:220", mentionCount: 4, corpusCount: 1 },
    ],
  },
  {
    authority: "nybcl",
    mentionCount: 3,
    keyCount: 1,
    corpusCount: 1,
    topKeys: [{ canonicalKey: "nybcl:912", mentionCount: 3, corpusCount: 1 }],
  },
];

const makeWantedMock = (wantedAuthorities: typeof BACKLOG | []) => ({
  request: {
    query: GET_WANTED_AUTHORITIES,
    variables: { corpusId: CORPUS_ID },
  },
  result: { data: { wantedAuthorities } },
});

test.describe("WantedAuthoritiesLive", () => {
  test("renders the ranked backlog with authority captions and ghost-key chips", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[makeWantedMock(BACKLOG), makeWantedMock(BACKLOG)]}
        addTypename={false}
      >
        <WantedAuthoritiesLive corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    const card = page.locator('[data-testid="wanted-authorities"]');
    await expect(card).toBeVisible({ timeout: 10000 });

    // Header sums mentions across all authorities (41 + 18 + 3).
    await expect(
      page.locator('[data-testid="wanted-authorities-meta"]')
    ).toContainText("62 unresolved references");

    // One row per authority, in the server's demand order.
    const rows = page.locator('[data-testid="wanted-authorities-row"]');
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toContainText("EXCHANGE ACT OF 1934");
    await expect(rows.nth(0)).toContainText("41 references · 7 sections");
    await expect(rows.nth(1)).toContainText("DELAWARE GEN. CORP. LAW");

    // Unregistered authorities fall back to the canonical-key display form.
    await expect(rows.nth(2)).toContainText("NYBCL");

    // Top keys render as chips in the graph's ghost vocabulary, with counts.
    await expect(rows.nth(0)).toContainText("Exchange Act § 16");
    await expect(rows.nth(0)).toContainText("×21");
    await expect(rows.nth(1)).toContainText("DGCL § 262");

    // Under the row cap nothing is hidden — no "more" note.
    await expect(
      page.locator('[data-testid="wanted-authorities-more"]')
    ).toHaveCount(0);

    await docScreenshot(page, "corpus--wanted-authorities--with-data");

    await component.unmount();
  });

  test("renders nothing at all when the backlog is empty", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[makeWantedMock([]), makeWantedMock([])]}
        addTypename={false}
      >
        <WantedAuthoritiesLive corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    // Give the query time to resolve, then assert the card never appeared.
    await page.waitForTimeout(1000);
    await expect(
      page.locator('[data-testid="wanted-authorities"]')
    ).toHaveCount(0);

    await component.unmount();
  });
});
