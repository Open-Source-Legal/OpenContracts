import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { FloatingSummaryPreview } from "../src/components/knowledge_base/document/floating_summary_preview/FloatingSummaryPreview";
import { relayStylePagination } from "@apollo/client/utilities";

// Minimal cache configuration
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          documentSummary: {
            keyArgs: ["documentId"],
          },
          documentSummaryRevisions: relayStylePagination(["documentId"]),
        },
      },
      DocumentSummaryType: { keyFields: ["id"] },
      DocumentSummaryRevision: { keyFields: ["id"] },
    },
  });

interface Props {
  mocks: ReadonlyArray<MockedResponse>;
  documentId: string;
  corpusId: string;
  documentTitle?: string;
  isVisible?: boolean;
  onSwitchToKnowledge?: (content?: string) => void;
  onBackToDocument?: () => void;
  isInKnowledgeLayer?: boolean;
  readOnly?: boolean;
}

export const FloatingSummaryPreviewTestWrapper: React.FC<Props> = ({
  mocks,
  documentId,
  corpusId,
  documentTitle = "Test Document",
  isVisible = true,
  onSwitchToKnowledge,
  onBackToDocument,
  isInKnowledgeLayer = false,
  readOnly = false,
}) => {
  return (
    <Provider>
      <MockedProvider mocks={mocks} cache={createTestCache()} addTypename>
        <FloatingSummaryPreview
          documentId={documentId}
          corpusId={corpusId}
          documentTitle={documentTitle}
          isVisible={isVisible}
          onSwitchToKnowledge={onSwitchToKnowledge}
          onBackToDocument={onBackToDocument}
          isInKnowledgeLayer={isInKnowledgeLayer}
          readOnly={readOnly}
        />
      </MockedProvider>
    </Provider>
  );
};
