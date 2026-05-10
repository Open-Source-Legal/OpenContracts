import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import {
  GET_DELETED_DOCUMENTS_IN_CORPUS,
  DeletedDocumentPathType,
} from "../src/graphql/queries/folders";
import { RESTORE_DELETED_DOCUMENT } from "../src/graphql/mutations";
import { TrashFolderView } from "../src/components/corpuses/folders/TrashFolderView";

// Mock data for deleted documents
const defaultDeletedDocuments: DeletedDocumentPathType[] = [
  {
    id: "path-1",
    path: "/documents/deleted-doc-1.pdf",
    versionNumber: 2,
    modified: "2025-01-15T10:00:00Z",
    creator: {
      id: "user-1",
      slug: "john-doe",
    },
    document: {
      id: "doc-1",
      title: "Deleted Document 1",
      description: "A test document",
      icon: "",
      fileType: "pdf",
      pageCount: 10,
      pdfFile: "/files/doc1.pdf",
    },
    folder: {
      id: "folder-1",
      name: "Original Folder",
    },
  },
  {
    id: "path-2",
    path: "/documents/deleted-doc-2.pdf",
    versionNumber: 1,
    modified: "2025-01-14T08:30:00Z",
    creator: {
      id: "user-2",
      slug: "jane-smith",
    },
    document: {
      id: "doc-2",
      title: "Deleted Document 2",
      description: "Another test document",
      icon: "",
      fileType: "docx",
      pageCount: 5,
      pdfFile: "/files/doc2.pdf",
    },
    folder: null, // Was at root
  },
];

// Mock data with null creator
const nullCreatorDocuments: DeletedDocumentPathType[] = [
  {
    id: "path-null-creator",
    path: "/documents/null-creator-doc.pdf",
    versionNumber: 1,
    modified: "2025-01-15T10:00:00Z",
    creator: null, // Null creator
    document: {
      id: "doc-null-creator",
      title: "Document with Null Creator",
      description: "Test document with null creator",
      icon: "",
      fileType: "pdf",
      pageCount: 5,
      pdfFile: "/files/doc-null-creator.pdf",
    },
    folder: null,
  },
];

// Mock data with null document
const nullDocumentData: DeletedDocumentPathType[] = [
  {
    id: "path-null-doc",
    path: "/documents/null-doc.pdf",
    versionNumber: 1,
    modified: "2025-01-15T10:00:00Z",
    creator: {
      id: "user-1",
      slug: "john-doe",
    },
    document: null, // Null document
    folder: null,
  },
];

// Mock data with invalid date
const invalidDateDocuments: DeletedDocumentPathType[] = [
  {
    id: "path-invalid-date",
    path: "/documents/invalid-date-doc.pdf",
    versionNumber: 1,
    modified: "invalid-date-string", // Invalid date
    creator: {
      id: "user-1",
      slug: "john-doe",
    },
    document: {
      id: "doc-invalid-date",
      title: "Document with Invalid Date",
      description: "Test document with invalid date",
      icon: "",
      fileType: "pdf",
      pageCount: 5,
      pdfFile: "/files/doc-invalid-date.pdf",
    },
    folder: null,
  },
];

// Mock data with mixed scenarios (valid doc + null doc)
const mixedNullDocuments: DeletedDocumentPathType[] = [
  {
    id: "path-valid",
    path: "/documents/valid-doc.pdf",
    versionNumber: 1,
    modified: "2025-01-15T10:00:00Z",
    creator: {
      id: "user-1",
      slug: "john-doe",
    },
    document: {
      id: "doc-valid",
      title: "Valid Document",
      description: "A valid document",
      icon: "",
      fileType: "pdf",
      pageCount: 10,
      pdfFile: "/files/valid-doc.pdf",
    },
    folder: null,
  },
  {
    id: "path-null-doc",
    path: "/documents/null-doc.pdf",
    versionNumber: 1,
    modified: "2025-01-15T10:00:00Z",
    creator: {
      id: "user-2",
      slug: "jane-smith",
    },
    document: null, // Null document - should be filtered in bulk restore
    folder: null,
  },
];

interface TrashFolderViewTestWrapperProps {
  corpusId?: string;
  mockType?:
    | "success"
    | "empty"
    | "error"
    | "nullCreator"
    | "nullDocument"
    | "invalidDate"
    | "mixedNull";
  restoreMockType?: "success" | "failure" | "error" | "partial" | "mixedNull";
  onBack?: () => void;
}

export const TrashFolderViewTestWrapper: React.FC<
  TrashFolderViewTestWrapperProps
