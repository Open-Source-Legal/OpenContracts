import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import {
  VersionHistoryPanel,
  GET_DOCUMENT_VERSION_HISTORY,
  RESTORE_DOCUMENT_TO_VERSION,
} from "../src/components/documents/VersionHistoryPanel";

// Mock data for version history
const defaultVersionHistoryData = {
  document: {
    id: "doc-123",
    title: "Test Document",
    versionHistory: {
      versions: [
        {
          id: "v3",
          versionNumber: 3,
          hash: "hash3",
          createdAt: "2025-01-15T10:00:00Z",
          createdBy: { username: "user1" },
          sizeBytes: 1048576,
          changeType: "CONTENT_UPDATE",
        },
        {
          id: "v2",
          versionNumber: 2,
          hash: "hash2",
          createdAt: "2025-01-14T10:00:00Z",
          createdBy: { username: "user2" },
          sizeBytes: 512000,
          changeType: "MINOR_EDIT",
        },
        {
          id: "v1",
          versionNumber: 1,
          hash: "hash1",
          createdAt: "2025-01-13T10:00:00Z",
          createdBy: { username: "user1" },
          sizeBytes: 256000,
          changeType: "INITIAL",
        },
      ],
      currentVersion: {
        id: "v3",
        versionNumber: 3,
      },
    },
  },
};

const emptyVersionHistoryData = {
  document: {
    id: "doc-123",
    title: "Test Document",
    versionHistory: {
      versions: [],
      currentVersion: null,
    },
  },
};

interface VersionHistoryPanelTestWrapperProps {
  documentId?: string;
  corpusId?: string;
  documentTitle?: string;
  isOpen?: boolean;
  mockType?: "success" | "empty" | "error";
  mutationMockType?: "success" | "error" | "failure";
  onClose?: () => void;
  onRestore?: (versionId: string) => void;
  onDownload?: (versionId: string) => void;
}

export const VersionHistoryPanelTestWrapper: React.FC<
  VersionHistoryPanelTestWrapperProps
> = ({
  documentId = "doc-123",
  corpusId = "corpus-123",
  documentTitle = "Test Document",
  isOpen = true,
  mockType = "success",
  mutationMockType,
  onClose = () => {},
  onRestore,
  onDownload,
}) => {
  const createMocks = (): MockedResponse<any>[] => {
    const mocks: MockedResponse<any>[] = [];

    // Add query mock
    if (mockType === "error") {
      mocks.push({
        request: {
          query: GET_DOCUMENT_VERSION_HISTORY,
          variables: { documentId },
        },
        error: new Error("Failed to fetch version history"),
      });
    } else if (mockType === "empty") {
      mocks.push({
        request: {
          query: GET_DOCUMENT_VERSION_HISTORY,
          variables: { documentId },
        },
        result: { data: emptyVersionHistoryData },
      });
    } else {
      // Add initial fetch
      mocks.push({
        request: {
          query: GET_DOCUMENT_VERSION_HISTORY,
          variables: { documentId },
        },
        result: { data: defaultVersionHistoryData },
      });
    }

    // Add mutation mocks if specified
    if (mutationMockType === "success") {
      // Mock for restoring v2
      mocks.push({
        request: {
          query: RESTORE_DOCUMENT_TO_VERSION,
          variables: { documentId: "v2", corpusId },
        },
        result: {
          data: {
            restoreDocumentToVersion: {
              ok: true,
              message: "Successfully restored",
              document: {
                id: "v4",
                title: "Test Document",
                isCurrent: true,
              },
              newVersionNumber: 4,
            },
          },
        },
      });
      // Add refetch mock after successful mutation
      mocks.push({
        request: {
          query: GET_DOCUMENT_VERSION_HISTORY,
          variables: { documentId },
        },
        result: { data: defaultVersionHistoryData },
      });
    } else if (mutationMockType === "failure") {
      // Business logic failure (ok: false)
      mocks.push({
        request: {
          query: RESTORE_DOCUMENT_TO_VERSION,
          variables: { documentId: "v2", corpusId },
        },
        result: {
          data: {
            restoreDocumentToVersion: {
              ok: false,
              message: "Permission denied",
              document: null,
              newVersionNumber: null,
            },
          },
        },
      });
    } else if (mutationMockType === "error") {
      // Network/GraphQL error
      mocks.push({
        request: {
          query: RESTORE_DOCUMENT_TO_VERSION,
          variables: { documentId: "v2", corpusId },
        },
        error: new Error("Network error occurred"),
      });
    }

    return mocks;
  };

  return (
    <MockedProvider mocks={createMocks()} addTypename={false}>
      <VersionHistoryPanel
        documentId={documentId}
        corpusId={corpusId}
        documentTitle={documentTitle}
        isOpen={isOpen}
        onClose={onClose}
        onRestore={onRestore}
        onDownload={onDownload}
      />
    </MockedProvider>
  );
};

export default VersionHistoryPanelTestWrapper;
