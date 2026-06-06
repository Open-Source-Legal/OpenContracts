import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { DndContext } from "@dnd-kit/core";
import { ModernDocumentItem } from "../src/components/documents/ModernDocumentItem";
import { ToastContainer } from "react-toastify";
import {
  DocumentType,
  DocumentProcessingStatus,
} from "../src/types/graphql-api";
import { openedCorpus } from "../src/graphql/cache";
import {
  GET_DOC_RELATIONSHIPS_FOR_DOC,
  GET_DOCUMENT_PDF_URL,
} from "../src/graphql/queries";
import { PDF_MIME_TYPE } from "../src/assets/configurations/constants";
import { ReactiveVarObserver } from "./utils/ReactiveVarObserver";
import { docScreenshot } from "./utils/docScreenshot";

/** Minimal document fixture with overridable fields. */
function makeDocument(overrides: Partial<DocumentType> = {}): DocumentType {
  return {
    id: "RG9jdW1lbnRUeXBlOjE=",
    title: "Test Document.pdf",
    description: "A test document",
    icon: null,
    pdfFile: "https://example.com/doc.pdf",
    fileType: "pdf",
    pageCount: 5,
    backendLock: false,
    isPublic: false,
    is_selected: false,
    is_open: false,
    myPermissions: [],
    processingStatus: DocumentProcessingStatus.COMPLETED,
    processingError: null,
    canRetry: false,
    ...overrides,
  } as DocumentType;
}

// Named `renderWithProviders` (not `mount`) to avoid shadowing Playwright CT's
// `mount` fixture destructured from each test's context.
function renderWithProviders(
  ui: React.ReactElement,
  mount: (el: React.ReactElement) => Promise<unknown>,
  mocks: MockedResponse[] = []
) {
  return mount(
    <MockedProvider mocks={mocks} addTypename={false}>
      <MemoryRouter>
        <DndContext>{ui}</DndContext>
        {/* react-toastify sink so toast.error(...) in handlers is assertable. */}
        <ToastContainer />
      </MemoryRouter>
    </MockedProvider>
  );
}

/**
 * DndContext's useDraggable listeners intercept pointer events on the
 * container, preventing React's synthetic click events from reaching children.
 * Invoke the React onClick handler directly via the __reactProps$ fiber.
 *
 * Tested against React 18.x. The `__reactProps$` key is a React internal with
 * no semver guarantee. Two things can silently break this shim on upgrade:
 *   1. The property name stem (`__reactProps$`) could be renamed/removed.
 *   2. The suffix after `$` is a build-specific random ID that changes on
 *      every React build (including minor/patch versions), so we must never
 *      hard-code the full key — always find it via `Object.keys(el).find(...)`.
 * If this breaks after a React upgrade, check whether DndContext now forwards
 * pointer events to children and remove this shim.
 */
async function clickViaReact(
  page: import("@playwright/test").Page,
  selector: string
) {
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) throw new Error(`Element not found: ${sel}`);
    const propsKey = Object.keys(el).find((k) => k.startsWith("__reactProps$"));
    if (!propsKey) throw new Error("React props not found on element");
    const props = (el as any)[propsKey];
    if (typeof props?.onClick !== "function")
      throw new Error("onClick handler missing");
    props.onClick({
      type: "click",
      bubbles: true,
      cancelable: true,
      stopPropagation: () => {},
      preventDefault: () => {},
      shiftKey: false,
      nativeEvent: {},
      target: el,
      currentTarget: el,
    });
  }, selector);
}

