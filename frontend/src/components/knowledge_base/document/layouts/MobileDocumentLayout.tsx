import React, { useState } from "react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { useAnnotationSelection } from "../../../annotator/context/UISettingsAtom";
import { HeaderBar } from "../document_kb/HeaderBar";
import { MobileAskBar } from "./mobile/MobileAskBar";
import { MobileDocToolbar } from "./mobile/MobileDocToolbar";
import { MobileFindSheet } from "./mobile/MobileFindSheet";
import { MobileSectionsSheet } from "./mobile/MobileSectionsSheet";
import { MobileSheet } from "./mobile/MobileSheet";
import { MobileTabBar, MobileTabId } from "./mobile/MobileTabBar";
import { useMobileFitToWidth } from "./mobile/useMobileFitToWidth";
import { DesktopDocumentLayoutProps } from "./DesktopDocumentLayout";
import UnifiedKnowledgeLayer from "../layers/UnifiedKnowledgeLayer";

/**
 * Root flex column: chrome (header / ask bar / tab bar) stays fixed while
 * only the surface area scrolls.
 */
const Root = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: ${OS_LEGAL_COLORS.background};
  position: relative;
  overflow: hidden;
`;

/** Scrollable surface area — swaps content based on the active tab. */
const Surface = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  position: relative;
`;

/**
 * Document surface: a fixed toolbar on top, the viewer fills the rest.
 * The viewer itself owns its internal scrolling, so this column does not
 * scroll — it just sizes the viewer to the available space.
 */
const DocumentSurface = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
`;

const ViewerArea = styled.div`
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
`;

/** Placeholder body for the "More" sheet — replaced by Task 12. */
const SheetPlaceholder = styled.div`
  padding: 16px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

/**
 * Summary surface wrapper: fills the scrollable {@link Surface} so the
 * {@link UnifiedKnowledgeLayer} (`height: 100%`) sizes correctly.
 */
const SummarySurface = styled.div`
  height: 100%;
  min-height: 0;
`;

/** Empty state shown on the Summary tab when the document has no corpus. */
const SummaryEmptyState = styled.div`
  padding: 24px 16px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-align: center;
`;

/**
 * Mobile layout for the DocumentKnowledgeBase.
 *
 * Owns only local UI state (the active {@link MobileTabId} and which sheets
 * are open); every other value is threaded in via
 * {@link DesktopDocumentLayoutProps} — the same interface the desktop layout
 * consumes. The two layouts are alternative presentations of identical
 * data/state.
 *
 * Task 8 wires the Document surface: the real document viewer
 * ({@link DesktopDocumentLayoutProps.viewerContent}) below a
 * {@link MobileDocToolbar}, defaulting to fit-to-width so the document is
 * readable on mount. Sections and Find open {@link MobileSheet}s over the
 * existing structural-annotation and text-search systems. Tasks 9–12 fill in
 * the Summary / Annotations / Chat / More surfaces.
 */
export const MobileDocumentLayout: React.FC<DesktopDocumentLayoutProps> = (
  props
) => {
  const {
    documentId,
    corpusId,
    readOnly,
    metadata,
    hasCorpus,
    mainLayerContent,
    viewerContent,
    zoomLevel,
    setZoomLevel,
    handleClose,
    setShowAddToCorpusModal,
    setActiveLayer,
    setSidebarViewMode,
    setShowRightPanel,
    setPendingChatMessage,
  } = props;

  const [activeTab, setActiveTab] = useState<MobileTabId>("document");
  const [moreSheetOpen, setMoreSheetOpen] = useState(false);
  const [sectionsSheetOpen, setSectionsSheetOpen] = useState(false);
  const [findSheetOpen, setFindSheetOpen] = useState(false);

  const { setSelectedAnnotations } = useAnnotationSelection();

  // Fit-to-width: default the document to a readable zoom on mount and back
  // the toolbar's "Fit width" chip. Gated on the Document tab being active.
  const { fitToWidth } = useMobileFitToWidth({
    active: activeTab === "document",
    setZoomLevel,
  });

  const handleSelectTab = (tab: MobileTabId) => {
    switch (tab) {
      case "document":
        setActiveLayer("document");
        setActiveTab("document");
        break;
      case "summary":
        setActiveLayer("knowledge");
        setActiveTab("summary");
        break;
      case "annotations":
        setActiveLayer("document");
        setSidebarViewMode("feed");
        setActiveTab("annotations");
        break;
      case "more":
        setMoreSheetOpen(true);
        break;
    }
  };

  return (
    <Root>
      <HeaderBar
        metadata={metadata}
        documentId={documentId}
        corpusId={corpusId}
        hasCorpus={Boolean(hasCorpus)}
        readOnly={readOnly}
        onAddToCorpus={() => setShowAddToCorpusModal(true)}
        onClose={handleClose}
      />

      <Surface>
        {activeTab === "document" && (
          <DocumentSurface data-testid="mobile-surface-document">
            <MobileDocToolbar
              zoomPercent={zoomLevel * 100}
              onFitWidth={fitToWidth}
              onSections={() => setSectionsSheetOpen(true)}
              onFind={() => setFindSheetOpen(true)}
            />
            <ViewerArea>{viewerContent}</ViewerArea>
          </DocumentSurface>
        )}
        {activeTab === "summary" && (
          <SummarySurface data-testid="mobile-surface-summary">
            {corpusId ? (
              <UnifiedKnowledgeLayer
                documentId={documentId}
                corpusId={corpusId}
                metadata={metadata}
                parentLoading={props.loading}
                readOnly={readOnly}
              />
            ) : (
              <SummaryEmptyState>
                Add this document to a corpus to view its summary.
              </SummaryEmptyState>
            )}
          </SummarySurface>
        )}
        {activeTab === "annotations" && (
          <div data-testid="mobile-surface-annotations">{mainLayerContent}</div>
        )}
      </Surface>

      <MobileAskBar
        onActivate={() => {
          setSidebarViewMode("chat");
          setShowRightPanel(true);
        }}
        onSubmit={(text) => {
          setPendingChatMessage(text);
          setSidebarViewMode("chat");
          setShowRightPanel(true);
        }}
      />

      <MobileTabBar active={activeTab} onSelect={handleSelectTab} />

      <MobileSheet
        open={sectionsSheetOpen}
        title="Sections"
        onClose={() => setSectionsSheetOpen(false)}
      >
        <MobileSectionsSheet
          open={sectionsSheetOpen}
          onNavigate={(annotationId) => {
            setSelectedAnnotations([annotationId]);
            setSectionsSheetOpen(false);
          }}
        />
      </MobileSheet>

      <MobileSheet
        open={findSheetOpen}
        title="Find in document"
        onClose={() => setFindSheetOpen(false)}
      >
        <MobileFindSheet open={findSheetOpen} />
      </MobileSheet>

      <MobileSheet
        open={moreSheetOpen}
        title="More"
        onClose={() => setMoreSheetOpen(false)}
      >
        <SheetPlaceholder data-testid="mobile-surface-more">
          More options coming soon.
        </SheetPlaceholder>
      </MobileSheet>
    </Root>
  );
};

export default MobileDocumentLayout;
