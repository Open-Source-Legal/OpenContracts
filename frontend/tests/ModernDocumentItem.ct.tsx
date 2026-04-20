import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { DndContext } from "@dnd-kit/core";
import { ModernDocumentItem } from "../src/components/documents/ModernDocumentItem";
import {
  DocumentType,
  DocumentProcessingStatus,
  DocumentRelationshipType,
} from "../src/types/graphql-api";
import { openedCorpus } from "../src/graphql/cache";
import { ReactiveVarObserver } from "./utils/ReactiveVarObserver";

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
  mount: (el: React.ReactElement) => Promise<unknown>
) {
  return mount(
    <MockedProvider mocks={[]} addTypename={false}>
      <MemoryRouter>
        <DndContext>{ui}</DndContext>
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
 * no semver guarantee — if this breaks after a React upgrade, check whether
 * DndContext now forwards pointer events to children and remove this shim.
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
    const rels: DocumentRelationshipType[] = [
      {
        id: "rel-1",
        relationshipType: "RELATIONSHIP",
        sourceDocument: {
          id: "RG9jdW1lbnRUeXBlOjE=",
          title: "Test Document.pdf",
        } as any,
        targetDocument: {
          id: "other-doc",
          title: "Other Document",
        } as any,
        annotationLabel: {
          id: "label-1",
          text: "references",
          color: "#14b8a6",
        } as any,
      } as any,
      {
        id: "rel-2",
        relationshipType: "NOTES",
        sourceDocument: {
          id: "other-doc-2",
          title: "Inbound Linker",
        } as any,
        targetDocument: {
          id: "RG9jdW1lbnRUeXBlOjE=",
          title: "Test Document.pdf",
        } as any,
        annotationLabel: null,
      } as any,
    ];

    const doc = makeDocument({
      docRelationshipCount: 2,
      allDocRelationships: rels,
    });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="card" />,
      mount
    );

    // Number is rendered in the badge
    await expect(page.getByText("2").first()).toBeVisible();
    // Popup text is present in the DOM even before hover (visibility:hidden)
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
    const rels: DocumentRelationshipType[] = [
      {
        id: "rel-1",
        relationshipType: "RELATIONSHIP",
        sourceDocument: {
          id: "RG9jdW1lbnRUeXBlOjE=",
          title: "Test Document.pdf",
        } as any,
        targetDocument: {
          id: "o1",
          title: "Linked Doc One",
        } as any,
        annotationLabel: {
          id: "lbl",
          text: "cites",
          color: "#3b82f6",
        } as any,
      } as any,
    ];
    const doc = makeDocument({
      docRelationshipCount: 1,
      allDocRelationships: rels,
    });

    await renderWithProviders(
      <ModernDocumentItem item={doc} viewMode="list" />,
      mount
    );

    // "1 Linked Document" (singular) should be in the popup DOM
    await expect(
      page.locator('text="1 Linked Document"').first()
    ).toBeAttached();
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
// `__reactProps$` caveat as clickViaReact applies.
// ---------------------------------------------------------------------------

async function openContextMenu(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    // Walk up from the title element to find an ancestor with onContextMenu.
    let el: HTMLElement | null = document.querySelector(
      ".checkbox"
    ) as HTMLElement | null;
    while (el) {
      const propsKey = Object.keys(el).find((k) =>
        k.startsWith("__reactProps$")
      );
      if (propsKey) {
        const props = (el as any)[propsKey];
        if (typeof props?.onContextMenu === "function") {
          props.onContextMenu({
            preventDefault: () => {},
            stopPropagation: () => {},
            clientX: 100,
            clientY: 100,
          });
          return;
        }
      }
      el = el.parentElement;
    }
    throw new Error(
      "openContextMenu: no onContextMenu handler found walking up from .checkbox — " +
        "is the component rendered with the checkbox present?"
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