// ---------------------------------------------------------------------------
// Card View — thumbnail, badges, meta
// ---------------------------------------------------------------------------
test.describe("ModernDocumentItem — card view rendering", () => {
  test("renders fallback thumbnail when icon is not provided", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ icon: null });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    await expect(page.getByText("Test Document.pdf")).toBeVisible();
    // Fallback icon class is applied when icon is absent
    await expect(page.locator("img.fallback-icon")).toHaveCount(1);
  });

  test("renders custom icon when provided", async ({ mount, page }) => {
    const doc = makeDocument({ icon: "https://example.com/icon.png" });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    // When icon is set, fallback is NOT rendered, real img is
    await expect(page.locator("img.fallback-icon")).toHaveCount(0);
    await expect(
      page.locator('img[src="https://example.com/icon.png"]')
    ).toBeVisible();
  });

  test("shows page count, public badge, and file type", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({
      pageCount: 42,
      isPublic: true,
      fileType: "pdf",
    });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    await expect(page.getByText("42p")).toBeVisible();
    await expect(page.getByText("Public")).toBeVisible();
    // FileTypeBadge renders the fileType literal (CSS upper-cases it
    // visually, the DOM text is lowercase).
    await expect(page.getByText("pdf", { exact: true })).toBeVisible();
  });

  test("shows doc-type label count badge from docTypeLabels (PR #1829)", async ({
    mount,
    page,
  }) => {
    // PR #1829 switched the badge source from the Relay-connection
    // ``docLabelAnnotations`` to the flat ``docTypeLabels`` field. Card view
    // renders a Tag meta-item showing the label count. pageCount 42 keeps the
    // page badge ("42p") from colliding with the exact "2" label-count match.
    const doc = makeDocument({
      pageCount: 42,
      docTypeLabels: [
        { labelType: "DOC_TYPE_LABEL", text: "Contract" },
        { labelType: "DOC_TYPE_LABEL", text: "NDA" },
      ],
    } as Partial<DocumentType>);

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    await expect(page.getByText("Test Document.pdf")).toBeVisible();
    await expect(page.getByText("2", { exact: true })).toBeVisible();

    await docScreenshot(
      page,
      "documents--modern-document-item--doc-type-badge"
    );
  });

  test("hides doc-type label badge when docTypeLabels is empty", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({
      pageCount: 42,
      docTypeLabels: [],
    } as Partial<DocumentType>);

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    await expect(page.getByText("Test Document.pdf")).toBeVisible();
    // No label-count meta-item should render for an empty list.
    await expect(page.getByText("2", { exact: true })).toHaveCount(0);
  });

  test("shows version badge when document has history", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({
      hasVersionHistory: true,
      versionCount: 3,
      isLatestVersion: true,
      canViewHistory: true,
    });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    // VersionBadge renders a role="button" with this exact aria-label when
    // hasHistory is true. The surrounding draggable wrapper also has
    // role="button", so match the badge's label exactly to avoid a strict
    // mode violation.
    await expect(
      page.getByRole("button", {
        name: "Version 3, click to view history",
        exact: true,
      })
    ).toBeVisible();
  });

  test("shows relationship badge with count when relationships exist", async ({
    mount,
    page,
  }) => {
    const rels = [
      {
        id: "rel-1",
        relationshipType: "RELATIONSHIP",
        sourceDocument: {
          id: "RG9jdW1lbnRUeXBlOjE=",
          title: "Test Document.pdf",
        },
        targetDocument: {
          id: "other-doc",
          title: "Other Document",
        },
        annotationLabel: {
          id: "label-1",
          text: "references",
          color: "#14b8a6",
        },
      },
      {
        id: "rel-2",
        relationshipType: "NOTES",
        sourceDocument: {
          id: "other-doc-2",
          title: "Inbound Linker",
        },
        targetDocument: {
          id: "RG9jdW1lbnRUeXBlOjE=",
          title: "Test Document.pdf",
        },
        annotationLabel: null,
      },
    ];

    const doc = makeDocument({
      docRelationshipCount: 2,
    });

    // Relationships are now fetched lazily on hover — provide a mock for the
    // GET_DOC_RELATIONSHIPS_FOR_DOC query that the badge triggers.
    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_DOC_RELATIONSHIPS_FOR_DOC,
          variables: { documentId: doc.id, corpusId: null },
        },
        result: { data: { bulkDocRelationships: rels } },
      },
    ];

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount,
      mocks
    );

    // Number is rendered in the badge immediately (from docRelationshipCount).
    await expect(page.getByText("2").first()).toBeVisible();

    // Trigger the hover handler directly via React props: the popup is
    // hidden by CSS so a hover() call would time out waiting for visibility.
    // Walk up from the popup header span to the badge wrapper that owns
    // the onMouseEnter handler. See `clickViaReact` above for precedent.
    await page.evaluate(() => {
      const span = Array.from(document.querySelectorAll("span")).find(
        (s) => s.textContent === "2 Linked Documents"
      );
      let node: HTMLElement | null = span?.closest("div") ?? null;
      while (node) {
        const propsKey = Object.keys(node).find((k) =>
          k.startsWith("__reactProps$")
        );
        const props = propsKey ? (node as any)[propsKey] : null;
        if (typeof props?.onMouseEnter === "function") {
          props.onMouseEnter({});
          return;
        }
        node = node.parentElement;
      }
      throw new Error("Could not find onMouseEnter handler on badge ancestor");
    });

    // After the lazy query resolves, the popup contents should be in the DOM.
    await expect(
      page.locator('text="2 Linked Documents"').first()
    ).toBeAttached();
    await expect(page.getByText("Other Document").first()).toBeAttached();
    await expect(page.getByText("Inbound Linker").first()).toBeAttached();
  });

  test("renders title fallback when title missing", async ({ mount, page }) => {
    const doc = makeDocument({ title: undefined });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    await expect(page.getByText("Untitled Document").first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// List View — thumbnail, badges, meta
// ---------------------------------------------------------------------------
test.describe("ModernDocumentItem — list view rendering", () => {
  test("renders description, file type, and page count", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({
      description: "A quarterly contract revision",
      fileType: "pdf",
      pageCount: 12,
    });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    await expect(page.getByText("Test Document.pdf")).toBeVisible();
    await expect(page.getByText("A quarterly contract revision")).toBeVisible();
    // List view uppercases the fileType client-side
    await expect(page.getByText("PDF", { exact: true })).toBeVisible();
    await expect(page.getByText("12 pages")).toBeVisible();
  });

  test("shows public badge in list meta", async ({ mount, page }) => {
    const doc = makeDocument({ isPublic: true });
    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );
    await expect(page.getByText("Public")).toBeVisible();
  });

  test("shows version info in list meta and marks outdated versions", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({
      hasVersionHistory: true,
      versionCount: 4,
      isLatestVersion: false,
    });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    // v4 (4 versions) should appear in list meta
    await expect(page.getByText(/v4/).first()).toBeVisible();
    await expect(page.getByText(/4 versions/).first()).toBeVisible();
  });

  test("shows relationship count badge in list meta", async ({
    mount,
    page,
  }) => {
    const rels = [
      {
        id: "rel-1",
        relationshipType: "RELATIONSHIP",
        sourceDocument: {
          id: "RG9jdW1lbnRUeXBlOjE=",
          title: "Test Document.pdf",
        },
        targetDocument: {
          id: "o1",
          title: "Linked Doc One",
        },
        annotationLabel: {
          id: "lbl",
          text: "cites",
          color: "#3b82f6",
        },
      },
    ];
    const doc = makeDocument({
      docRelationshipCount: 1,
    });

    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_DOC_RELATIONSHIPS_FOR_DOC,
          variables: { documentId: doc.id, corpusId: null },
        },
        result: { data: { bulkDocRelationships: rels } },
      },
    ];

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount,
      mocks
    );

    // The hover popup is hidden via CSS visibility, but React's onMouseEnter
    // is on the badge wrapper (an ancestor). Walk up from the popup header
    // span to find the element with the React onMouseEnter handler attached
    // and invoke it directly. See `clickViaReact` above for the precedent.
    await page.evaluate(() => {
      const span = Array.from(document.querySelectorAll("span")).find(
        (s) => s.textContent === "1 Linked Document"
      );
      let node: HTMLElement | null = span?.closest("div") ?? null;
      while (node) {
        const propsKey = Object.keys(node).find((k) =>
          k.startsWith("__reactProps$")
        );
        const props = propsKey ? (node as any)[propsKey] : null;
        if (typeof props?.onMouseEnter === "function") {
          props.onMouseEnter({});
          return;
        }
        node = node.parentElement;
      }
      throw new Error("Could not find onMouseEnter handler on badge ancestor");
    });

    // After the fetch resolves, the linked-doc title should be in the popup DOM.
    await expect(page.getByText("Linked Doc One").first()).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// Selection & is_selected styling
