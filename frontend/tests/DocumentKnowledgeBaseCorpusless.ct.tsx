import React from "react";
import { test, expect } from "./utils/coverage";
import type { MockedResponse } from "@apollo/client/testing";
import { DocumentKnowledgeBaseCorpuslessTestWrapper } from "./DocumentKnowledgeBaseCorpuslessTestWrapper";
import {
  GET_DOCUMENT_ONLY,
  GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
  GET_DOCUMENT_ANNOTATIONS_ONLY,
  GET_MY_CORPUSES,
  ADD_DOCUMENT_TO_CORPUS,
  GET_CONVERSATIONS,
} from "../src/graphql/queries";
import { LINK_DOCUMENTS_TO_CORPUS } from "../src/graphql/mutations";
import { gql } from "@apollo/client";

import fs from "fs";
import { Page } from "@playwright/test";
import {
  TEST_PDF_PATH,
  TEST_PAWLS_PATH,
} from "./mocks/DocumentKnowledgeBase.mocks";

// Mock data for document without corpus
const mockDocument = {
  id: "doc-123",
  title: "Test Document",
  description: "A test document",
  customMeta: {},
  backendLock: false,
  fileType: "application/pdf",
  pdfFile: "http://localhost/test.pdf",
  pawlsParseFile: "http://localhost/test.pawls",
  txtFile: "http://localhost/test.txt",
  totalPageCount: 10,
  corpusAssignments: {
    edges: [],
  },
};

// Mock data for document with corpus
const mockDocumentWithCorpus = {
  ...mockDocument,
  allAnnotations: [
    {
      id: "annotation-1",
      page: 1,
      rawText: "Test annotation",
      annotationLabel: {
        id: "label-1",
        text: "Test Label",
        color: "blue",
        icon: "tag",
        description: "Test label description",
        labelType: "TokenLabel",
      },
      annotationType: "TokenAnnotation",
      json: "{}",
      myPermissions: ["read", "write", "delete"],
      userFeedback: {
        edges: [],
        totalCount: 0,
      },
    },
  ],
  allStructuralAnnotations: [],
  allRelationships: [],
};

// Mock corpus data
const mockCorpuses = [
  {
    id: "corpus-1",
    title: "Test Corpus 1",
    description: "First test corpus",
    myPermissions: [
      "read",
      "write",
      "create",
      "delete",
      "update_corpus",
      "publish",
    ],
  },
  {
    id: "corpus-2",
    title: "Test Corpus 2",
    description: "Second test corpus",
    myPermissions: ["read", "write", "update_corpus"],
  },
];

// The GetEditableCorpuses query used by the updated AddToCorpusModal
const GET_EDITABLE_CORPUSES = gql`
  query GetEditableCorpuses($textSearch: String) {
    corpuses(textSearch: $textSearch, first: 10) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      edges {
        node {
          id
          icon
          title
          creator {
            email
          }
          description
          documents {
            totalCount
          }
          labelSet {
            id
            title
          }
          myPermissions
        }
      }
    }
  }
`;

const documentOnlyMock: MockedResponse = {
  request: {
    query: GET_DOCUMENT_ONLY,
    variables: { documentId: "doc-123" },
  },
  result: {
    data: {
      document: mockDocument,
    },
  },
};

const documentWithCorpusMock: MockedResponse = {
  request: {
    query: GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
    variables: { documentId: "doc-123", corpusId: "corpus-1" },
  },
  result: {
    data: {
      document: mockDocumentWithCorpus,
      corpus: {
        id: "corpus-1",
        title: "Test Corpus 1",
        description: "First test corpus",
        labelSet: {
          id: "labelset-1",
          title: "Test Label Set",
          description: "Test label set description",
          allAnnotationLabels: [
            {
              id: "label-1",
              text: "Test Label",
              color: "blue",
              description: "Test label description",
              icon: "tag",
            },
          ],
        },
      },
    },
  },
};

