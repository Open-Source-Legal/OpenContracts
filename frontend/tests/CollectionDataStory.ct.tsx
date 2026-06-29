/**
 * Component tests for CollectionDataStory — the "what the data says" surface of
 * the corpus home. It reads the per-document Collection Profile (type /
 * counterparty / effective date / value) via ``corpusDataStory`` and renders an
 * honest, compact data story: headline figures, composition by type, a timeline
 * of effective dates, and the documents by value. Each panel renders only when
 * that facet has data, and the whole block self-hides until the extract has run.
 *
 * These tests mount it under a MockedProvider supplying that one query and assert
 * (a) the populated story renders all four facets, and (b) it self-hides when no
 * facet has any data.
 *
 * NOTE: each JSX-component import is kept in its own statement, separate from
 * helper imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { CollectionDataStory } from "../src/components/corpuses/CorpusHome/intelligence/CollectionDataStory";
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

const STORY = '[data-testid="collection-data-story"]';

test.describe("CollectionDataStory", () => {
  test("renders figures, composition, timeline and value panels", async ({
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
    ];

    const component = await mount(
      <MockedProvider mocks={[dataStoryMock(profiles)]} addTypename={false}>
        <CollectionDataStory corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    const story = page.locator(STORY);
    await expect(story).toBeVisible({ timeout: 10000 });
    await expect(story).toContainText("What the collection says");

    // Headline figures: total value ($16.75M -> $17M), the date span, and the
    // number of distinct document types (Grant + Renewal = 2).
    const figures = page.locator(
      '[data-testid="collection-data-story-figures"]'
    );
    await expect(figures).toContainText("$17M");
    await expect(figures).toContainText("Total value");
    await expect(figures).toContainText("2021–2023");
    await expect(figures).toContainText("Document types");

    // Composition by type.
    const types = page.locator('[data-testid="collection-data-story-types"]');
    await expect(types).toContainText("By document type");
    await expect(types).toContainText("Grant");
    await expect(types).toContainText("Renewal");

    // Timeline renders when more than one document is dated.
    await expect(
      page.locator('[data-testid="collection-data-story-timeline"]')
    ).toBeVisible();

    // By value, surfacing the counterparty for the largest deal.
    const values = page.locator('[data-testid="collection-data-story-values"]');
    await expect(values).toContainText("By value");
    await expect(values).toContainText("Alpha Corp");

    await docScreenshot(page, "corpus--collection-data-story--with-data");

    await component.unmount();
  });

  test("self-hides when no facet has any data", async ({ mount, page }) => {
    // Profiles exist but carry no type, date or value, so every panel is empty
    // and the block suppresses itself rather than showing an empty frame.
    const profiles: ProfileSeed[] = [
      { documentId: "Doc1", title: "Bare A" },
      { documentId: "Doc2", title: "Bare B" },
    ];

    const component = await mount(
      <MockedProvider mocks={[dataStoryMock(profiles)]} addTypename={false}>
        <CollectionDataStory corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    await page.waitForTimeout(700);
    await expect(page.locator(STORY)).toHaveCount(0);

    await component.unmount();
  });
});
