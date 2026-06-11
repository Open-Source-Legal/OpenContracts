/**
 * Component tests for DocumentReferencesPanel — one document's slice of the
 * corpus reference web: outbound citations ("Cites", grouped by canonical
 * key with mention counts) and inbound citations ("Cited by", grouped by
 * source document).
 *
 * NOTE: each JSX-component import is kept in its own ``import`` statement,
 * separate from all other imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { DocumentReferencesPanel } from "../src/components/knowledge_base/document/DocumentReferencesPanel";
import { docScreenshot } from "./utils/docScreenshot";
import { GET_CORPUS_REFERENCES_FOR_DOCUMENT } from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";
const DOC_ID = "RG9jdW1lbnRUeXBlOjE=";
const EXHIBIT_ID = "RG9jdW1lbnRUeXBlOjI=";
const OTHER_DOC_ID = "RG9jdW1lbnRUeXBlOjM=";

const REFERENCE_ROWS = [
  // Outbound: two mentions of the same statute section → one grouped row ×2.
  {
    id: "ref1",
    referenceType: "LAW",
    canonicalKey: "dgcl:145",
    resolutionStatus: "RESOLVED",
    sourceAnnotation: {
      id: "ann1",
      rawText: "Section 145 of the Delaware General Corporation Law",
      linkUrl: "/d/owner/dgcl/dgcl-145",
      document: { id: DOC_ID, title: "Acme S-1 primary" },
    },
    targetDocument: { id: "Doc:statute", title: "DGCL § 145" },
  },
  {
    id: "ref2",
    referenceType: "LAW",
    canonicalKey: "dgcl:145",
    resolutionStatus: "RESOLVED",
    sourceAnnotation: {
      id: "ann2",
      rawText: "as permitted by Section 145 of the DGCL",
      linkUrl: "/d/owner/dgcl/dgcl-145",
      document: { id: DOC_ID, title: "Acme S-1 primary" },
    },
    targetDocument: { id: "Doc:statute", title: "DGCL § 145" },
  },
  // Outbound: an unresolved citation stays a ghost.
  {
    id: "ref3",
    referenceType: "LAW",
    canonicalKey: "securities-act:4(a)(2)",
    resolutionStatus: "EXTERNAL",
    sourceAnnotation: {
      id: "ann3",
      rawText: "Section 4(a)(2) of the Securities Act",
      linkUrl: null,
      document: { id: DOC_ID, title: "Acme S-1 primary" },
    },
    targetDocument: null,
  },
  // Outbound: an exhibit cross-reference.
  {
    id: "ref4",
    referenceType: "DOCUMENT",
    canonicalKey: null,
    resolutionStatus: "RESOLVED",
    sourceAnnotation: {
      id: "ann4",
      rawText: "filed as Exhibit 1.1 hereto",
      linkUrl: "/d/owner/corpus/exhibit-1-1",
      document: { id: DOC_ID, title: "Acme S-1 primary" },
    },
    targetDocument: { id: EXHIBIT_ID, title: "Exhibit 1.1: EX-1.1" },
  },
  // Inbound: another document cites this one.
  {
    id: "ref5",
    referenceType: "DOCUMENT",
    canonicalKey: null,
    resolutionStatus: "RESOLVED",
    sourceAnnotation: {
      id: "ann5",
      rawText: "as described in the primary S-1",
      linkUrl: "/d/owner/corpus/acme-s1",
      document: { id: OTHER_DOC_ID, title: "Amendment No. 1" },
    },
    targetDocument: { id: DOC_ID, title: "Acme S-1 primary" },
  },
];

const makeMock = (rows: typeof REFERENCE_ROWS) => ({
  request: {
    query: GET_CORPUS_REFERENCES_FOR_DOCUMENT,
    variables: { corpusId: CORPUS_ID, documentId: DOC_ID },
  },
  result: {
    data: {
      corpusReferences: {
        edges: rows.map((node) => ({ node })),
      },
    },
  },
});

test.describe("DocumentReferencesPanel", () => {
  test("splits outbound and inbound, grouping repeat citations", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[makeMock(REFERENCE_ROWS), makeMock(REFERENCE_ROWS)]}
          addTypename={false}
        >
          <DocumentReferencesPanel documentId={DOC_ID} corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    const panel = page.locator('[data-testid="references-panel"]');
    await expect(panel).toBeVisible({ timeout: 10000 });

    // Outbound: three groups (DGCL §145 ×2, Securities Act ghost, exhibit).
    await expect(
      page.locator('[data-testid="references-panel-outbound-row"]')
    ).toHaveCount(3);
    await expect(panel).toContainText("Cites");
    await expect(panel).toContainText("DGCL § 145");
    await expect(panel).toContainText("×2");
    await expect(panel).toContainText("cited, not yet ingested");
    await expect(panel).toContainText("Exhibit 1.1: EX-1.1");

    // Inbound: one source document.
    await expect(
      page.locator('[data-testid="references-panel-inbound-row"]')
    ).toHaveCount(1);
    await expect(panel).toContainText("Cited by");
    await expect(panel).toContainText("Amendment No. 1");

    await docScreenshot(page, "annotations--references-panel--with-data");

    await component.unmount();
  });

  test("clicking an outbound citation navigates to its link target", async ({
    mount,
    page,
  }) => {
    // The DGCL row carries a site-relative linkUrl; openSafeUrl must route it
    // through the SPA router (not a hard load). A matching <Route> renders a
    // marker once navigation lands.
    const component = await mount(
      <MemoryRouter initialEntries={["/"]}>
        <MockedProvider
          mocks={[makeMock(REFERENCE_ROWS), makeMock(REFERENCE_ROWS)]}
          addTypename={false}
        >
          <Routes>
            <Route
              path="/d/owner/dgcl/dgcl-145"
              element={<div data-testid="nav-arrived">arrived</div>}
            />
            <Route
              path="*"
              element={
                <DocumentReferencesPanel
                  documentId={DOC_ID}
                  corpusId={CORPUS_ID}
                />
              }
            />
          </Routes>
        </MockedProvider>
      </MemoryRouter>
    );

    const dgclRow = page
      .locator('[data-testid="references-panel-outbound-row"]')
      .filter({ hasText: "DGCL § 145" });
    await expect(dgclRow).toBeVisible({ timeout: 10000 });
    await dgclRow.click();

    await expect(page.locator('[data-testid="nav-arrived"]')).toBeVisible();

    await component.unmount();
  });

  test("shows the empty state when the document has no references", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[makeMock([]), makeMock([])]}
          addTypename={false}
        >
          <DocumentReferencesPanel documentId={DOC_ID} corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.locator('[data-testid="references-panel-empty"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("explains corpus requirement when mounted without a corpus", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={[]} addTypename={false}>
          <DocumentReferencesPanel documentId={DOC_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.locator('[data-testid="references-panel-no-corpus"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });
});