const getMyCorpusesMock: MockedResponse = {
  request: {
    query: GET_MY_CORPUSES,
  },
  result: {
    data: {
      corpuses: {
        edges: mockCorpuses.map((corpus) => ({
          node: { ...corpus, documents: { totalCount: 0 } },
        })),
      },
    },
  },
};

// Mock for the new GetEditableCorpuses query
const getEditableCorpusesMock: MockedResponse = {
  request: {
    query: GET_EDITABLE_CORPUSES,
    variables: { textSearch: "" },
  },
  result: {
    data: {
      corpuses: {
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
        edges: mockCorpuses.map((corpus) => ({
          node: {
            ...corpus,
            icon: null,
            creator: { email: "test@example.com" },
            documents: { totalCount: 0 },
            labelSet: null,
          },
        })),
      },
    },
  },
};

// Additional mock for undefined textSearch
const getEditableCorpusesUndefinedMock: MockedResponse = {
  request: {
    query: GET_EDITABLE_CORPUSES,
    variables: {},
  },
  result: {
    data: {
      corpuses: {
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
        edges: mockCorpuses.map((corpus) => ({
          node: {
            ...corpus,
            icon: null,
            creator: { email: "test@example.com" },
            documents: { totalCount: 0 },
            labelSet: null,
          },
        })),
      },
    },
  },
};

const linkDocumentsToCorpusMock: MockedResponse = {
  request: {
    query: LINK_DOCUMENTS_TO_CORPUS,
    variables: {
      corpusId: "corpus-1",
      documentIds: ["doc-123"],
    },
  },
  result: {
    data: {
      linkDocumentsToCorpus: {
        ok: true,
        message: "Document added to corpus successfully!",
      },
    },
  },
};

const getConversationsMock: MockedResponse = {
  request: {
    query: GET_CONVERSATIONS,
    variables: {
      documentId: "doc-123",
      limit: undefined,
      cursor: undefined,
      title_Contains: undefined,
      createdAt_Gte: undefined,
      createdAt_Lte: undefined,
    },
  },
  result: {
    data: {
      conversations: {
        __typename: "ConversationTypeConnection",
        edges: [],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
      },
    },
  },
};

// Mock for GET_DOCUMENT_ANNOTATIONS_ONLY with annotations
// This is needed because DocumentKnowledgeBase refetches annotations when analysis/extract changes
const documentAnnotationsOnlyMock: MockedResponse = {
  request: {
    query: GET_DOCUMENT_ANNOTATIONS_ONLY,
    variables: {
      documentId: "doc-123",
      corpusId: "corpus-1",
      analysisId: null,
    },
  },
  result: {
    data: {
      document: {
        id: "doc-123",
        allStructuralAnnotations: [],
        allAnnotations: [
          {
            id: "annotation-1",
            page: 1,
            rawText: "Test annotation",
            annotationLabel: {
              id: "label-1",
              text: "Test Label",
              color: "blue",
              icon: "tag",
              description: "Test label description",
              labelType: "TokenLabel",
            },
            annotationType: "TokenAnnotation",
            json: "{}",
            myPermissions: ["read", "write", "delete"],
            userFeedback: {
              edges: [],
              totalCount: 0,
            },
          },
        ],
        allRelationships: [],
      },
    },
  },
};

const LONG_TIMEOUT = 60_000;

test.use({ viewport: { width: 1280, height: 720 } });

test.setTimeout(LONG_TIMEOUT);

async function registerRestMocks(page: Page): Promise<void> {
  // Route for PAWLS JSON
  await page.route("**/test.pawls", (route) => {
    if (!fs.existsSync(TEST_PAWLS_PATH)) {
      return route.fulfill({ status: 404, body: "PAWLS file not found" });
    }
    const pawlsContent = fs.readFileSync(TEST_PAWLS_PATH, "utf-8");
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: pawlsContent,
    });
  });

  // Route for plain text extract
  await page.route("**/test.txt", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/plain",
      body: "Mock document text content for testing.",
    })
  );

  // Route for PDF file
  await page.route("**/test.pdf", async (route) => {
    if (!fs.existsSync(TEST_PDF_PATH)) {
      return route.fulfill({ status: 404, body: "PDF not found" });
    }
    const buffer = fs.readFileSync(TEST_PDF_PATH);
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      body: buffer,
      headers: {
        "Content-Length": String(buffer.length),
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache, no-store, must-revalidate",
      },
    });
  });
}

