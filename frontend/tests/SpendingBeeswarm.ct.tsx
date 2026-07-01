/**
 * Component tests for SpendingBeeswarm — the standalone, poster-grade "every
 * document, over time, by value" beeswarm built to be screenshot and shared.
 *
 * It reads the existing ``corpusDataStory`` (no extra query), builds a
 * deterministic d3-force packing in a ``useMemo`` (no RNG), and self-hides until
 * there is at least one *dated* document. These tests mount it under a
 * MockedProvider supplying that one query and assert the poster renders (title,
 * axis years, one dot per dated document) — and that it self-hides when no
 * document carries a parseable effective date.
 *
 * NOTE: each JSX-component import is kept in its own statement, separate from
 * helper imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { SpendingBeeswarm } from "../src/components/corpuses/CorpusHome/intelligence/SpendingBeeswarm";
import { docScreenshot } from "./utils/docScreenshot";
// Use the real query document so the mocks stay in lock-step with the component.
import { GET_CORPUS_DATA_STORY } from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

interface ProfileSeed {
  documentId: string;
  title: string;
  type?: string | null;
  party?: string | null;
  effectiveDate?: string | null;
  value?: number | null;
}

// The beeswarm asks for the data story by corpus id (variables matched exactly).
const dataStoryMock = (profiles: ProfileSeed[]) => ({
  request: {
    query: GET_CORPUS_DATA_STORY,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      corpusDataStory: {
        totalDocuments: profiles.length,
        profiles: profiles.map((p) => ({
          documentId: p.documentId,
          title: p.title,
          slug: p.documentId.toLowerCase(),
          type: p.type ?? null,
          party: p.party ?? null,
          effectiveDate: p.effectiveDate ?? null,
          value: p.value ?? null,
        })),
      },
    },
  },
});

const BEESWARM = '[data-testid="spending-beeswarm"]';

test.describe("SpendingBeeswarm", () => {
  test("renders the poster with a dot per dated document, an axis and whale labels", async ({
    mount,
    page,
  }) => {
    const profiles: ProfileSeed[] = [
      {
        documentId: "Doc1",
        title: "Series A Stock Purchase Agreement",
        type: "Grant",
        party: "Alpha Corp",
        effectiveDate: "2021-01-15",
        value: 15_000_000,
      },
      {
        documentId: "Doc2",
        title: "Master Services Agreement",
        type: "Renewal",
        party: "Beta LLC",
        effectiveDate: "2022-06-01",
        value: 1_500_000,
      },
      {
        documentId: "Doc3",
        title: "Order Form",
        type: "Grant",
        party: "Gamma Inc",
        effectiveDate: "2023-03-20",
        value: 250_000,
      },
      {
        documentId: "Doc4",
        title: "Amendment No. 1",
        type: "Amendment",
        party: null,
        effectiveDate: "2023-09-10",
        value: 0,
      },
    ];

    const component = await mount(
      <MockedProvider mocks={[dataStoryMock(profiles)]} addTypename={false}>
        <SpendingBeeswarm corpusId={CORPUS_ID} noun="contracts" />
      </MockedProvider>
    );

    const frame = page.locator(BEESWARM);
    await expect(frame).toBeVisible({ timeout: 10000 });

    // Auto-derived headline: "<count> <noun>, <yearStart>–<yearEnd>".
    await expect(frame).toContainText("4 contracts, 2021–2023");
    // Auto-derived takeaway carries the compact total value ($16.75M -> $17M).
    await expect(frame).toContainText("$17M in total value");

    // One <circle> per dated document (4) plus the per-type legend swatches, so
    // the dot layer is present and non-empty.
    const circles = frame.locator("svg circle");
    await expect(circles.first()).toBeVisible();
    expect(await circles.count()).toBeGreaterThanOrEqual(4);

    // The x-axis renders a year label for the spanned range.
    await expect(frame.locator("svg text", { hasText: "2022" })).toHaveCount(1);

    await docScreenshot(page, "corpus--spending-beeswarm--with-data");

    await component.unmount();
  });

  test("honours configurable title, takeaway and byline captions", async ({
    mount,
    page,
  }) => {
    const profiles: ProfileSeed[] = [
      {
        documentId: "Doc1",
        title: "Grant Agreement",
        type: "Grant",
        party: "Alpha Corp",
        effectiveDate: "2020-02-01",
        value: 5_000_000,
      },
      {
        documentId: "Doc2",
        title: "Renewal",
        type: "Renewal",
        party: "Beta LLC",
        effectiveDate: "2021-02-01",
        value: 2_000_000,
      },
    ];

    const component = await mount(
      <MockedProvider mocks={[dataStoryMock(profiles)]} addTypename={false}>
        <SpendingBeeswarm
          corpusId={CORPUS_ID}
          title="Where the Money Went"
          takeaway="Two grants, two years"
          byline="Source: ACME filings"
        />
      </MockedProvider>
    );

    const frame = page.locator(BEESWARM);
    await expect(frame).toBeVisible({ timeout: 10000 });
    await expect(frame).toContainText("Where the Money Went");
    await expect(frame).toContainText("Two grants, two years");
    await expect(frame).toContainText("Source: ACME filings");

    await component.unmount();
  });

  test("drops isolated early date-outliers and notes the omission", async ({
    mount,
    page,
  }) => {
    // One contract dated far before the rest would stretch the time axis, so the
    // model walks up from the oldest dropping each leading point that sits >3
    // years before the next, and the subtitle notes how many were omitted.
    const profiles: ProfileSeed[] = [
      {
        documentId: "Old",
        title: "Ancient Agreement",
        type: "Grant",
        party: "Old Corp",
        effectiveDate: "2005-04-01",
        value: 3_000_000,
      },
      {
        documentId: "Doc1",
        title: "Recent A",
        type: "Grant",
        party: "Alpha Corp",
        effectiveDate: "2021-01-15",
        value: 5_000_000,
      },
      {
        documentId: "Doc2",
        title: "Recent B",
        type: "Renewal",
        party: "Beta LLC",
        effectiveDate: "2022-06-01",
        value: 1_500_000,
      },
      {
        documentId: "Doc3",
        title: "Recent C",
        type: "Grant",
        party: "Gamma Inc",
        effectiveDate: "2023-03-20",
        value: 250_000,
      },
    ];

    const component = await mount(
      <MockedProvider mocks={[dataStoryMock(profiles)]} addTypename={false}>
        <SpendingBeeswarm corpusId={CORPUS_ID} noun="contracts" />
      </MockedProvider>
    );

    const frame = page.locator(BEESWARM);
    await expect(frame).toBeVisible({ timeout: 10000 });
    // The 2005 outlier is dropped: the headline spans only the recent bulk and
    // the takeaway calls out the single omission.
    await expect(frame).toContainText("3 contracts, 2021–2023");
    await expect(frame).toContainText("1 earlier omitted");

    await component.unmount();
  });

  test("self-hides when no document carries a parseable effective date", async ({
    mount,
    page,
  }) => {
    // Profiles exist but none are dated, so the time-axis model is empty and the
    // whole poster suppresses itself rather than rendering an empty frame.
    const profiles: ProfileSeed[] = [
      { documentId: "Doc1", title: "Undated A", type: "Memo", value: 1000 },
      { documentId: "Doc2", title: "Undated B", type: "Memo", value: null },
    ];

    const component = await mount(
      <MockedProvider mocks={[dataStoryMock(profiles)]} addTypename={false}>
        <SpendingBeeswarm corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    // Allow the query to resolve, then confirm nothing rendered.
    await page.waitForTimeout(700);
    await expect(page.locator(BEESWARM)).toHaveCount(0);

    await component.unmount();
  });
});
