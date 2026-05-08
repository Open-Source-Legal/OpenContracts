import React from "react";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import {
  HeaderBar,
  DocumentMetadata,
} from "../src/components/knowledge_base/document/document_kb/HeaderBar";

interface HeaderBarTestWrapperProps {
  metadata: DocumentMetadata;
  hasCorpus: boolean;
  readOnly?: boolean;
  documentId?: string;
  corpusId?: string;
  mocks?: MockedResponse[];
}

/**
 * Test wrapper for HeaderBar. Wraps the component in a MockedProvider +
 * MemoryRouter so the optional DocumentVersionSelector branch (rendered only
 * when `hasCorpus && corpusId`) has the providers it needs.
 */
export const HeaderBarTestWrapper: React.FC<HeaderBarTestWrapperProps> = ({
  metadata,
  hasCorpus,
  readOnly = false,
  documentId = "doc-1",
  corpusId,
  mocks = [],
}) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <MemoryRouter>
      <div style={{ padding: "1rem", background: "#fff" }}>
        <HeaderBar
          metadata={metadata}
          documentId={documentId}
          corpusId={corpusId}
          hasCorpus={hasCorpus}
          readOnly={readOnly}
          onAddToCorpus={() => {}}
          onClose={() => {}}
        />
      </div>
    </MemoryRouter>
  </MockedProvider>
);
