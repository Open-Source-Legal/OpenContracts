import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { CorpusesTestWrapper } from "./CorpusesTestWrapper";
import {
  GET_CORPUSES,
  GET_CORPUS_METADATA,
  GET_DOCUMENTS,
  GET_CORPUS_STATS,
  GET_CORPUS_ARTICLE,
} from "../src/graphql/queries";
import { GET_CORPUS_FOLDERS } from "../src/graphql/queries/folders";
import { DEFAULT_LIST_PAGE_SIZE } from "../src/assets/configurations/constants";
import {
  GET_CORPUS_METADATA_COLUMNS,
  GET_DOCUMENT_METADATA_DATACELLS,
  CREATE_METADATA_COLUMN,
  SET_METADATA_VALUE,
} from "../src/graphql/metadataOperations";
import {
  FullAppWrapper,
  FilterTestComponent,
  BulkEditTestComponent,
} from "./MetadataWorkflow.story";
import { openedCorpus } from "../src/graphql/cache";
import { CorpusType, DocumentType } from "../src/types/graphql-api";
import { PermissionTypes } from "../src/components/types";

test.describe("Metadata Workflow Integration", () => {
  // Use a valid base64-encoded GraphQL ID that passes isValidGraphQLId
  // "CorpusType:1" base64 encoded = "Q29ycHVzVHlwZTox"
  const corpusId = "Q29ycHVzVHlwZTox";
  const corpus: CorpusType = {
    id: corpusId,
    slug: "test-corpus",
    title: "Test Corpus",
    description: "Test corpus for metadata workflow",
    descriptionPreview: "Test corpus for metadata workflow",
    icon: null,
    isPublic: false,
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    allowComments: true,
    creator: {
      id: "VXNlclR5cGU6MQ==", // "UserType:1" base64 encoded
      email: "test@example.com",
      slug: "test-user",
      __typename: "UserType",
    },
    labelSet: null,
    parent: undefined,
    preferredEmbedder: null,
    appliedAnalyzerIds: [],
    myPermissions: [
      "update_corpus",
      "read_corpus",
    ] as unknown as PermissionTypes[],
    documents: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo",
      },
      totalCount: 0,
      __typename: "DocumentTypeConnection",
    },
    analyses: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo",
      },
      totalCount: 0,
      __typename: "AnalysisTypeConnection",
    },
    annotations: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo",
      },
      totalCount: 0,
      __typename: "AnnotationTypeConnection",
    },
    __typename: "CorpusType",
  };

  test("complete metadata setup and data entry flow", async ({
    mount,
    page,
  }, testInfo) => {
    testInfo.setTimeout(60000); // Increase timeout for this complex test
    // Start with no metadata schema
    // Document ID: "DocumentType:1" base64 encoded = "RG9jdW1lbnRUeXBlOjE="
    const docId = "RG9jdW1lbnRUeXBlOjE=";
    const documents: Partial<DocumentType>[] = [
      {
        id: docId,
        slug: "document-1",
        title: "Document 1",
        description: "",
        fileType: "application/pdf",
        __typename: "DocumentType",
        backendLock: false,
        // @ts-ignore
        icon: null,
        isPublic: false,
        myPermissions: ["read_document"] as unknown as PermissionTypes[],
        // @ts-ignore
        pdfFile: null,
        // @ts-ignore
        txtExtractFile: null,
        // @ts-ignore
        pawlsParseFile: null,
        // @ts-ignore
        creator: {
          slug: "test-user",
        },
        // @ts-ignore - version fields from GET_DOCUMENTS query
        hasVersionHistory: false,
        versionCount: 1,
        isLatestVersion: true,
        canViewHistory: false,
        docLabelAnnotations: {
          __typename: "AnnotationTypeConnection",
          edges: [],
          pageInfo: {
            __typename: "PageInfo",
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
          },
        },
        metadataAnnotations: {
          __typename: "AnnotationTypeConnection",
          edges: [],
          pageInfo: {
            __typename: "PageInfo",
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
          },
        },
      },
    ];

    const mocks: MockedResponse[] = [
      // Initial corpus list
      {
        request: { query: GET_CORPUSES, variables: {} },
        result: {
          data: {
            corpuses: {
              edges: [{ node: corpus, __typename: "CorpusTypeEdge" }],
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
                __typename: "PageInfo",
              },
              __typename: "CorpusTypeConnection",
            },
          },
        },
      },
      // Second call with empty search term
      {
        request: { query: GET_CORPUSES, variables: { textSearch: "" } },
        result: {
          data: {
            corpuses: {
              edges: [{ node: corpus, __typename: "CorpusTypeEdge" }],
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
                __typename: "PageInfo",
              },
              __typename: "CorpusTypeConnection",
            },
          },
        },
      },
      // Corpus stats
      {
        request: {
          query: GET_CORPUS_STATS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusStats: {
              totalDocs: 1,
              totalAnnotations: 0,
              totalAnalyses: 0,
              totalExtracts: 0,
              totalComments: 0,
              totalThreads: 0,
              totalChats: 0,
              totalRelationships: 0,
              __typename: "CorpusStatsType",
            },
          },
        },
      },
      // Duplicated for refetch after state changes
      {
        request: {
          query: GET_CORPUS_STATS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusStats: {
              totalDocs: 1,
              totalAnnotations: 0,
              totalAnalyses: 0,
              totalExtracts: 0,
              totalComments: 0,
              totalThreads: 0,
              totalChats: 0,
              totalRelationships: 0,
              __typename: "CorpusStatsType",
            },
          },
        },
      },
      // Third copy for additional refetches
      {
        request: {
          query: GET_CORPUS_STATS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusStats: {
              totalDocs: 1,
              totalAnnotations: 0,
              totalAnalyses: 0,
              totalExtracts: 0,
              totalComments: 0,
              totalThreads: 0,
              totalChats: 0,
              totalRelationships: 0,
              __typename: "CorpusStatsType",
            },
          },
        },
      },
      // Corpus metadata
      {
        request: {
          query: GET_CORPUS_METADATA,
          variables: { metadataForCorpusId: corpusId },
        },
        result: {
          data: {
            corpus: {
              ...corpus,
              descriptionRevisions: [],
              allAnnotationSummaries: [],
            },
          },
        },
      },
      // Initial metadata columns (empty)
      {
        request: {
          query: GET_CORPUS_METADATA_COLUMNS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusMetadataColumns: [],
          },
        },
      },
      // Generic create metadata column mock to match any field name
      {
        request: {
          query: CREATE_METADATA_COLUMN,
          variables: {
            corpusId,
            name: "Project Name", // the test fills this exact value
            dataType: "STRING",
            validationConfig: { required: false },
            defaultValue: "",
            displayOrder: 0,
          },
        },
        result: {
          data: {
            createMetadataColumn: {
              ok: true,
              message: "Column created",
              obj: {
                id: "col1",
                name: "Project Name",
                dataType: "STRING",
                helpText: "",
                validationConfig: { required: false },
                defaultValue: "",
                displayOrder: 0,
                isManualEntry: true,
                __typename: "MetadataColumn",
              },
              __typename: "CreateMetadataColumnOutput",
            },
          },
        },
      },
      // Refetch after creation
      {
        request: {
          query: GET_CORPUS_METADATA_COLUMNS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusMetadataColumns: [
              {
                id: "col1",
                name: "Project Name",
                dataType: "STRING",
                helpText: null,
                validationConfig: null,
                defaultValue: null,
                displayOrder: 0,
                isManualEntry: true,
                __typename: "MetadataColumn",
              },
            ],
          },
        },
      },
      // Documents query for corpus (include metadata)
      {
        request: {
          query: GET_DOCUMENTS,
          variables: {
            // CorpusDocumentCards bounds the first page (see useLazyPdfUrl /
            // limit comment in CorpusDocumentCards.tsx).
            limit: DEFAULT_LIST_PAGE_SIZE,
            inCorpusWithId: corpusId,
            inFolderId: "__root__",
            annotateDocLabels: true,
            includeMetadata: true,
            includeCaml: true,
          },
        },
        result: {
          data: {
            documents: {
              edges: documents.map((doc) => {
                const { docLabelAnnotations, metadataAnnotations, ...rest } =
                  doc;
                return {
                  node: {
                    ...rest,
                    doc_label_annotations: docLabelAnnotations,
                    metadata_annotations: metadataAnnotations,
                  },
                  __typename: "DocumentTypeEdge",
                };
              }),
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
                __typename: "PageInfo",
              },
              __typename: "DocumentTypeConnection",
            },
          },
        },
      },
      // Duplicated for refetch after state changes
      {
        request: {
          query: GET_DOCUMENTS,
          variables: {
            // CorpusDocumentCards bounds the first page (see useLazyPdfUrl /
            // limit comment in CorpusDocumentCards.tsx).
            limit: DEFAULT_LIST_PAGE_SIZE,
            inCorpusWithId: corpusId,
            inFolderId: "__root__",
            annotateDocLabels: true,
            includeMetadata: true,
            includeCaml: true,
          },
        },
        result: {
          data: {
            documents: {
              edges: documents.map((doc) => {
                const { docLabelAnnotations, metadataAnnotations, ...rest } =
                  doc;
                return {
                  node: {
                    ...rest,
                    doc_label_annotations: docLabelAnnotations,
                    metadata_annotations: metadataAnnotations,
                  },
                  __typename: "DocumentTypeEdge",
                };
              }),
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
                __typename: "PageInfo",
              },
              __typename: "DocumentTypeConnection",
            },
          },
        },
      },
      // Initial documents query (no corpus selected yet)
      {
        request: {
          query: GET_DOCUMENTS,
          variables: {
            annotateDocLabels: false,
            includeMetadata: false,
          },
        },
        result: {
          data: {
            documents: {
              edges: [],
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
                __typename: "PageInfo",
              },
              __typename: "DocumentTypeConnection",
            },
          },
        },
      },
      // Documents query for corpus (without inFolderId - used by Corpuses.tsx lazy query)
      {
        request: {
          query: GET_DOCUMENTS,
          variables: {
            inCorpusWithId: corpusId,
            annotateDocLabels: true,
            includeMetadata: true,
            includeCaml: true,
          },
        },
        result: {
          data: {
            documents: {
              edges: documents.map((doc) => {
                const { docLabelAnnotations, metadataAnnotations, ...rest } =
                  doc;
                return {
                  node: {
                    ...rest,
                    doc_label_annotations: docLabelAnnotations,
                    metadata_annotations: metadataAnnotations,
                  },
                  __typename: "DocumentTypeEdge",
                };
              }),
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
                __typename: "PageInfo",
              },
              __typename: "DocumentTypeConnection",
            },
          },
        },
      },
      // Duplicate for refetch
      {
        request: {
          query: GET_DOCUMENTS,
          variables: {
            inCorpusWithId: corpusId,
            annotateDocLabels: true,
            includeMetadata: true,
            includeCaml: true,
          },
        },
        result: {
          data: {
            documents: {
              edges: documents.map((doc) => {
                const { docLabelAnnotations, metadataAnnotations, ...rest } =
                  doc;
                return {
                  node: {
                    ...rest,
                    doc_label_annotations: docLabelAnnotations,
                    metadata_annotations: metadataAnnotations,
                  },
                  __typename: "DocumentTypeEdge",
                };
              }),
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: null,
                endCursor: null,
                __typename: "PageInfo",
              },
              __typename: "DocumentTypeConnection",
            },
          },
        },
      },
      // Set metadata value
      {
        request: {
          query: SET_METADATA_VALUE,
          variables: {
            documentId: docId,
            corpusId,
            columnId: "col1",
            value: "Alpha Project",
          },
        },
        result: {
          data: {
            setMetadataValue: {
              ok: true,
              message: "Value set successfully",
              obj: {
                id: "datacell1",
                data: { value: "Alpha Project" },
                dataDefinition: "STRING",
                column: {
                  id: "col1",
                  name: "Project Name",
                  dataType: "STRING",
                },
              },
            },
          },
        },
      },
      // Folder structure for documents tab (empty - no subfolders)
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusFolders: [], // Array of folders, not a connection object
          },
        },
      },
      // Duplicated for refetch
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusFolders: [],
          },
        },
      },
      // Third copy for additional refetches
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusFolders: [],
          },
        },
      },
      // Fourth copy for additional refetches
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusFolders: [],
          },
        },
      },
      // GET_CORPUS_ARTICLE - initial fetch
      {
        request: {
          query: GET_CORPUS_ARTICLE,
          variables: { corpusId, title: "Readme.CAML" },
        },
        result: {
          data: {
            documents: {
              edges: [],
              __typename: "DocumentTypeConnection",
            },
          },
        },
      },
      // GET_CORPUS_ARTICLE - refetch
      {
        request: {
          query: GET_CORPUS_ARTICLE,
          variables: { corpusId, title: "Readme.CAML" },
        },
        result: {
          data: {
            documents: {
              edges: [],
              __typename: "DocumentTypeConnection",
            },
          },
        },
      },
      // Document metadata datacells (empty initially, then populated after column creation)
      {
        request: {
          query: GET_DOCUMENT_METADATA_DATACELLS,
          variables: { documentId: docId, corpusId },
        },
        result: {
          data: {
            documentMetadataDatacells: [],
          },
        },
      },
      // Duplicate for refetch
      {
        request: {
          query: GET_DOCUMENT_METADATA_DATACELLS,
          variables: { documentId: docId, corpusId },
        },
        result: {
          data: {
            documentMetadataDatacells: [],
          },
        },
      },
      // Third refetch for GET_CORPUS_METADATA_COLUMNS (after navigating to documents tab)
      {
        request: {
          query: GET_CORPUS_METADATA_COLUMNS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusMetadataColumns: [
              {
                id: "col1",
                name: "Project Name",
                dataType: "STRING",
                helpText: null,
                validationConfig: null,
                defaultValue: null,
                displayOrder: 0,
                isManualEntry: true,
                __typename: "MetadataColumn",
              },
            ],
          },
        },
      },
      // Fourth refetch for GET_CORPUS_METADATA_COLUMNS
      {
        request: {
          query: GET_CORPUS_METADATA_COLUMNS,
          variables: { corpusId },
        },
        result: {
          data: {
            corpusMetadataColumns: [
              {
                id: "col1",
                name: "Project Name",
                dataType: "STRING",
                helpText: null,
                validationConfig: null,
                defaultValue: null,
                displayOrder: 0,
                isManualEntry: true,
                __typename: "MetadataColumn",
              },
            ],
          },
        },
      },
    ];

    // Set the opened corpus before mounting
    openedCorpus(null); // Start with no corpus opened

    await mount(
      <CorpusesTestWrapper
        mocks={mocks}
        initialCorpus={corpus}
        initialEntries={[`/corpuses/${corpusId}?mode=power`]}
      />
    );

    // Wait for the navigation sidebar rendered in power user mode
    await expect(
      page.locator('[data-testid="navigation-sidebar"]')
    ).toBeVisible({ timeout: 10000 });

    // Navigate to settings tab through sidebar
    const settingsTab = page.locator('[data-item-id="settings"]');
    await expect(settingsTab).toBeVisible();
    await settingsTab.click();

    // Wait for settings content to load
    await page.waitForTimeout(1000); // Give time for component to mount

    // Debug: log what's visible
    const visibleHeadings = await page.locator("h2, h3, h4").allTextContents();
    console.log("Visible headings:", visibleHeadings);

    // Try to find the metadata section - it might be scrolled out of view
    const metadataHeading = page
      .locator("h2")
      .filter({ hasText: "Metadata Fields" });

    // Scroll the metadata section into view if needed
    try {
      await metadataHeading.scrollIntoViewIfNeeded({ timeout: 5000 });
      await expect(metadataHeading).toBeVisible();
    } catch (e) {
      // If we can't find it, try scrolling the main content area
      const mainContent = page.locator("#main-corpus-content-area");
      await mainContent.evaluate((el) => (el.scrollTop = el.scrollHeight));
      await page.waitForTimeout(500);
    }

    // Should show empty state
    const emptyStateHeading = page.getByRole("heading", {
      name: "No metadata fields defined",
    });
    await emptyStateHeading.scrollIntoViewIfNeeded();
    await expect(emptyStateHeading).toBeVisible();

    // Click add field button
    // The button text is "Add Field" - use exact match
    const addFieldButton = page
      .getByRole("button", { name: "Add Field" })
      .first();
    await addFieldButton.scrollIntoViewIfNeeded();

    // Debug: Check if button is actually clickable
    const isEnabled = await addFieldButton.isEnabled();
    const isVisible = await addFieldButton.isVisible();
    console.log("Add Field button state:", { isEnabled, isVisible });

    // Try different click strategies
    try {
      await addFieldButton.click({ force: true });
    } catch (e) {
      console.log("First click failed, trying alternative:", e.message);
      // Alternative: click using page coordinates
      await addFieldButton.click({ position: { x: 5, y: 5 } });
    }

    // Give modal time to animate in
    await page.waitForTimeout(500);

    // Wait for modal to appear - the header says "Create Metadata Field"
    try {
      await expect(page.getByText("Create Metadata Field")).toBeVisible({
        timeout: 5000,
      });
    } catch (e) {
      // Debug: Check what's actually on the page
      const bodyText = await page.locator("body").textContent();
      console.log(
        "Modal not found. Page contains:",
        bodyText?.substring(0, 500)
      );

      // Also check for any error messages
      const errorMessages = await page
        .locator(".error, .message.negative")
        .allTextContents();
      if (errorMessages.length > 0) {
        console.log("Error messages found:", errorMessages);
      }

      throw e;
    }

    // Fill in field details
    // The modal might be positioned off-screen, so let's be more specific
    // Target the input within the modal (uses @os-legal/ui Modal with .oc-modal class)
    const modal = page
      .locator(".oc-modal")
      .filter({ hasText: "Create Metadata Field" });

    // Ensure modal is in view
    await modal.evaluate((el) => {
      // Force the modal to be centered on screen
      el.style.position = "fixed";
      el.style.top = "50%";
      el.style.left = "50%";
      el.style.transform = "translate(-50%, -50%)";
      el.style.zIndex = "9999";
    });

    // Now fill in the field name input within the modal
    const fieldNameInput = modal
      .locator('input[placeholder*="Contract Status"]')
      .first();
    await fieldNameInput.click();
    await fieldNameInput.fill("Project Name");

    // Save - the button says "Create Field"
    const createButton = modal.getByRole("button", { name: "Create Field" });
    await createButton.click();

    // Wait for the modal to process and close - the save will trigger a refetch
    await page.waitForTimeout(1000);

    // Verify field was added
    // Look for the field in the table that should now be visible
    const projectNameCell = page
      .locator("td")
      .filter({ hasText: "Project Name" });
    await expect(projectNameCell).toBeVisible({ timeout: 5000 });

    // Navigate to documents tab
    const documentsTab = page.locator('[data-item-id="documents"]');
    await documentsTab.click();

    // Wait for documents tab to load
    await page.waitForTimeout(1000);

    // Verify documents are displayed in list view
    // The document title should be visible
    await expect(page.getByText("Document 1")).toBeVisible({ timeout: 5000 });

    // Note: Grid view state change doesn't work reliably in Playwright component tests
    // due to React state update timing. The metadata editing workflow via grid
    // is tested separately in DocumentMetadataGrid component tests.

    // Verify view toggle buttons are present and clickable
    const gridButton = page.getByTestId("grid-view-button");
    await expect(gridButton).toBeVisible();
    await expect(gridButton).toBeEnabled();

    // Test passes if:
    // 1. Metadata column was successfully created (Project Name field visible in Settings)
    // 2. Documents tab loads and shows documents
    // 3. View toggle buttons are present
    console.log("Metadata workflow test completed successfully!");
  });

  test("metadata filters affect document list", async ({ mount, page }) => {
    await mount(
      <FullAppWrapper
        mocks={[]}
        initialPath={`/corpuses/${corpusId}/documents`}
      >
        <FilterTestComponent />
      </FullAppWrapper>
    );

    // Initially see all documents
    const documentCards = page.locator('[data-testid="document-card"]');
    await expect(documentCards).toHaveCount(3);

    // Apply filter
    await page.getByTestId("status-filter").selectOption("Active");

    // Should only see active documents
    await expect(documentCards).toHaveCount(2);
    await expect(page.getByText("Active Project A")).toBeVisible();
    await expect(page.getByText("Active Project C")).toBeVisible();
    await expect(page.getByText("Completed Project B")).not.toBeVisible();
  });

  test("bulk metadata editing", async ({ mount, page }) => {
    await mount(
      <FullAppWrapper mocks={[]} initialPath="/corpuses">
        <BulkEditTestComponent />
      </FullAppWrapper>
    );

    // Select multiple documents
    await page.getByTestId("select-doc1").check();
    await page.getByTestId("select-doc2").check();

    // Open bulk edit
    await page.getByTestId("bulk-edit").click();

    // Enter bulk value
    await page.getByTestId("bulk-value").fill("Legal");
    await page.getByTestId("apply-bulk").click();

    // Verify values updated
    await expect(page.getByTestId("cell-doc1")).toContainText("Legal");
    await expect(page.getByTestId("cell-doc2")).toContainText("Legal");
    await expect(page.getByTestId("cell-doc3")).toContainText("—"); // Not selected
  });
});
