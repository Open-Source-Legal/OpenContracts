import React, { Dispatch, SetStateAction } from "react";
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
import { ContentFilters, SortOption, SidebarViewMode } from "../unified_feed";
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
import {
  DesktopSidebarTabs,
  MobileSidebarTabs,
} from "../document_kb/SidebarTabs";
import { HeaderBar, DocumentMetadata } from "../document_kb/HeaderBar";

import {
  AnalysisType,
  ColumnType,
  DatacellType,
  ExtractType,
  NoteType,
} from "../../../../types/graphql-api";
import { PdfAnnotations } from "../../../annotator/types/annotations";
import { useChatSourceState } from "../../../annotator/context/ChatSourceAtom";
import {
  useAnnotationControls,
  ChatPanelWidthMode,
} from "../../../annotator/context/UISettingsAtom";

/**
 * Props for {@link DesktopDocumentLayout}.
 *
 * This is a purely presentational component: every value it needs is passed
 * in from {@link DocumentKnowledgeBase}, which owns all hooks, data loading,
 * effects, and derived state. The desktop render was moved here verbatim with
 * no behavior change.
 */
export interface DesktopDocumentLayoutProps {
  /* ----- Component props threaded through from DocumentKnowledgeBase ----- */
  documentId: string;
  corpusId?: string;
  readOnly: boolean;
  showCorpusInfo?: boolean;
  showSuccessMessage?: string;

  /* ----- Layer / panel state ----- */
  activeLayer: "knowledge" | "document";
  setActiveLayer: Dispatch<SetStateAction<"knowledge" | "document">>;
  showRightPanel: boolean;
  setShowRightPanel: Dispatch<SetStateAction<boolean>>;
  sidebarViewMode: SidebarViewMode["mode"];
  setSidebarViewMode: Dispatch<SetStateAction<SidebarViewMode["mode"]>>;

  /* ----- Modal state ----- */
  showGraph: boolean;
  setShowGraph: Dispatch<SetStateAction<boolean>>;
  selectedNote: NoteType | null;
  setSelectedNote: Dispatch<SetStateAction<NoteType | null>>;
  editingNoteId: string | null;
  setEditingNoteId: Dispatch<SetStateAction<string | null>>;
  showNewNoteModal: boolean;
  setShowNewNoteModal: Dispatch<SetStateAction<boolean>>;
  showAddToCorpusModal: boolean;
  setShowAddToCorpusModal: Dispatch<SetStateAction<boolean>>;

  /* ----- Unified feed state ----- */
  feedFilters: ContentFilters;
  setFeedFilters: Dispatch<SetStateAction<ContentFilters>>;
  feedSortBy: SortOption;
  setFeedSortBy: Dispatch<SetStateAction<SortOption>>;

  /* ----- Floating panel state ----- */
  showAnalysesPanel: boolean;
  setShowAnalysesPanel: Dispatch<SetStateAction<boolean>>;
  showExtractsPanel: boolean;
  setShowExtractsPanel: Dispatch<SetStateAction<boolean>>;

  /* ----- Chat ----- */
  pendingChatMessage: string | undefined;
  setPendingChatMessage: Dispatch<SetStateAction<string | undefined>>;

  /* ----- Summary ----- */
  setSelectedSummaryContent: Dispatch<SetStateAction<string | null>>;

  /* ----- Document metadata / derived ----- */
  metadata: DocumentMetadata;
  hasCorpus: boolean;

  /* ----- Zoom ----- */
  zoomLevel: number;
  setZoomLevel: (zoom: number) => void;
  showZoomIndicator: boolean;
  showZoomFeedback: () => void;
  autoZoomEnabled: boolean;
  setAutoZoomEnabled: (enabled: boolean) => void;

  /* ----- Center content + floating controls ----- */
  mainLayerContent: React.ReactNode;
  /**
   * The bare document viewer (PDF / text / DOCX) — the same node embedded
   * inside `mainLayerContent`'s `#document-layer` wrapper. Exposed separately
   * so the mobile layout can render the viewer directly without the desktop
   * panel-width math that wrapper applies.
   */
  viewerContent: React.ReactNode;
  floatingControlsState: { offset: number; visible: boolean };

  /* ----- Panel width / resize ----- */
  mode: ChatPanelWidthMode;
  setMode: (mode: ChatPanelWidthMode) => void;
  isDragging: boolean;
  handleResizeStart: (e: React.MouseEvent) => void;
  handlePanelMouseEnter: () => void;
  getPanelWidthPercentage: () => number;

  /* ----- Handlers ----- */
  handleClose: () => void;
  handleClearAnalysisExtractSelection: () => void;

  /* ----- Data ----- */
  pdfAnnotations: PdfAnnotations;
  analyses: AnalysisType[];
  extracts: ExtractType[];
  selectedAnalysis: AnalysisType | null;
  selectedExtract: ExtractType | null;
  threadCount: number;
  dataCells: DatacellType[];
  columns: ColumnType[];
  notes: NoteType[];
  loading: boolean;
  queryError: Error | undefined;
  corpusData:
    | {
        corpus?: {
          title?: string | null;
          description?: string | null;
        } | null;
      }
    | undefined;
  combinedDocumentData?: {
    id: string;
    slug?: string | null;
    creator?: { id: string; slug?: string | null } | null;
  } | null;
  refetch: () => void;
  corpusMdContent: string | null;

  /* ----- Search ----- */
  searchText: string;

  /* ----- Annotation editing ----- */
  canEdit: boolean;
  activeSpanLabel: ReturnType<typeof useAnnotationControls>["activeSpanLabel"];
  setActiveSpanLabel: ReturnType<
    typeof useAnnotationControls
  >["setActiveSpanLabel"];

  /* ----- Chat source state ----- */
  setChatSourceState: ReturnType<
    typeof useChatSourceState
  >["setChatSourceState"];
}

/**
 * Desktop layout for the DocumentKnowledgeBase. Renders the full-screen modal
 * shell: header, context bar, content area (zoom controls, floating input,
 * main layer content, floating controls/panels), the sliding right panel, and
 * the document modals.
 *
 * This component owns no state and no data-loading hooks — it is a verbatim
 * extraction of the previous desktop render from DocumentKnowledgeBase.
 */
export const DesktopDocumentLayout: React.FC<DesktopDocumentLayoutProps> = (
  props
) => {
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
                  setZoomLevel(Math.min(zoomLevel + 0.1, 4));
                  showZoomFeedback();
                }}
                onZoomOut={() => {
                  setZoomLevel(Math.max(zoomLevel - 0.1, 0.5));
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

                    {/* Mobile Tab Bar - horizontal tabs at top for mobile */}
                    <MobileSidebarTabs
                      sidebarViewMode={sidebarViewMode}
                      setSidebarViewMode={setSidebarViewMode}
                      showRightPanel={showRightPanel}
                      setShowRightPanel={setShowRightPanel}
                      setMode={setMode}
                      selectedAnalysis={selectedAnalysis}
                      selectedExtract={selectedExtract}
                      threadCount={threadCount}
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

export default DesktopDocumentLayout;
