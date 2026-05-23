import React from "react";
import { AnimatePresence } from "framer-motion";
import { toast } from "react-toastify";

import {
  ContentArea,
  MainContentArea,
  SlidingPanel,
  ResizeHandle,
} from "../StyledContainers";
import { FullScreenModal } from "../LayoutComponents";
import { SafeMarkdown } from "../../markdown/SafeMarkdown";
import { EnhancedLabelSelector } from "../../../annotator/labels/EnhancedLabelSelector";
import { FloatingSummaryPreview } from "../floating_summary_preview/FloatingSummaryPreview";
import { ZoomControls } from "../ZoomControls";
import { FloatingDocumentControls } from "../FloatingDocumentControls";
import { FloatingDocumentInput } from "../FloatingDocumentInput";
import { FloatingAnalysesPanel } from "../FloatingAnalysesPanel";
import { FloatingExtractsPanel } from "../FloatingExtractsPanel";

import {
  ErrorMessage,
  InfoMessage,
  SuccessMessage,
} from "../../../widgets/feedback";

import { FloatingInputWrapper, ZoomIndicator } from "../document_kb/styles";
import { RightPanelContent } from "../document_kb/RightPanelContent";
import { DocumentModals } from "../document_kb/DocumentModals";
import { AnalysisExtractContextBar } from "../document_kb/ContextBar";
import { DesktopSidebarTabs } from "../document_kb/SidebarTabs";
import { HeaderBar } from "../document_kb/HeaderBar";

import {
  ZOOM_MIN,
  ZOOM_MAX,
} from "../../../../assets/configurations/constants";

import { DocumentLayoutProps } from "./types";

/**
 * Desktop layout for the DocumentKnowledgeBase. Renders the full-screen modal
 * shell: header, context bar, content area (zoom controls, floating input,
 * main layer content, floating controls/panels), the sliding right panel, and
 * the document modals.
 *
 * This component owns no state and no data-loading hooks — it is a verbatim
 * extraction of the previous desktop render from DocumentKnowledgeBase.
 */