// ---------------------------------------------------------------------------
test.describe("ModernDocumentItem — selection", () => {
  test("applies is-selected class when is_selected is true (card view)", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ is_selected: true });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    await expect(page.locator(".is-selected")).toBeVisible();
    // Check mark icon is rendered inside the checkbox
    await expect(page.locator(".checkbox.selected")).toBeVisible();
  });

  test("applies is-selected class when is_selected is true (list view)", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ is_selected: true });
    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );
    await expect(page.locator(".is-selected")).toBeVisible();
  });

  test("checkbox click invokes onShiftClick callback (card view)", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument();
    let shiftClicked: string | null = null;

    await renderWithProviders(
      <ModernDocumentItem
        item={doc}
        viewMode="card"
        onShiftClick={(d) => {
          shiftClicked = d.id;
        }}
      />,
      mount
    );

    await clickViaReact(page, ".checkbox");

    await expect
      .poll(() => shiftClicked, { timeout: 2000 })
      .toBe("RG9jdW1lbnRUeXBlOjE=");
  });
});

// ---------------------------------------------------------------------------
// Permission-gated actions
// ---------------------------------------------------------------------------
test.describe("ModernDocumentItem — permissions", () => {
  test("hides edit button for read-only users (list view)", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ myPermissions: ["read_document"] });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    // Without CAN_UPDATE, the edit button is not rendered
    await expect(page.locator('button[title="Edit"]')).toHaveCount(0);
    // Baseline sanity: the Open button is always present
    await expect(page.locator('button[title="Open"]')).toBeVisible();
  });

  test("shows edit button for users with CAN_UPDATE (list view)", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ myPermissions: ["update_document"] });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    await expect(page.locator('button[title="Edit"]')).toBeVisible();
  });

  test("hides remove button when removeFromCorpus is absent", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument();

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    await expect(page.locator('button[title="Remove"]')).toHaveCount(0);
  });

  test("shows remove button when removeFromCorpus is provided", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument();

    await renderWithProviders(
      <ModernDocumentItem
        item={doc}
        viewMode="list"
        removeFromCorpus={() => {}}
      />,
      mount
    );

    await expect(page.locator('button[title="Remove"]')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Action button behaviors
// ---------------------------------------------------------------------------
test.describe("ModernDocumentItem — action buttons", () => {
  test("click on View button triggers viewingDocument reactive var", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument();

    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter>
          <DndContext>
            <ModernDocumentItem item={doc} viewMode="list" />
            <ReactiveVarObserver />
          </DndContext>
        </MemoryRouter>
      </MockedProvider>
    );

    await clickViaReact(page, 'button[title="View"]');

    await expect(page.getByTestId("rv-observer")).toHaveAttribute(
      "data-viewing-id",
      doc.id,
      { timeout: 2000 }
    );
  });

  test("click on Edit button triggers editingDocument reactive var", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ myPermissions: ["update_document"] });

    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter>
          <DndContext>
            <ModernDocumentItem item={doc} viewMode="list" />
            <ReactiveVarObserver />
          </DndContext>
        </MemoryRouter>
      </MockedProvider>
    );

    await clickViaReact(page, 'button[title="Edit"]');

    await expect(page.getByTestId("rv-observer")).toHaveAttribute(
      "data-editing-id",
      doc.id,
      { timeout: 2000 }
    );
  });

  test("click on Remove button invokes removeFromCorpus with document id", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument();
    let removedIds: string[] = [];

    await renderWithProviders(
      <ModernDocumentItem
        item={doc}
        viewMode="list"
        removeFromCorpus={(ids) => {
          removedIds = ids;
        }}
      />,
      mount
    );

    await clickViaReact(page, 'button[title="Remove"]');

    await expect.poll(() => removedIds.length, { timeout: 2000 }).toBe(1);
    expect(removedIds[0]).toBe(doc.id);
  });

  test("click on Open button calls onClick callback", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument();
    let clicked: string | null = null;
    openedCorpus(null);

    await renderWithProviders(
      <ModernDocumentItem
        item={doc}
        viewMode="list"
        onClick={(d) => {
          clicked = d.id;
        }}
      />,
      mount
    );

    await clickViaReact(page, 'button[title="Open"]');

    await expect.poll(() => clicked, { timeout: 2000 }).toBe(doc.id);
  });

  test("hides download button when pdfFile is missing", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ pdfFile: undefined });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    await expect(page.locator('button[title="Download"]')).toHaveCount(0);
  });

  test("shows download button when pdfFile is present", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ pdfFile: "https://example.com/doc.pdf" });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    await expect(page.locator('button[title="Download"]')).toBeVisible();
  });

  test("download surfaces a toast when the lazy PDF URL resolves to null", async ({
    mount,
    page,
  }) => {
    // pdfFile is no longer fetched per card; the button shows for any
    // PDF-typed doc and the signed URL is resolved on click. When the lazy
    // query yields no file, the handler must surface a toast instead of a
    // silent no-op (see DocumentItem/ModernDocumentItem handleDownload).
    const doc = makeDocument({ pdfFile: undefined, fileType: PDF_MIME_TYPE });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount,
      [
        {
          request: {
            query: GET_DOCUMENT_PDF_URL,
            variables: { documentId: doc.id },
          },
          result: {
            data: { document: { id: doc.id, pdfFile: null } },
          },
        },
      ]
    );

    await clickViaReact(page, 'button[title="Download"]');

    await expect(
      page.getByText("No downloadable file is available for this document.")
    ).toBeVisible({ timeout: 5000 });
  });
});

