import React from "react";
import { MemoryRouter } from "react-router-dom";
import { DesktopDocumentLayout } from "../src/components/knowledge_base/document/layouts/DesktopDocumentLayout";
import type { DocumentLayoutProps } from "../src/components/knowledge_base/document/layouts/types";
import { PdfAnnotations } from "../src/components/annotator/types/annotations";

const noop = () => {};

const baseStubProps: DocumentLayoutProps = {
  documentId: "doc-1",
  corpusId: "corpus-1",
  readOnly: false,
  showCorpusInfo: false,
  showSuccessMessage: undefined,

  activeLayer: "document",
  setActiveLayer: noop,
  showRightPanel: false,
  setShowRightPanel: noop,
  sidebarViewMode: "chat",
  setSidebarViewMode: noop,

  showGraph: false,
  setShowGraph: noop,
  selectedNote: null,
  setSelectedNote: noop,
  editingNoteId: null,
  setEditingNoteId: noop,
  showNewNoteModal: false,
  setShowNewNoteModal: noop,
  showAddToCorpusModal: false,
  setShowAddToCorpusModal: noop,

  feedFilters: { contentTypes: new Set() },
  setFeedFilters: noop,
  feedSortBy: "page",
  setFeedSortBy: noop,

  showAnalysesPanel: false,
  setShowAnalysesPanel: noop,
  showExtractsPanel: false,
  setShowExtractsPanel: noop,

  pendingChatMessage: undefined,
  setPendingChatMessage: noop,

  setSelectedSummaryContent: noop,

  metadata: {
    title: "Stub Document",
    fileType: "application/pdf",
    creator: null,
    created: null,
  },
  hasCorpus: false,

  zoomLevel: 1,
  setZoomLevel: noop,
  showZoomIndicator: false,
  showZoomFeedback: noop,
  autoZoomEnabled: false,
  setAutoZoomEnabled: noop,

  mainLayerContent: <div data-testid="stub-main-layer">Document surface</div>,
  viewerContent: <div data-testid="stub-viewer">PDF viewer</div>,
  floatingControlsState: { offset: 0, visible: false },

  mode: "quarter",
  setMode: noop,
  isDragging: false,
  handleResizeStart: noop,
  handlePanelMouseEnter: noop,
  getPanelWidthPercentage: () => 25,

  handleClose: noop,
  handleClearAnalysisExtractSelection: noop,

  pdfAnnotations: new PdfAnnotations([], [], []),
  analyses: [],
  extracts: [],
  selectedAnalysis: null,
  selectedExtract: null,
  threadCount: 0,
  dataCells: [],
  columns: [],
  notes: [],
  loading: false,
  queryError: undefined,
  corpusData: undefined,
  combinedDocumentData: null,
  refetch: noop,
  corpusMdContent: null,

  searchText: "",

  canEdit: true,
  activeSpanLabel: null,
  setActiveSpanLabel: noop,

  setChatSourceState: noop,
};

interface DesktopHarnessProps {
  /**
   * When true, the layout renders with the right panel open — the
   * `RightEdgeRail` branch is *not* taken; the sidebar tabs anchor to the
   * left edge of the panel instead.
   */
  showRightPanel?: boolean;
  threadCount?: number;
}

/**
 * Test harness for {@link DesktopDocumentLayout}. Mirrors the
 * `MobileLayoutHarness` pattern: a complete prop stub satisfies the
 * `DesktopDocumentLayoutProps` interface so the layout renders
 * without GraphQL or Apollo plumbing. Used to cover the unified
 * `RightEdgeRail` rendering path (issue #1734) in CT tests.
 */
export const DesktopLayoutHarness: React.FC<DesktopHarnessProps> = ({
  showRightPanel = false,
  threadCount = 0,
}) => (
  <MemoryRouter>
    <div style={{ height: 800, width: 1280 }}>
      <DesktopDocumentLayout
        {...baseStubProps}
        showRightPanel={showRightPanel}
        threadCount={threadCount}
      />
    </div>
  </MemoryRouter>
);
