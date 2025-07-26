import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import UnifiedKnowledgeLayer from "../src/components/knowledge_base/document/layers/UnifiedKnowledgeLayer";
import { GET_DOCUMENT_SUMMARY_VERSIONS } from "../src/components/knowledge_base/document/floating_summary_preview/graphql/documentSummaryQueries";

interface UnifiedKnowledgeLayerTestWrapperProps {
  documentId?: string;
  corpusId?: string;
  metadata?: any;
  parentLoading?: boolean;
  mocks?: MockedResponse[];
}

// Default metadata
const defaultMetadata = {
  title: "Test Document",
  description: "Test document description",
  author: "Test Author",
  created: new Date().toISOString(),
};

// Default mock for summary revisions query
const createSummaryRevisionsMock = (documentId: string, corpusId: string) => ({
  request: {
    query: GET_DOCUMENT_SUMMARY_VERSIONS,
    variables: { documentId, corpusId },
  },
  result: {
    data: {
      document: {
        id: documentId,
        summaryContent: "This is the current summary of the document.",
        currentSummaryVersion: 2,
        summaryRevisions: [
          {
            id: "rev-1",
            version: 1,
            snapshot: "This is the first version of the summary.",
            created: new Date(Date.now() - 86400000).toISOString(), // 1 day ago
            diff: "Initial version",
            author: {
              id: "user-1",
              username: "user1",
              email: "user1@example.com",
            },
          },
          {
            id: "rev-2",
            version: 2,
            snapshot: "This is the current summary of the document.",
            created: new Date().toISOString(),
            diff: "Updated summary content",
            author: {
              id: "user-2",
              username: "user2",
              email: "user2@example.com",
            },
          },
        ],
      },
    },
  },
});

const createCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          document: {
            keyArgs: ["id"],
          },
        },
      },
    },
  });

export const UnifiedKnowledgeLayerTestWrapper: React.FC<
  UnifiedKnowledgeLayerTestWrapperProps
> = ({
  documentId = "test-doc-1",
  corpusId = "test-corpus-1",
  metadata = defaultMetadata,
  parentLoading = false,
  mocks = [],
}) => {
  // Add default mocks if not provided
  const allMocks = [createSummaryRevisionsMock(documentId, corpusId), ...mocks];

  return (
    <MockedProvider mocks={allMocks} cache={createCache()} addTypename={true}>
      <div
        style={{
          width: "100vw",
          height: "100vh",
          position: "relative",
          background: "#f5f5f5",
        }}
      >
        <UnifiedKnowledgeLayer
          documentId={documentId}
          corpusId={corpusId}
          metadata={metadata}
          parentLoading={parentLoading}
        />
      </div>
    </MockedProvider>
  );
};
