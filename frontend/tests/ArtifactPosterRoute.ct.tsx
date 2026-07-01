/**
 * Component tests for ArtifactPosterRoute — the public ``/a/<slug>`` page for a
 * shareable corpus poster (Artifact). It resolves the artifact by slug, renders
 * the named template full-bleed on a fixed poster canvas using the artifact's
 * configurable captions, and offers share affordances (Download PNG, Copy link).
 *
 * These tests mount the route inside a MemoryRouter + Routes (so ``useParams``
 * resolves the slug) under a MockedProvider, and cover: the loading state, the
 * not-found state (missing artifact), the unknown-template fallback, and the
 * happy path (poster + toolbar + share buttons, with the download/copy handlers
 * exercised). The ``spending-beeswarm`` template reads its own data story, so the
 * happy-path mocks include that query too.
 *
 * NOTE: each JSX-component import is kept in its own statement, separate from
 * helper imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ArtifactPosterRoute } from "../src/components/routes/ArtifactPosterRoute";
import { docScreenshot } from "./utils/docScreenshot";
// Use the real query documents so the mocks stay in lock-step with the route.
import {
  GET_ARTIFACT_BY_SLUG,
  GET_CORPUS_DATA_STORY,
} from "../src/graphql/queries";

const SLUG = "where-the-money-went";
const CORPUS_ID = "Q29ycHVzVHlwZTox";

const artifactMock = (
  artifact: Record<string, unknown> | null,
  delay?: number
) => ({
  request: { query: GET_ARTIFACT_BY_SLUG, variables: { slug: SLUG } },
  ...(delay ? { delay } : {}),
  result: { data: { artifactBySlug: artifact } },
});

const beeswarmArtifact = {
  id: "Artifact:1",
  slug: SLUG,
  template: "spending-beeswarm",
  title: "Where the Money Went",
  subtitle: "Every contract, by value",
  byline: "Source: ACME filings",
  config: { noun: "contracts" },
  corpusId: CORPUS_ID,
  corpusSlug: "acme",
  imageUrl: null,
};

// The spending-beeswarm template reads the corpus data story for its corpusId.
const dataStoryMock = {
  request: {
    query: GET_CORPUS_DATA_STORY,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      corpusDataStory: {
        totalDocuments: 2,
        profiles: [
          {
            documentId: "Doc1",
            title: "Grant Agreement",
            slug: "doc1",
            type: "Grant",
            party: "Alpha Corp",
            effectiveDate: "2021-01-15",
            value: 12_000_000,
          },
          {
            documentId: "Doc2",
            title: "Renewal",
            slug: "doc2",
            type: "Renewal",
            party: "Beta LLC",
            effectiveDate: "2022-06-01",
            value: 1_500_000,
          },
        ],
      },
    },
  },
};

/** Mount the route at ``/a/:slug`` so useParams resolves the slug. */
const mountRoute = (mount: any, mocks: any[]) =>
  mount(
    <MemoryRouter initialEntries={[`/a/${SLUG}`]}>
      <MockedProvider mocks={mocks} addTypename={false}>
        <Routes>
          <Route path="/a/:slug" element={<ArtifactPosterRoute />} />
        </Routes>
      </MockedProvider>
    </MemoryRouter>
  );

test.describe("ArtifactPosterRoute", () => {
  test("shows a loading state while the artifact resolves", async ({
    mount,
    page,
  }) => {
    const component = await mountRoute(mount, [
      artifactMock(beeswarmArtifact, 600),
      dataStoryMock,
    ]);

    await expect(page.getByText("Loading poster…")).toBeVisible();
    // Once it resolves, the poster replaces the loading state.
    await expect(page.locator('[data-testid="artifact-poster"]')).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("renders the poster, captions and share affordances for a known template", async ({
    mount,
    page,
  }) => {
    const component = await mountRoute(mount, [
      artifactMock(beeswarmArtifact),
      dataStoryMock,
    ]);

    // Toolbar carries the artifact's title; the poster frame and the named
    // template (the beeswarm) render inside it.
    await expect(page.locator('[data-testid="artifact-poster"]')).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Where the Money Went").first()).toBeVisible();
    await expect(
      page.locator('[data-testid="spending-beeswarm"]')
    ).toBeVisible();

    // The route sets the document title from the artifact title.
    await expect
      .poll(() => page.title(), { timeout: 5000 })
      .toContain("Where the Money Went");

    // Share affordances are present; exercise both handlers (copy + download).
    const download = page.locator('[data-testid="artifact-download"]');
    const copy = page.locator('[data-testid="artifact-copy-link"]');
    await expect(download).toBeVisible();
    await expect(copy).toBeVisible();

    await copy.click();
    await download.click();
    // Give the async SVG->PNG rasterisation a moment; the poster must survive it.
    await page.waitForTimeout(700);
    await expect(page.locator('[data-testid="artifact-poster"]')).toBeVisible();

    await docScreenshot(page, "corpus--artifact-poster-route--with-data");

    await component.unmount();
  });

  test("shows a not-available message when the slug resolves to nothing", async ({
    mount,
    page,
  }) => {
    const component = await mountRoute(mount, [artifactMock(null)]);

    await expect(
      page.locator('[data-testid="artifact-not-found"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByText("This artifact isn't available.")
    ).toBeVisible();

    await component.unmount();
  });

  test("falls back to not-available for an unknown template id", async ({
    mount,
    page,
  }) => {
    const component = await mountRoute(mount, [
      artifactMock({ ...beeswarmArtifact, template: "reference-web" }),
    ]);

    await expect(
      page.locator('[data-testid="artifact-not-found"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });
});