export const DesktopDocumentLayout: React.FC<DocumentLayoutProps> = (props) => {
  const {
    documentId,
    corpusId,
    readOnly,
    showCorpusInfo,
    showSuccessMessage,
    activeLayer,
    setActiveLayer,
    showRightPanel,
    setShowRightPanel,
    sidebarViewMode,
    setSidebarViewMode,
    showGraph,
    setShowGraph,
    selectedNote,
    setSelectedNote,
    editingNoteId,
    setEditingNoteId,
    showNewNoteModal,
    setShowNewNoteModal,
    showAddToCorpusModal,
    setShowAddToCorpusModal,
    feedFilters,
    setFeedFilters,
    feedSortBy,
    setFeedSortBy,
    showAnalysesPanel,
    setShowAnalysesPanel,
    showExtractsPanel,
    setShowExtractsPanel,
    pendingChatMessage,
    setPendingChatMessage,
    setSelectedSummaryContent,
    metadata,
    hasCorpus,
    zoomLevel,
    setZoomLevel,
    showZoomIndicator,
    showZoomFeedback,
    autoZoomEnabled,
    setAutoZoomEnabled,
    mainLayerContent,
    floatingControlsState,
    mode,
    setMode,
    isDragging,
    handleResizeStart,
    handlePanelMouseEnter,
    getPanelWidthPercentage,
    handleClose,
    handleClearAnalysisExtractSelection,
    pdfAnnotations,
    analyses,
    extracts,
    selectedAnalysis,
    selectedExtract,
    threadCount,
    dataCells,
    columns,
    notes,
    loading,
    queryError,
    corpusData,
    combinedDocumentData,
    refetch,
    corpusMdContent,
    searchText,
    canEdit,
    activeSpanLabel,
    setActiveSpanLabel,
    setChatSourceState,
  } = props;

  return (
    <FullScreenModal
      id="knowledge-base-modal"
      open={true}
      onClose={handleClose}
    >
      <HeaderBar
        metadata={metadata}
        documentId={documentId}
        corpusId={corpusId}
        hasCorpus={Boolean(hasCorpus)}
        readOnly={readOnly}
        onAddToCorpus={() => setShowAddToCorpusModal(true)}
        onClose={() => handleClose()}
      />

      {/* Context Bar - shows when analysis or extract is selected */}
      <AnalysisExtractContextBar
        selectedAnalysis={selectedAnalysis}
        selectedExtract={selectedExtract}
        pdfAnnotations={pdfAnnotations}
        analysesCount={analyses.length}
        extractsCount={extracts.length}
        onClearSelection={handleClearAnalysisExtractSelection}
      />

      {/* Error message for GraphQL failures - show prominently and prevent other content */}
      {queryError ? (
        <ContentArea id="content-area">
          <div style={{ padding: "2rem", textAlign: "center" }}>
            <ErrorMessage title="Error loading document">
              {queryError.message}
            </ErrorMessage>
          </div>
        </ContentArea>
      ) : (
        <>
          {/* Corpus info display */}
          {showCorpusInfo && corpusData?.corpus && (
            <InfoMessage title={`Corpus: ${corpusData.corpus.title}`}>
              {(corpusMdContent || corpusData.corpus.description) && (
                <SafeMarkdown>
                  {corpusMdContent || corpusData.corpus.description || ""}
                </SafeMarkdown>
              )}
            </InfoMessage>
          )}

          {/* Success message if just added to corpus */}
          {showSuccessMessage && (
            <SuccessMessage>{showSuccessMessage}</SuccessMessage>
          )}

          <ContentArea id="content-area">
            {/* Zoom Controls - positioned relative to ContentArea */}
            {activeLayer === "document" && (
              <ZoomControls
                zoomLevel={zoomLevel}
                onZoomIn={() => {
                  setZoomLevel(Math.min(zoomLevel + 0.1, ZOOM_MAX));
                  showZoomFeedback();
                }}
                onZoomOut={() => {
                  setZoomLevel(Math.max(zoomLevel - 0.1, ZOOM_MIN));
                  showZoomFeedback();
                }}
              />
            )}

            {/* Unified Search/Chat Input - positioned relative to ContentArea */}
            <FloatingInputWrapper $panelOffset={floatingControlsState.offset}>
              <FloatingDocumentInput
                fixed={false}
                visible={activeLayer === "document"}
                readOnly={readOnly}
                onChatSubmit={(message) => {
                  setPendingChatMessage(message);
                  setSidebarViewMode("chat");
                  setShowRightPanel(true);
                }}
                onToggleChat={() => {
                  setSidebarViewMode("chat");
                  setShowRightPanel(true);
                }}
              />
            </FloatingInputWrapper>

            <MainContentArea id="main-content-area">
              {mainLayerContent}
              <EnhancedLabelSelector
                sidebarWidth="0px"
                activeSpanLabel={canEdit ? activeSpanLabel ?? null : null}
                setActiveLabel={canEdit ? setActiveSpanLabel : () => {}}
                showRightPanel={showRightPanel}
                panelOffset={floatingControlsState.offset}
                hideControls={!floatingControlsState.visible || !canEdit}
                readOnly={!canEdit}
              />

              {/* Floating Summary Preview - only visible when corpus is available */}
              {corpusId && (
                <FloatingSummaryPreview
                  documentId={documentId}
                  corpusId={corpusId}
                  documentTitle={metadata.title || "Untitled Document"}
                  isVisible={true}
                  isInKnowledgeLayer={activeLayer === "knowledge"}
                  readOnly={readOnly}
                  onSwitchToKnowledge={(content?: string) => {
                    setActiveLayer("knowledge");
                    setShowRightPanel(false);
                    if (content) {
                      setSelectedSummaryContent(content);
                    } else {
                      setSelectedSummaryContent(null);
                    }
                    setChatSourceState((prev) => ({
                      ...prev,
                      selectedMessageId: null,
                      selectedSourceIndex: null,
                    }));
                  }}
                  onBackToDocument={() => {
                    setActiveLayer("document");
                    setSelectedSummaryContent(null);
                    // When going back to document, show chat panel by default
                    setShowRightPanel(true);
                    setSidebarViewMode("chat");
                  }}
                />
              )}

              {/* Zoom Indicator - shows current zoom level when zooming */}
              {showZoomIndicator && activeLayer === "document" && (
                <ZoomIndicator data-testid="zoom-indicator">
                  {Math.round(zoomLevel * 100)}%
                </ZoomIndicator>
              )}

              {/* Floating Document Controls - only in document layer */}
              <FloatingDocumentControls
                visible={activeLayer === "document"}
                showRightPanel={showRightPanel}
                onAnalysesClick={() => {
                  if (!corpusId) {
                    toast.info("Add document to corpus to run analyses");
                    setShowAddToCorpusModal(true);
                  } else {
                    setShowAnalysesPanel(!showAnalysesPanel);
                  }
                }}
                onExtractsClick={() => {
                  if (!corpusId) {
                    toast.info("Add document to corpus for data extraction");
                    setShowAddToCorpusModal(true);
                  } else {
                    setShowExtractsPanel(!showExtractsPanel);
                  }
                }}
                onSummaryClick={() => {
                  setActiveLayer("knowledge");
                  setShowRightPanel(false);
                  setSelectedSummaryContent(null);
                  setChatSourceState((prev) => ({
                    ...prev,
                    selectedMessageId: null,
                    selectedSourceIndex: null,
                  }));
                }}
                analysesOpen={showAnalysesPanel}
                extractsOpen={showExtractsPanel}
                panelOffset={floatingControlsState.offset}
                readOnly={readOnly}
                panelWidthMode={mode === "custom" ? "half" : mode}
                onPanelWidthChange={setMode}
                autoZoomEnabled={autoZoomEnabled}
                onAutoZoomChange={setAutoZoomEnabled}
                hideDocumentTools={showRightPanel && sidebarViewMode === "chat"}
              />

              {/* Floating Analyses Panel - only show with corpus and when no analysis selected (results now in sidebar) */}
              {corpusId && (
                <FloatingAnalysesPanel
                  visible={
                    showAnalysesPanel &&
                    activeLayer === "document" &&
                    !selectedAnalysis
                  }
                  analyses={analyses}
                  onClose={() => setShowAnalysesPanel(false)}
                  panelOffset={floatingControlsState.offset}
                  readOnly={readOnly}
                />
              )}

              {/* Floating Extracts Panel - only show with corpus and when no extract selected (results now in sidebar) */}
              {corpusId && (
                <FloatingExtractsPanel
                  visible={
                    showExtractsPanel &&
                    activeLayer === "document" &&
                    !selectedExtract
                  }
                  extracts={extracts}
                  onClose={() => setShowExtractsPanel(false)}
                  panelOffset={floatingControlsState.offset}
                  readOnly={readOnly}
                />
              )}

              {/* Sidebar View Mode Tabs - shown to the right of the document
                  while the panel is closed; the panel-open variant lives
                  inside the SlidingPanel below. */}
              {!showRightPanel && (
                <DesktopSidebarTabs
                  panelOpen={false}
                  sidebarViewMode={sidebarViewMode}
                  setSidebarViewMode={setSidebarViewMode}
                  setShowRightPanel={setShowRightPanel}
                  setMode={setMode}
                  selectedAnalysis={selectedAnalysis}
                  selectedExtract={selectedExtract}
                  threadCount={threadCount}
                />
              )}

              {/* Right Panel, if needed */}
              <AnimatePresence>
                {showRightPanel && (
                  <SlidingPanel
                    id="sliding-panel"
                    panelWidth={getPanelWidthPercentage()}
                    onMouseEnter={handlePanelMouseEnter}
                    initial={{ x: "100%", opacity: 0 }}
                    animate={{ x: "0%", opacity: 1 }}
                    exit={{ x: "100%", opacity: 0 }}
                    transition={{
                      x: { type: "spring", damping: 30, stiffness: 300 },
                      opacity: { duration: 0.2, ease: "easeOut" },
                    }}
                  >
                    <ResizeHandle
                      id="resize-handle"
                      onMouseDown={handleResizeStart}
                      $isDragging={isDragging}
                      whileHover={{ scale: 1.02 }}
                    />

                    {/* Tabs when panel is open - positioned on left edge of panel (desktop only) */}
                    <DesktopSidebarTabs
                      panelOpen={true}
                      sidebarViewMode={sidebarViewMode}
                      setSidebarViewMode={setSidebarViewMode}
                      setShowRightPanel={setShowRightPanel}
                      setMode={setMode}
                      selectedAnalysis={selectedAnalysis}
                      selectedExtract={selectedExtract}
                      threadCount={threadCount}
                    />

                    <RightPanelContent
                      showRightPanel={showRightPanel}
                      sidebarViewMode={sidebarViewMode}
                      setSidebarViewMode={setSidebarViewMode}
                      feedFilters={feedFilters}
                      setFeedFilters={setFeedFilters}
                      feedSortBy={feedSortBy}
                      setFeedSortBy={setFeedSortBy}
                      searchText={searchText}
                      selectedAnalysis={selectedAnalysis}
                      selectedExtract={selectedExtract}
                      dataCells={dataCells}
                      columns={columns}
                      notes={notes}
                      loading={loading}
                      readOnly={readOnly}
                      documentId={documentId}
                      corpusId={corpusId}
                      setActiveLayer={setActiveLayer}
                      setSelectedNote={setSelectedNote}
                      pendingChatMessage={pendingChatMessage}
                    />
                  </SlidingPanel>
                )}
              </AnimatePresence>
            </MainContentArea>
          </ContentArea>

          <DocumentModals
            showGraph={showGraph}
            setShowGraph={setShowGraph}
            selectedNote={selectedNote}
            setSelectedNote={setSelectedNote}
            editingNoteId={editingNoteId}
            setEditingNoteId={setEditingNoteId}
            showNewNoteModal={showNewNoteModal}
            setShowNewNoteModal={setShowNewNoteModal}
            showAddToCorpusModal={showAddToCorpusModal}
            setShowAddToCorpusModal={setShowAddToCorpusModal}
            readOnly={readOnly}
            documentId={documentId}
            corpusId={corpusId}
            refetch={refetch}
            combinedDocumentData={combinedDocumentData}
          />
        </>
      )}
    </FullScreenModal>
  );
};