// ---------------------------------------------------------------------------
// Processing state & overlay
// ---------------------------------------------------------------------------
test.describe("ModernDocumentItem — processing state", () => {
  test("shows backend-locked styling and Processing overlay (card)", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({
      processingStatus: DocumentProcessingStatus.PROCESSING,
      backendLock: true,
    });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    await expect(page.locator(".backend-locked")).toBeVisible();
    await expect(page.getByText("Processing...")).toBeVisible();
  });

  test("shows floating delete button while processing when removeFromCorpus provided", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({
      processingStatus: DocumentProcessingStatus.PENDING,
      backendLock: true,
    });

    await renderWithProviders(
      <ModernDocumentItem
        item={doc}
        viewMode="card"
        removeFromCorpus={() => {}}
      />,
      mount
    );

    await expect(
      page.getByLabel("Remove processing document from corpus")
    ).toBeVisible();
  });

  test("disables action buttons when backendLock is true", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({
      processingStatus: DocumentProcessingStatus.PROCESSING,
      backendLock: true,
    });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    // Open button should exist but be disabled due to backendLock
    await expect(page.locator('button[title="Open"]')).toBeDisabled();
    await expect(page.locator('button[title="View"]')).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Context menu (right-click via contextMenu event dispatch)
//
// DndContext pointer listeners don't intercept contextmenu, but to avoid
// relying on coordinate-based click targeting we walk up the DOM from a known
// element and invoke the React onContextMenu prop directly. Same React 18.x
// `__reactProps$` caveat as clickViaReact applies (including the build-hash
// suffix: never hard-code the full key, always discover it via Object.keys).
// ---------------------------------------------------------------------------

async function openContextMenu(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    const dispatch = (el: HTMLElement): boolean => {
      const propsKey = Object.keys(el).find((k) =>
        k.startsWith("__reactProps$")
      );
      if (!propsKey) return false;
      const props = (el as any)[propsKey];
      if (typeof props?.onContextMenu !== "function") return false;
      props.onContextMenu({
        preventDefault: () => {},
        stopPropagation: () => {},
        clientX: 100,
        clientY: 100,
      });
      return true;
    };

    // Prefer walking up from the checkbox — it's nested inside the item root
    // and guarantees we target the correct card/list ancestor. If the
    // checkbox is ever conditionally hidden (e.g. future read-only view),
    // fall back to scanning the entire document for the first element with
    // an onContextMenu React prop, which will be the item root because
    // nothing else in the tree attaches one.
    let el: HTMLElement | null = document.querySelector(
      ".checkbox"
    ) as HTMLElement | null;
    while (el) {
      if (dispatch(el)) return;
      el = el.parentElement;
    }

    // Fallback: scan every element in the document for a React onContextMenu
    // handler. Order is document order, so the outermost handler wins — which
    // is fine because only the item root attaches one.
    const all = document.querySelectorAll<HTMLElement>("*");
    for (const candidate of Array.from(all)) {
      if (dispatch(candidate)) return;
    }

    throw new Error(
      "openContextMenu: no element in the document carries a React " +
        "onContextMenu prop — is the ModernDocumentItem rendered?"
    );
  });
}

