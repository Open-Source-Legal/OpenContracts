/**
 * Component tests for DocumentGraphLive — the Apollo-wired thin shell that
 * fetches GET_CORPUS_DOCUMENT_GRAPH and feeds the presentational
 * DocumentGraphGlimpse. Mounts under MockedProvider so the query resolves
 * synchronously in the test environment.
 *
 * NOTE: each JSX-component import is kept in its own ``import`` statement,
 * separate from all other imports, per the Playwright CT split-import rule.
 * Mixing a component reference with helpers in a single import statement
 * causes Playwright CT's babel transform to leave the component unrewritten
 * and ``mount()`` throws.
 */
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { DocumentGraphLive } from "../src/components/corpuses/CorpusHome/intelligence/DocumentGraphLive";
import { docScreenshot } from "./utils/docScreenshot";
import { GET_CORPUS_DOCUMENT_GRAPH } from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

// Two graph mock instances so Apollo does not exhaust the mock on a potential
// refetch (MockedProvider removes each mock after one use by default).
const makeGraphMock = () => ({
  request: {
    query: GET_CORPUS_DOCUMENT_GRAPH,
    // DocumentGraphLive builds variables as { corpusId } — no limit field.
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      corpusDocumentGraph: {
        nodes: [
          {
            id: "Doc:1",
            title: "Alpha",
            fileType: "application/pdf",
            degree: 2,
          },
          {
            id: "Doc:2",
            title: "Beta",
            fileType: "application/pdf",
            degree: 1,
          },
          {
            id: "Doc:3",
            title: "Gamma",
            fileType: "application/pdf",
            degree: 1,
          },
        ],
        edges: [
          {
            id: "e1",
            source: "Doc:1",
            target: "Doc:2",
            label: "Cites",
            relationshipType: "RELATIONSHIP",
          },
        ],
        totalNodeCount: 3,
        totalEdgeCount: 1,
        truncated: false,
      },
    },
  },
});

test.describe("DocumentGraphLive", () => {
  test("renders the graph glimpse with live data from the Apollo mock", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[makeGraphMock(), makeGraphMock()]}
        addTypename={false}
      >
        <DocumentGraphLive corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    // Wait for the SVG to appear — the skeleton disappears once data resolves.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-svg"]')
    ).toBeVisible({ timeout: 20000 });

    // Three nodes rendered — one per document in the mock.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-node"]')
    ).toHaveCount(3, { timeout: 20000 });

    // One edge line rendered.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-edges"] line')
    ).toHaveCount(1);

    // Meta summary reflects the returned counts.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-meta"]')
    ).toContainText("3 linked documents");

    await docScreenshot(page, "corpus--document-graph-live--with-data");

    await component.unmount();
  });

  test("shows the loading skeleton before the query resolves", async ({
    mount,
    page,
  }) => {
    // Use a delayed mock so we can catch the loading state.
    const delayedMock = {
      ...makeGraphMock(),
      delay: 2000,
    };

    const component = await mount(
      <MockedProvider mocks={[delayedMock]} addTypename={false}>
        <DocumentGraphLive corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    // While the query is in-flight the skeleton must be visible.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-skeleton"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });
});
