import React from "react";
import { DocumentViewer } from "../src/components/knowledge_base/document/document_kb/DocumentViewer";
import { ViewState } from "../src/components/types";
import { ServerTokenAnnotation } from "../src/components/annotator/types/annotations";

interface DocumentViewerTestWrapperProps {
  fileType: string;
  viewState: ViewState;
  canEdit?: boolean;
  containerWidth?: number | null;
}

const noopCreateAnnotation = async (
  _annotation: ServerTokenAnnotation
): Promise<void> => {
  /* noop */
};

/**
 * Test wrapper for DocumentViewer. Smoke-test focused: renders the
 * unsupported-filetype + loading branches that don't require PDF.js,
 * Tiptap, or DOCX wasm fixtures.
 */
export const DocumentViewerTestWrapper: React.FC<
  DocumentViewerTestWrapperProps
> = ({ fileType, viewState, canEdit = false, containerWidth = 800 }) => (
  <div
    style={{
      width: "100%",
      height: "400px",
      background: "#fafafa",
      position: "relative",
    }}
    data-testid="document-viewer-host"
  >
    <DocumentViewer
      fileType={fileType}
      viewState={viewState}
      canEdit={canEdit}
      containerWidth={containerWidth}
      containerRefCallback={() => {}}
      createAnnotationHandler={noopCreateAnnotation}
    />
  </div>
);
