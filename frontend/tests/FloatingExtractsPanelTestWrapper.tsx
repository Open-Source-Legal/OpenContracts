import React from "react";
import { Provider as JotaiProvider } from "jotai";
import { FloatingExtractsPanel } from "../src/components/knowledge_base/document/FloatingExtractsPanel";
import { ExtractType, ColumnType } from "../src/types/graphql-api";

interface FloatingExtractsPanelTestWrapperProps {
  visible?: boolean;
  extracts?: ExtractType[];
  onClose?: () => void;
  panelOffset?: number;
  initiallyExpanded?: boolean;
  readOnly?: boolean;
}

// Mock extract data
const createMockExtract = (id: string): ExtractType => ({
  id,
  name: `Test Extract ${id}`,
  created: new Date().toISOString(),
  modified: new Date().toISOString(),
  started: new Date().toISOString(),
  finished: new Date().toISOString(),
  isPublic: false,
  error: null,
  creator: {
    id: "user-1",
    email: "test@example.com",
    username: "testuser",
    __typename: "UserType",
  },
  corpus: {
    id: "corpus-1",
    title: "Test Corpus",
    __typename: "CorpusType",
  },
  __typename: "ExtractType",
});

export const FloatingExtractsPanelTestWrapper: React.FC<
  FloatingExtractsPanelTestWrapperProps
> = ({
  visible = true,
  extracts = [
    createMockExtract("1"),
    createMockExtract("2"),
    createMockExtract("3"),
  ],
  onClose = () => {},
  panelOffset = 0,
  initiallyExpanded = false,
  readOnly = false,
}) => {
  return (
    <JotaiProvider>
      <div
        style={{
          width: "100vw",
          height: "100vh",
          position: "relative",
          background: "#f5f5f5",
        }}
      >
        <FloatingExtractsPanel
          visible={visible}
          extracts={extracts}
          onClose={onClose}
          panelOffset={panelOffset}
          initiallyExpanded={initiallyExpanded}
          readOnly={readOnly}
        />
      </div>
    </JotaiProvider>
  );
};