test.describe("ModernDocumentItem — context menu", () => {
  test("right-click opens context menu with document actions", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ pdfFile: "https://example.com/doc.pdf" });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    await openContextMenu(page);

    await expect(page.getByText("Open Document")).toBeVisible({
      timeout: 3000,
    });
    await expect(page.getByText("View Details")).toBeVisible();
    await expect(page.getByText("Download PDF")).toBeVisible();
  });

  test("context menu shows 'Link to Document' when handler provided", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument();

    await renderWithProviders(
      <ModernDocumentItem
        item={doc}
        viewMode="list"
        onLinkToDocument={() => {}}
      />,
      mount
    );

    await openContextMenu(page);

    await expect(page.getByText("Link to Document...")).toBeVisible({
      timeout: 3000,
    });
  });

  test("context menu shows 'Remove from Corpus' when removeFromCorpus provided", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument();

    await renderWithProviders(
      <ModernDocumentItem
        item={doc}
        viewMode="list"
        removeFromCorpus={() => {}}
      />,
      mount
    );

    await openContextMenu(page);

    await expect(page.getByText("Remove from Corpus")).toBeVisible({
      timeout: 3000,
    });
  });

  test("context menu shows 'Select' vs 'Deselect' based on is_selected", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ is_selected: true });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    await openContextMenu(page);

    await expect(page.getByText("Deselect")).toBeVisible({ timeout: 3000 });
  });

  test("context menu shows 'View Version History' for docs with history", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({
      hasVersionHistory: true,
      canViewHistory: true,
      versionCount: 2,
    });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    await openContextMenu(page);

    await expect(page.getByText("View Version History")).toBeVisible({
      timeout: 3000,
    });
  });

  test("context menu shows Edit Document when user has CAN_UPDATE", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ myPermissions: ["update_document"] });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    await openContextMenu(page);

    await expect(page.getByText("Edit Document")).toBeVisible({
      timeout: 3000,
    });
  });
});