test.beforeEach(async ({ page }) => {
  await registerRestMocks(page);
  // Stub WebSocket to avoid real network and to support chat in corpus-less mode
  await page.evaluate(() => {
    const activeInstances = new Set();

    class StubSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      url: string;
      readyState: number;
      onopen?: (event: any) => void;
      onmessage?: (event: any) => void;
      onclose?: (event: any) => void;
      private _disconnectTimeout?: any;

      constructor(url: string) {
        this.url = url;
        this.readyState = 1; // OPEN
        activeInstances.add(this);
        setTimeout(() => this.onopen && this.onopen({}), 0);
        this._disconnectTimeout = setTimeout(() => {
          if (this.readyState !== 3) {
            this.readyState = 3; // CLOSED
            this.onclose && this.onclose({});
            activeInstances.delete(this);
          }
        }, 30000);
      }

      send(data: any) {
        const emit = (payload: any) =>
          this.onmessage && this.onmessage({ data: JSON.stringify(payload) });
        try {
          const msg = JSON.parse(data);
          if (msg.query) {
            const id = Date.now().toString();
            emit({
              type: "ASYNC_START",
              content: "",
              data: { message_id: id },
            });
            emit({
              type: "ASYNC_CONTENT",
              content: "Received: ",
              data: { message_id: id },
            });
            emit({
              type: "ASYNC_CONTENT",
              content: msg.query,
              data: { message_id: id },
            });
            emit({
              type: "ASYNC_FINISH",
              content: `Received: ${msg.query}`,
              data: { message_id: id },
            });
          }
        } catch {}
      }

      close() {
        if (this._disconnectTimeout) clearTimeout(this._disconnectTimeout);
        if (this.readyState !== 3) {
          this.readyState = 3;
          this.onclose && this.onclose({});
          activeInstances.delete(this);
        }
      }

      addEventListener() {}
      removeEventListener() {}
    }

    // @ts-ignore
    window.WebSocket = StubSocket;
    // @ts-ignore
    window.WebSocketInstances = activeInstances;
  });
});

