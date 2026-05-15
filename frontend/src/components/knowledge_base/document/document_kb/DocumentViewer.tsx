import React from "react";
import { Spinner } from "@os-legal/ui";
import { FileText } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
// ``PDFContainer`` is the styled.div used by every renderer (PDF, TXT,
// DOCX). The exported name is historical — re-aliased here as
// ``ViewerContainer`` so the per-filetype branches below don't read as
// "wrap text/DOCX in a PDF container". The styling contract is shared
// across renderers; renaming the source export is tracked separately.
import { PDFContainer as ViewerContainer } from "../../../annotator/display/viewer/DocumentViewer";
import { PDF } from "../../../annotator/renderers/pdf/PDF";
import TxtAnnotatorWrapper from "../../../annotator/components/wrappers/TxtAnnotatorWrapper";
import DocxAnnotatorWrapper from "../../../annotator/components/wrappers/DocxAnnotatorWrapper";
import { ViewState } from "../../../types";
import {
  isTextFileType,
  isPdfFileType,
  isDocxFileType,
} from "../../../../utils/files";
import { EmptyState } from "./EmptyStates";
import { ServerTokenAnnotation } from "../../../annotator/types/annotations";

interface ViewerStatusProps {
  loadingLabel: string;
  errorTitle: string;
  errorDescription: string;
  viewState: ViewState;
  children: React.ReactNode;
}

const loadingBlock = (label: string) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      height: "100%",
      gap: "0.5rem",
    }}
  >
    <Spinner size={24} />
    <span
      style={{
        color: OS_LEGAL_COLORS.textSecondary,
        fontSize: "0.875rem",
      }}
    >
      {label}
    </span>
  </div>
);

const ViewerStatus: React.FC<ViewerStatusProps> = ({
  loadingLabel,
  errorTitle,
  errorDescription,
  viewState,
  children,
}) => {
  if (viewState === ViewState.LOADED) return <>{children}</>;
  if (viewState === ViewState.LOADING) return loadingBlock(loadingLabel);
  return (
    <EmptyState
      icon={<FileText size={40} />}
      title={errorTitle}
      description={errorDescription}
    />
  );
};

export interface DocumentViewerProps {
  /** MIME-style filetype string from the document's metadata */
  fileType: string;
  /** Current load state for the document body (PDF/PAWLS/DOCX/text) */
  viewState: ViewState;
  /** Whether annotations can be created/edited (passed to PDF only) */
  canEdit: boolean;
  /** Measured width of the viewer container, used for fit-to-width zoom */
  containerWidth: number | null;
  /** Ref callback that publishes the container element to atoms + zoom hooks */
  containerRefCallback: React.RefCallback<HTMLDivElement>;
  /** Annotation creation handler (PDF only) */
  createAnnotationHandler: (annotation: ServerTokenAnnotation) => Promise<void>;
  /** OC_URL link-annotation creator (PDF only); enables the "Add link" action. */
  createUrlAnnotationHandler?: (
    annotation: ServerTokenAnnotation,
    url: string
  ) => Promise<void>;
}

/**
 * Renders the central document body — PDF, plain-text, or DOCX — based on the
 * document's filetype. Each branch shares the same loading / error scaffolding;
 * only the loaded renderer differs. Unsupported filetypes show a generic empty
 * state.
 */
export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  fileType,
  viewState,
  canEdit,
  containerWidth,
  containerRefCallback,
  createAnnotationHandler,
  createUrlAnnotationHandler,
}) => {
  if (isPdfFileType(fileType)) {
    return (
      <ViewerContainer id="pdf-container" ref={containerRefCallback}>
        <ViewerStatus
          loadingLabel="Loading PDF..."
          errorTitle="Error Loading PDF"
          errorDescription="Could not load the PDF document."
          viewState={viewState}
        >
          <PDF
            read_only={!canEdit}
            containerWidth={containerWidth}
            createAnnotationHandler={createAnnotationHandler}
            createUrlAnnotationHandler={createUrlAnnotationHandler}
          />
        </ViewerStatus>
      </ViewerContainer>
    );
  }

  if (isTextFileType(fileType)) {
    return (
      <ViewerContainer id="text-container" ref={containerRefCallback}>
        <ViewerStatus
          loadingLabel="Loading Text..."
          errorTitle="Error Loading Text"
          errorDescription="Could not load the text file."
          viewState={viewState}
        >
          <TxtAnnotatorWrapper readOnly={!canEdit} allowInput={canEdit} />
        </ViewerStatus>
      </ViewerContainer>
    );
  }

  if (isDocxFileType(fileType)) {
    return (
      <ViewerContainer id="docx-container" ref={containerRefCallback}>
        <ViewerStatus
          loadingLabel="Loading DOCX..."
          errorTitle="Error Loading DOCX"
          errorDescription="Could not load the Word document."
          viewState={viewState}
        >
          <DocxAnnotatorWrapper readOnly={!canEdit} allowInput={canEdit} />
        </ViewerStatus>
      </ViewerContainer>
    );
  }

  return (
    <div
      style={{
        padding: "2rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
      }}
    >
      {viewState === ViewState.LOADING ? (
        loadingBlock("Loading Document...")
      ) : (
        <EmptyState
          icon={<FileText size={40} />}
          title="Unsupported File"
          description="This document type can't be displayed."
        />
      )}
    </div>
  );
};
