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
    createdBy: {
      id: "user-1",
      username: "john_doe",
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
    createdBy: {
      id: "user-2",
      username: "jane_smith",
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

interface TrashFolderViewTestWrapperProps {
  corpusId?: string;
  mockType?: "success" | "empty" | "error";
  restoreMockType?: "success" | "failure" | "error" | "partial";
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

    // Add query mock
    if (mockType === "error") {
      mocks.push({
        request: {
          query: GET_DELETED_DOCUMENTS_IN_CORPUS,
          variables: { corpusId },
        },
        error: new Error("Failed to load trash"),
      });
    } else if (mockType === "empty") {
      mocks.push({
        request: {
          query: GET_DELETED_DOCUMENTS_IN_CORPUS,
          variables: { corpusId },
        },
        result: { data: { deletedDocumentsInCorpus: [] } },
      });
    } else {
      mocks.push({
        request: {
          query: GET_DELETED_DOCUMENTS_IN_CORPUS,
          variables: { corpusId },
        },
        result: { data: { deletedDocumentsInCorpus: defaultDeletedDocuments } },
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