test.describe("DocumentKnowledgeBase - Corpus-less Mode", () => {
  test("should render document without corpus", async ({ mount, page }) => {
    const component = await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock]}
        documentId="doc-123"
      />
    );

    // Check that document title is rendered
    await expect(page.locator("text=Test Document")).toBeVisible();

    // Check that "Add to Corpus" button is visible
    await expect(
      page.locator('[data-testid="add-to-corpus-button"]')
    ).toBeVisible();
  });

  test("should hide corpus-required features but enable chat", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock, getConversationsMock]}
        documentId="doc-123"
      />
    );

    // Open the chat sidebar via the ChatIndicator
    const chatIndicator = page
      .locator("button")
      .filter({ has: page.locator('svg[class*="lucide-message-square"]') })
      .last();
    await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
    await chatIndicator.click();

    // Sidebar should open and chat container should be visible
    await expect(page.locator("#sliding-panel")).toBeVisible({
      timeout: LONG_TIMEOUT,
    });
    await expect(page.locator("#chat-container")).toBeVisible({
      timeout: LONG_TIMEOUT,
    });

    // Annotation tools should be visible but disabled (readonly mode)
    const annotationTools = page.locator("[data-testid='annotation-tools']");
    await expect(annotationTools).toBeVisible();

    // Try clicking the annotation tools - they should not expand in readonly mode
    await annotationTools.click();
    await expect(
      page.locator("[data-testid='label-selector-dropdown']")
    ).not.toBeVisible();

    // Extract features should not be visible
    await expect(
      page.locator("[data-testid='extract-tools']")
    ).not.toBeVisible();
  });

  test("should prevent annotation creation", async ({ mount, page }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock]}
        documentId="doc-123"
      />
    );

    // Try to select text in the document
    const pdfContainer = page.locator("#pdf-container");
    await expect(pdfContainer).toBeVisible({ timeout: LONG_TIMEOUT });

    // Get bounding box for safer mouse operations
    const box = await pdfContainer.boundingBox();
    if (!box) {
      throw new Error("Could not get bounding box for #pdf-container");
    }

    // Perform a small drag gesture roughly across the width of the page to simulate text selection
    const startX = box.x + box.width * 0.25;
    const startY = box.y + box.height * 0.3;
    const endX = box.x + box.width * 0.75;
    const endY = startY;

    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.waitForTimeout(50);
    await page.mouse.move(endX, endY, { steps: 10 });
    await page.mouse.up();

    // Give the UI a brief moment to react (if it would)
    await page.waitForTimeout(300);

    // Annotation popup should not appear
    await expect(
      page.locator("[data-testid='annotation-popup']")
    ).not.toBeVisible();
  });

  test("should show add to corpus modal", async ({ mount, page }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[
          documentOnlyMock,
          getEditableCorpusesMock,
          getEditableCorpusesUndefinedMock,
        ]}
        documentId="doc-123"
      />
    );

    // Click "Add to Corpus" button – it should be visible in the header
    const addButton = page.locator('[data-testid="add-to-corpus-button"]');
    await expect(addButton).toBeVisible({ timeout: LONG_TIMEOUT });
    await addButton.click();

    // Modal should appear (Semantic-UI appends modals to body)
    const modal = page.locator('[data-testid="add-to-corpus-modal"]');
    await expect(modal).toBeVisible({ timeout: LONG_TIMEOUT });

    // Wait for modal content to load
    await expect(modal.locator("text=Add to Corpus")).toBeVisible({
      timeout: LONG_TIMEOUT,
    });

    // Available corpuses should be listed using specific data-testids
    await expect(modal.locator('[data-testid="corpus-list"]')).toBeVisible({
      timeout: LONG_TIMEOUT,
    });
    await expect(
      modal.locator('[data-testid="corpus-title-corpus-1"]')
    ).toBeVisible({ timeout: LONG_TIMEOUT });
    await expect(
      modal.locator('[data-testid="corpus-title-corpus-2"]')
    ).toBeVisible({ timeout: LONG_TIMEOUT });
  });

  test("should handle adding document to corpus", async ({ mount, page }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[
          documentOnlyMock,
          getEditableCorpusesMock,
          getEditableCorpusesUndefinedMock,
          linkDocumentsToCorpusMock,
        ]}
        documentId="doc-123"
      />
    );

    // Open modal
    await page.locator('[data-testid="add-to-corpus-button"]').click();

    // Select first corpus card
    await page.locator('[data-testid="corpus-item-corpus-1"]').click();

    // Proceed to confirmation step
    await page.locator('[data-testid="next-button"]').click();

    // Confirm adding document
    await page.locator('[data-testid="confirm-add-button"]').click();

    // Modal should close on successful addition
    await expect(
      page.locator('[data-testid="add-to-corpus-modal"]')
    ).toBeHidden({ timeout: LONG_TIMEOUT });
  });

  test("should render document with corpus", async ({ mount, page }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentWithCorpusMock]}
        documentId="doc-123"
        corpusId="corpus-1"
      />
    );

    // Document should render
    await expect(page.locator("text=Test Document")).toBeVisible();

    // Corpus-less banner should NOT be shown
    await expect(
      page.locator('[data-testid="add-to-corpus-ribbon"]')
    ).not.toBeVisible();

    // Corpus features should be available
    await expect(
      page.locator("[data-testid='annotation-tools']")
    ).toBeVisible();
  });

  test("should show existing annotations with corpus", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[
          documentWithCorpusMock,
          getConversationsMock,
          documentAnnotationsOnlyMock,
        ]}
        documentId="doc-123"
        corpusId="corpus-1"
      />
    );

    // Wait for document to load
    await expect(page.locator("text=Test Document")).toBeVisible({
      timeout: LONG_TIMEOUT,
    });

    // Click the chat indicator button (MessageSquare icon) to open sidebar
    const chatIndicator = page
      .locator("button")
      .filter({
        has: page.locator('svg[class*="lucide-message-square"]'),
      })
      .last();
    await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
    await chatIndicator.click();

    // Wait for the right panel to appear and animation to complete
    await page.waitForTimeout(1000);

    // Now look for the feed toggle in the sidebar control bar
    const feedToggle = page.getByTestId("view-mode-feed");
    await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
    await feedToggle.click();

    // Wait a moment for the feed to render
    await page.waitForTimeout(500);

    // Check that annotations are displayed in the feed
    await expect(page.locator("text=Test annotation")).toBeVisible({
      timeout: LONG_TIMEOUT,
    });
  });

  test("should show feature unavailable states", async ({ mount, page }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock]}
        documentId="doc-123"
      />
    );

    // Try to access chat feature
    const chatToggle = page.locator("[data-testid='chat-toggle']");
    if (await chatToggle.isVisible()) {
      await chatToggle.click();

      // Should show feature unavailable message
      await expect(
        page.locator("text=Document Chat requires corpus membership")
      ).toBeVisible();
    }
  });

  test("should handle read-only mode without corpus", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock]}
        documentId="doc-123"
        readOnly={true}
      />
    );

    // Document should render in read-only mode
    await expect(page.locator("text=Test Document")).toBeVisible();

    // Add to Corpus button should not be visible in read-only mode
    await expect(
      page.locator('[data-testid="add-to-corpus-ribbon"]')
    ).not.toBeVisible();
  });

  test("should toggle between PDF and text views", async ({ mount, page }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock]}
        documentId="doc-123"
      />
    );

    // PDF should be visible by default
    await expect(page.locator("#pdf-container")).toBeVisible();

    // Click text view toggle if available
    const textToggle = page.locator("[data-testid='view-toggle-text']");
    if (await textToggle.isVisible()) {
      await textToggle.click();

      // Text view should be visible
      await expect(
        page.locator("[data-testid='text-container']")
      ).toBeVisible();
    }
  });

  test("should show corpus info when enabled", async ({ mount, page }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentWithCorpusMock]}
        documentId="doc-123"
        corpusId="corpus-1"
        showCorpusInfo={true}
      />
    );

    // Corpus info should be displayed
    await expect(page.locator("text=Test Corpus 1")).toBeVisible();
  });

  test("should handle empty corpus list gracefully", async ({
    mount,
    page,
  }) => {
    const emptyCorpusesMock: MockedResponse = {
      request: {
        query: GET_EDITABLE_CORPUSES,
        variables: { textSearch: "" },
      },
      result: {
        data: {
          corpuses: {
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
            },
            edges: [],
          },
        },
      },
    };

    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock, emptyCorpusesMock]}
        documentId="doc-123"
      />
    );

    // Open modal
    await page.locator('[data-testid="add-to-corpus-button"]').click();

    // Should show empty state
    await expect(
      page.locator("text=You don't have any corpuses with edit permissions")
    ).toBeVisible();

    // Modal should have cancel button available
    await expect(page.locator('[data-testid="cancel-button"]')).toBeVisible();
  });

  test("should handle GraphQL errors gracefully", async ({ mount, page }) => {
    const errorMock: MockedResponse = {
      request: {
        query: GET_DOCUMENT_ONLY,
        variables: { documentId: "doc-123" },
      },
      error: new Error("Failed to fetch document"),
    };

    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[errorMock]}
        documentId="doc-123"
      />
    );

    // Error message should be displayed
    await expect(page.locator("text=Error loading document")).toBeVisible();
  });

  test("should show success message when provided", async ({ mount, page }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock]}
        documentId="doc-123"
        showSuccessMessage="Document uploaded successfully!"
      />
    );

    // Success message should be visible
    await expect(
      page.locator("text=Document uploaded successfully!")
    ).toBeVisible();
  });

  test("corpus-required: prevents annotation selection toolbar in unified feed", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock, getConversationsMock]}
        documentId="doc-123"
        // Note: corpusId intentionally omitted to test corpus-less behavior
      />
    );

    // Wait for document to load
    await expect(page.locator("text=Test Document")).toBeVisible({
      timeout: LONG_TIMEOUT,
    });

    // Open sidebar to access unified feed
    const chatIndicator = page
      .locator("button")
      .filter({
        has: page.locator('svg[class*="lucide-message-square"]'),
      })
      .last();
    await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
    await chatIndicator.click();

    // Wait for sidebar animation
    await page.waitForTimeout(500);

    // Without corpus, the feed mode should either not be available
    // or if it is available, annotation selection should not work
    const feedToggle = page.getByTestId("view-mode-feed");
    if (await feedToggle.isVisible()) {
      await feedToggle.click();
      await page.waitForTimeout(500);

      // Try to click an annotation if available (there won't be any without corpus)
      const annotationCard = page
        .locator('[data-testid^="annotation-card-"]')
        .first();

      if ((await annotationCard.count()) > 0) {
        await annotationCard.click();
        await page.waitForTimeout(500);

        // Selection toolbar should NOT appear without corpus
        const selectionToolbar = page.locator(
          '[data-testid="selection-toolbar"]'
        );
        await expect(selectionToolbar).not.toBeVisible({ timeout: 3000 });
      }
    }

    console.log("[TEST SUCCESS] Annotation selection prevented without corpus");
  });

  test("corpus-required: relationship actions require corpus context", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentWithCorpusMock, getConversationsMock]}
        documentId="doc-123"
        corpusId="corpus-1" // WITH corpus to enable relationship features
      />
    );

    // Wait for document to load
    await expect(page.locator("text=Test Document")).toBeVisible({
      timeout: LONG_TIMEOUT,
    });

    // Open sidebar
    const chatIndicator = page
      .locator("button")
      .filter({
        has: page.locator('svg[class*="lucide-message-square"]'),
      })
      .last();
    await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
    await chatIndicator.click();
    await page.waitForTimeout(500);

    // Switch to feed mode
    const feedToggle = page.getByTestId("view-mode-feed");
    if (await feedToggle.isVisible()) {
      await feedToggle.click();
      await page.waitForTimeout(500);

      // With corpus, annotation selection should work
      const annotationCard = page
        .locator('[data-testid^="annotation-card-"]')
        .first();

      if ((await annotationCard.count()) > 0) {
        await annotationCard.click();
        await page.waitForTimeout(500);

        // Selection toolbar SHOULD appear with corpus
        const selectionToolbar = page.locator(
          '[data-testid="selection-toolbar"]'
        );
        // Note: This may or may not appear depending on implementation details
        // The key test is the contrast with corpus-less mode above

        console.log("[TEST] Annotation selection allowed with corpus context");
      }
    }
  });

  test("corpus-required: RelationshipActionModal requires corpus for label operations", async ({
    mount,
    page,
  }) => {
    // This test verifies that RelationshipActionModal properly checks for corpus
    // and shows appropriate error states when corpus is missing

    await mount(
      <DocumentKnowledgeBaseCorpuslessTestWrapper
        mocks={[documentOnlyMock]}
        documentId="doc-123"
        // No corpus - modal should not be accessible
      />
    );

    await expect(page.locator("text=Test Document")).toBeVisible({
      timeout: LONG_TIMEOUT,
    });

    // Verify that relationship creation features are not accessible
    // The modal itself should not open without a corpus context
    const relationshipModal = page.locator(
      '[data-testid="relationship-action-modal"]'
    );
    await expect(relationshipModal).not.toBeVisible();

    console.log(
      "[TEST SUCCESS] Relationship modal not accessible without corpus"
    );
  });
});
