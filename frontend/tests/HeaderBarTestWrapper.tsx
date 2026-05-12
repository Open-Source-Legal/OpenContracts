import React, { useState } from "react";
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
  onClose?: () => void;
  onAddToCorpus?: () => void;
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
  onClose,
  onAddToCorpus,
}) => {
  // Expose click counters as DOM data attributes so tests can verify
  // handlers fired without Playwright window-bridge serialization issues.
  const [closeCount, setCloseCount] = useState(0);
  const [addCount, setAddCount] = useState(0);

  return (
    <MockedProvider mocks={mocks} addTypename={false}>
      <MemoryRouter>
        <div
          style={{ padding: "1rem", background: "#fff" }}
          data-testid="header-bar-test-wrapper"
          data-close-count={closeCount}
          data-add-count={addCount}
        >
          <HeaderBar
            metadata={metadata}
            documentId={documentId}
            corpusId={corpusId}
            hasCorpus={hasCorpus}
            readOnly={readOnly}
            onAddToCorpus={() => {
              setAddCount((n) => n + 1);
              onAddToCorpus?.();
            }}
            onClose={() => {
              setCloseCount((n) => n + 1);
              onClose?.();
            }}
          />
        </div>
      </MemoryRouter>
    </MockedProvider>
  );
};