// ---------------------------------------------------------------------------
// Lazy relationship fetching
//
// The relationship badge fetches its detail data lazily on hover/click/focus
// via useLazyQuery. These tests pin every branch of `handleRelationshipHover`
// (count==0 / data already loaded / loading already in-flight / errored /
// fetch fires) and exercise the onMouseEnter, onClick, and onFocus triggers
// so coverage captures keyboard navigation and the touch-device fallback.
// ---------------------------------------------------------------------------

/** Walk up from a known descendant to find the React `onMouseEnter` ancestor. */
async function fireRelationshipHover(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    // Match the popup header span ("N Linked Document(s)") and walk up.
    const span = Array.from(document.querySelectorAll("span")).find((s) =>
      /^\d+ Linked Document/.test(s.textContent ?? "")
    );
    let node: HTMLElement | null = span?.closest("div") ?? null;
    while (node) {
      const propsKey = Object.keys(node).find((k) =>
        k.startsWith("__reactProps$")
      );
      const props = propsKey ? (node as any)[propsKey] : null;
      if (typeof props?.onMouseEnter === "function") {
        props.onMouseEnter({});
        return;
      }
      node = node.parentElement;
    }
    throw new Error("Could not find onMouseEnter handler on badge ancestor");
  });
}

/** Same walk-up, but invoke the React `onFocus` (keyboard navigation). */
async function fireRelationshipFocus(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    const span = Array.from(document.querySelectorAll("span")).find((s) =>
      /^\d+ Linked Document/.test(s.textContent ?? "")
    );
    let node: HTMLElement | null = span?.closest("div") ?? null;
    while (node) {
      const propsKey = Object.keys(node).find((k) =>
        k.startsWith("__reactProps$")
      );
      const props = propsKey ? (node as any)[propsKey] : null;
      if (typeof props?.onFocus === "function" && props.onMouseEnter) {
        // Match the wrapper that has BOTH onFocus and onMouseEnter — that's
        // RelationshipBadgeContainer, not the outer card focus handler.
        props.onFocus({});
        return;
      }
      node = node.parentElement;
    }
    throw new Error("Could not find onFocus handler on badge wrapper");
  });
}

