/**
 * Component tests for DocumentGraphGlimpse — the document-relationship graph
 * on the Corpus Intelligence home. The component is purely presentational
 * (deterministic d3-force layout → SVG), so it mounts directly with sample
 * data and no providers.
 *
 * NOTE: the JSX component import is kept in its own statement, separate from
 * any helper/constant imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { DocumentGraphGlimpse } from "../src/components/corpuses/CorpusHome/intelligence/DocumentGraphGlimpse";

const NODES = [
  { id: "Doc:1", title: "Alpha", fileType: "application/pdf", degree: 2 },
  { id: "Doc:2", title: "Beta", fileType: "application/pdf", degree: 1 },
  { id: "Doc:3", title: "Gamma", fileType: "application/pdf", degree: 1 },
];

const EDGES = [
  {
    id: "e1",
    source: "Doc:1",
    target: "Doc:2",
    label: "Cites",
    relationshipType: "RELATIONSHIP",
  },
  {
    id: "e2",
    source: "Doc:1",
    target: "Doc:3",
    label: null,
    relationshipType: "NOTES",
  },
];

test.describe("DocumentGraphGlimpse", () => {
  test("renders one node per document and one line per edge", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentGraphGlimpse
        nodes={NODES}
        edges={EDGES}
        totalNodeCount={3}
        totalEdgeCount={2}
        truncated={false}
      />
    );

    // The SVG and its node/edge groups render.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-svg"]')
    ).toBeVisible({ timeout: 10000 });

    await expect(
      page.locator('[data-testid="document-graph-glimpse-node"]')
    ).toHaveCount(3);

    await expect(
      page.locator('[data-testid="document-graph-glimpse-edges"] line')
    ).toHaveCount(2);

    // Meta line summarises the full graph.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-meta"]')
    ).toContainText("3 linked documents");
    // "total" qualifier: when truncated, the count includes edges that are
    // not drawn, so the copy must not imply every connection is on screen.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-meta"]')
    ).toContainText("2 total connections");

    await component.unmount();
  });

  test("shows a skeleton (not the empty state) while loading", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentGraphGlimpse
        nodes={[]}
        edges={[]}
        totalNodeCount={0}
        totalEdgeCount={0}
        truncated={false}
        loading={true}
      />
    );

    await expect(
      page.locator('[data-testid="document-graph-glimpse-skeleton"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator('[data-testid="document-graph-glimpse-empty"]')
    ).toHaveCount(0);

    await component.unmount();
  });

  test("renders a legend explaining edge styles and node size", async ({
    mount,
    page,
  }) => {
    // EDGES contains one RELATIONSHIP and one NOTES edge, so all three legend
    // entries should appear.
    const component = await mount(
      <DocumentGraphGlimpse
        nodes={NODES}
        edges={EDGES}
        totalNodeCount={3}
        totalEdgeCount={2}
        truncated={false}
      />
    );

    const legend = page.locator(
      '[data-testid="document-graph-glimpse-legend"]'
    );
    await expect(legend).toBeVisible({ timeout: 10000 });
    await expect(legend).toContainText("Citation / exhibit");
    await expect(legend).toContainText("Related filing");
    await expect(legend).toContainText("Larger = more connections");

    await component.unmount();
  });

  test("omits the 'related filing' legend entry when no notes edges exist", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentGraphGlimpse
        nodes={NODES.slice(0, 2)}
        edges={[EDGES[0]]} // RELATIONSHIP only
        totalNodeCount={2}
        totalEdgeCount={1}
        truncated={false}
      />
    );

    const legend = page.locator(
      '[data-testid="document-graph-glimpse-legend"]'
    );
    await expect(legend).toContainText("Citation / exhibit", {
      timeout: 10000,
    });
    await expect(legend).not.toContainText("Related filing");

    await component.unmount();
  });

  test("notes the most-connected subset when truncated", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentGraphGlimpse
        nodes={NODES.slice(0, 2)}
        edges={[EDGES[0]]}
        totalNodeCount={3}
        totalEdgeCount={2}
        truncated={true}
      />
    );

    await expect(
      page.locator('[data-testid="document-graph-glimpse-meta"]')
    ).toContainText("showing the most connected");

    await component.unmount();
  });

  test("shows an empty state when there are no relationships", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentGraphGlimpse
        nodes={[]}
        edges={[]}
        totalNodeCount={0}
        totalEdgeCount={0}
        truncated={false}
      />
    );

    await expect(
      page.locator('[data-testid="document-graph-glimpse-empty"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });
});