> = ({
  corpusId = "corpus-123",
  mockType = "success",
  restoreMockType,
  onBack,
}) => {
  const createMocks = (): MockedResponse<any>[] => {
    const mocks: MockedResponse<any>[] = [];

    // Add query mock based on mockType
    let documentsToUse: DeletedDocumentPathType[] = defaultDeletedDocuments;

    if (mockType === "error") {
      mocks.push({
        request: {
          query: GET_DELETED_DOCUMENTS_IN_CORPUS,
          variables: { corpusId },
        },
        error: new Error("Failed to load trash"),
      });
    } else {
      // Select the appropriate mock data based on mockType
      if (mockType === "empty") {
        documentsToUse = [];
      } else if (mockType === "nullCreator") {
        documentsToUse = nullCreatorDocuments;
      } else if (mockType === "nullDocument") {
        documentsToUse = nullDocumentData;
      } else if (mockType === "invalidDate") {
        documentsToUse = invalidDateDocuments;
      } else if (mockType === "mixedNull") {
        documentsToUse = mixedNullDocuments;
      }

      mocks.push({
        request: {
          query: GET_DELETED_DOCUMENTS_IN_CORPUS,
          variables: { corpusId },
        },
        result: { data: { deletedDocumentsInCorpus: documentsToUse } },
      });
    }

    // Add restore mutation mocks if specified
    if (restoreMockType === "success") {
      mocks.push({
        request: {
          query: RESTORE_DELETED_DOCUMENT,
          variables: { documentId: "doc-1", corpusId },
        },
        result: {
          data: {
            restoreDeletedDocument: {
              ok: true,
              message: "Document restored successfully",
              document: {
                id: "doc-1",
                title: "Deleted Document 1",
              },
            },
          },
        },
      });
      // Add refetch mock after restore
      mocks.push({
        request: {
          query: GET_DELETED_DOCUMENTS_IN_CORPUS,
          variables: { corpusId },
        },
        result: {
          data: {
            deletedDocumentsInCorpus: [defaultDeletedDocuments[1]], // Only second doc remains
          },
        },
      });
    } else if (restoreMockType === "failure") {
      mocks.push({
        request: {
          query: RESTORE_DELETED_DOCUMENT,
          variables: { documentId: "doc-1", corpusId },
        },
        result: {
          data: {
            restoreDeletedDocument: {
              ok: false,
              message: "Permission denied",
              document: null,
            },
          },
        },
      });
    } else if (restoreMockType === "error") {
      mocks.push({
        request: {
          query: RESTORE_DELETED_DOCUMENT,
          variables: { documentId: "doc-1", corpusId },
        },
        error: new Error("Network error"),
      });
    } else if (restoreMockType === "partial") {
      // First doc succeeds
      mocks.push({
        request: {
          query: RESTORE_DELETED_DOCUMENT,
          variables: { documentId: "doc-1", corpusId },
        },
        result: {
          data: {
            restoreDeletedDocument: {
              ok: true,
              message: "Document restored successfully",
              document: {
                id: "doc-1",
                title: "Deleted Document 1",
              },
            },
          },
        },
      });
      // Second doc fails
      mocks.push({
        request: {
          query: RESTORE_DELETED_DOCUMENT,
          variables: { documentId: "doc-2", corpusId },
        },
        result: {
          data: {
            restoreDeletedDocument: {
              ok: false,
              message: "Permission denied",
              document: null,
            },
          },
        },
      });
      // Add refetch mock after partial restore
      mocks.push({
        request: {
          query: GET_DELETED_DOCUMENTS_IN_CORPUS,
          variables: { corpusId },
        },
        result: {
          data: {
            deletedDocumentsInCorpus: [defaultDeletedDocuments[1]], // Only second doc remains
          },
        },
      });
    } else if (restoreMockType === "mixedNull") {
      // For mixedNull scenario: restoring valid doc succeeds, null doc is filtered out
      mocks.push({
        request: {
          query: RESTORE_DELETED_DOCUMENT,
          variables: { documentId: "doc-valid", corpusId },
        },
        result: {
          data: {
            restoreDeletedDocument: {
              ok: true,
              message: "Document restored successfully",
              document: {
                id: "doc-valid",
                title: "Valid Document",
              },
            },
          },
        },
      });
      // Add refetch mock after restore
      mocks.push({
        request: {
          query: GET_DELETED_DOCUMENTS_IN_CORPUS,
          variables: { corpusId },
        },
        result: {
          data: {
            deletedDocumentsInCorpus: [mixedNullDocuments[1]], // Only null doc remains (wasn't restored)
          },
        },
      });
    }

    return mocks;
  };

  return (
    <MockedProvider mocks={createMocks()} addTypename={false}>
      <TrashFolderView corpusId={corpusId} onBack={onBack} />
    </MockedProvider>
  );
};

export default TrashFolderViewTestWrapper;