/** Same walk-up, but invoke the React `onClick` (touch-device fallback). */
async function fireRelationshipClick(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    const span = Array.from(document.querySelectorAll("span")).find((s) =>
      /^\d+ Linked Document/.test(s.textContent ?? "")
    );
    let node: HTMLElement | null = span?.closest("div") ?? null;
    while (node) {
      const propsKey = Object.keys(node).find((k) =>
        k.startsWith("__reactProps$")
      );
      const props = propsKey ? (node as any)[propsKey] : null;
      if (typeof props?.onClick === "function" && props.onMouseEnter) {
        // Match the wrapper that has BOTH onClick and onMouseEnter — that's
        // RelationshipBadgeContainer, not the outer card click handler.
        props.onClick({
          stopPropagation: () => {},
          preventDefault: () => {},
        });
        return;
      }
      node = node.parentElement;
    }
    throw new Error("Could not find onClick handler on badge wrapper");
  });
}

test.describe("ModernDocumentItem — lazy relationship fetching", () => {
  test.beforeEach(() => {
    // Some earlier tests set the openedCorpus reactive var; reset to null so
    // the lazy query's variables match the mocks below.
    openedCorpus(null);
  });

  test("hover triggers fetchDocRelationships when count > 0", async ({
    mount,
    page,
  }) => {
    const rels = [
      {
        id: "rel-x",
        relationshipType: "RELATIONSHIP",
        sourceDocument: { id: "RG9jdW1lbnRUeXBlOjE=", title: "Test" },
        targetDocument: { id: "linked-1", title: "Hover Linked Doc" },
        annotationLabel: { id: "lbl", text: "ref", color: "#000" },
      },
    ];
    const doc = makeDocument({ docRelationshipCount: 1 });

    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_DOC_RELATIONSHIPS_FOR_DOC,
          variables: { documentId: doc.id, corpusId: null },
        },
        result: { data: { bulkDocRelationships: rels } },
      },
    ];

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount,
      mocks
    );

    await expect(page.getByText("1").first()).toBeVisible();

    // Linked-doc title is rendered only after the lazy fetch resolves.
    await expect(page.getByText("Hover Linked Doc")).toHaveCount(0);

    await fireRelationshipHover(page);

    // After the hover, the popup should populate from the fetch result.
    await expect(page.getByText("Hover Linked Doc").first()).toBeAttached();
  });

  test("does not fetch when docRelationshipCount is 0", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ docRelationshipCount: 0 });

    // The badge is gated at render time by `!!docRelationshipCount &&
    // docRelationshipCount > 0`, so the hover handler is never reachable from
    // the DOM. Mount with no mocks — if any fetch fires, MockedProvider
    // surfaces an unhandled-mock warning and fails the test.
    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount,
      []
    );

    // Badge is NOT in DOM when count is 0.
    await expect(page.getByText("Linked Document")).toHaveCount(0);
  });

  test("click trigger fires fetch (touch-device fallback)", async ({
    mount,
    page,
  }) => {
    const rels = [
      {
        id: "rel-tap",
        relationshipType: "RELATIONSHIP",
        sourceDocument: { id: "RG9jdW1lbnRUeXBlOjE=", title: "Test" },
        targetDocument: { id: "linked-tap", title: "Tap Linked Doc" },
        annotationLabel: null,
      },
    ];
    const doc = makeDocument({ docRelationshipCount: 1 });

    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_DOC_RELATIONSHIPS_FOR_DOC,
          variables: { documentId: doc.id, corpusId: null },
        },
        result: { data: { bulkDocRelationships: rels } },
      },
    ];

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount,
      mocks
    );

    await expect(page.getByText("1").first()).toBeVisible();

    await fireRelationshipClick(page);

    await expect(page.getByText("Tap Linked Doc").first()).toBeAttached();
  });

  test("focus trigger fires fetch (keyboard navigation)", async ({
    mount,
    page,
  }) => {
    const rels = [
      {
        id: "rel-focus",
        relationshipType: "RELATIONSHIP",
        sourceDocument: { id: "RG9jdW1lbnRUeXBlOjE=", title: "Test" },
        targetDocument: { id: "linked-focus", title: "Focus Linked Doc" },
        annotationLabel: null,
      },
    ];
    const doc = makeDocument({ docRelationshipCount: 1 });

    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_DOC_RELATIONSHIPS_FOR_DOC,
          variables: { documentId: doc.id, corpusId: null },
        },
        result: { data: { bulkDocRelationships: rels } },
      },
    ];

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount,
      mocks
    );

    await expect(page.getByText("1").first()).toBeVisible();

    await fireRelationshipFocus(page);

    await expect(page.getByText("Focus Linked Doc").first()).toBeAttached();
  });

  test("network error short-circuits subsequent hovers", async ({
    mount,
    page,
  }) => {
    const doc = makeDocument({ docRelationshipCount: 1 });

    // Single mock that returns a network error; without the `error` guard the
    // second hover would consume a second mock (which we deliberately don't
    // provide), and MockedProvider would surface "No more mocked responses".
    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_DOC_RELATIONSHIPS_FOR_DOC,
          variables: { documentId: doc.id, corpusId: null },
        },
        error: new Error("network down"),
      },
    ];

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount,
      mocks
    );

    await fireRelationshipHover(page);

    // Error fallback replaces the misleading "Loading..." text.
    await expect(page.getByText("Couldn't load relationships.")).toBeAttached();

    // Second hover must NOT retrigger the failing fetch.
    await fireRelationshipHover(page);
    await expect(page.getByText("Couldn't load relationships.")).toBeAttached();
  });

  test("repeat hovers do not refetch once data is loaded", async ({
    mount,
    page,
  }) => {
    const rels = [
      {
        id: "rel-once",
        relationshipType: "RELATIONSHIP",
        sourceDocument: { id: "RG9jdW1lbnRUeXBlOjE=", title: "Test" },
        targetDocument: { id: "linked-once", title: "Cached Linked Doc" },
        annotationLabel: null,
      },
    ];
    const doc = makeDocument({ docRelationshipCount: 1 });

    // Provide ONLY ONE matching mock. If the component refetches, Apollo's
    // MockedProvider would log a "no more mocked responses" warning — but
    // more importantly, the second/third hovers should be short-circuited by
    // the relationshipsData guard before they hit the network.
    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_DOC_RELATIONSHIPS_FOR_DOC,
          variables: { documentId: doc.id, corpusId: null },
        },
        result: { data: { bulkDocRelationships: rels } },
      },
    ];

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount,
      mocks
    );

    await fireRelationshipHover(page);
    await expect(page.getByText("Cached Linked Doc").first()).toBeAttached();

    // Subsequent hovers exercise the early-return guard (relationshipsData
    // is now populated). The popup contents stay attached without errors.
    await fireRelationshipHover(page);
    await fireRelationshipHover(page);
    await expect(page.getByText("Cached Linked Doc").first()).toBeAttached();
  });
});
