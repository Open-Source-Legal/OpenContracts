import React from "react";
import { FloatingAnalysesPanel } from "../src/components/knowledge_base/document/FloatingAnalysesPanel";
import { AnalysisType } from "../src/types/graphql-api";

interface FloatingAnalysesPanelTestWrapperProps {
  visible?: boolean;
  analyses?: AnalysisType[];
  onClose?: () => void;
  panelOffset?: number;
  readOnly?: boolean;
}

// Mock analysis data helper (also defined in test file to avoid import issues)
const createMockAnalysis = (
  id: string,
  completed: boolean = true
): AnalysisType => ({
  id,
  analysisName: `Test Analysis ${id}`,
  analysisCompleted: completed,
  analysisStatus: completed ? "COMPLETE" : "PROCESSING",
  analysisStarted: new Date().toISOString(),
  analyzer: {
    id: `analyzer-${id}`,
    description: `Test Analyzer ${id}`,
    taskName: `test_analyzer_${id}`,
    disabled: false,
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    creator: {
      id: "user-1",
      email: "test@example.com",
      username: "testuser",
      __typename: "UserType",
    },
    hostGremlin: {
      id: "gremlin-1",
      __typename: "GremlinEngineType_Write",
    } as any,
    __typename: "AnalyzerType",
  },
  annotations: {
    totalCount: Math.floor(Math.random() * 50) + 1,
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    __typename: "AnnotationTypeConnection",
  },
  __typename: "AnalysisType",
});

export const FloatingAnalysesPanelTestWrapper: React.FC<
  FloatingAnalysesPanelTestWrapperProps
> = ({
  visible = true,
  analyses = [
    createMockAnalysis("1", true),
    createMockAnalysis("2", true),
    createMockAnalysis("3", false),
  ],
  onClose = () => {},
  panelOffset = 0,
  readOnly = false,
}) => {
  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        position: "relative",
        background: "#f5f5f5",
      }}
    >
      <FloatingAnalysesPanel
        visible={visible}
        analyses={analyses}
        onClose={onClose}
        panelOffset={panelOffset}
        readOnly={readOnly}
      />
    </div>
  );
};
