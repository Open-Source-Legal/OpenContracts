import React, { useState } from "react";
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
  /**
   * Override corpusId so tests can drive the `!corpusId` branch of the
   * action-button callbacks (which toasts and opens the add-to-corpus modal).
   * Pass an empty string or `undefined` to disable the corpus.
   */
  corpusId?: string;
  /**
   * Sidebar view mode. The open-panel `FloatingDocumentControls` hides its
   * analyses/extracts buttons when this is `"chat"` (the panel covers the
   * same intents) — tests that need to click those buttons in the open
   * state should pass a non-chat mode.
   */
  sidebarViewMode?: "chat" | "feed" | "index" | "discussions";
}

/**
 * Test harness for {@link DesktopDocumentLayout}. Mirrors the
 * `MobileLayoutHarness` pattern: a complete prop stub satisfies the
 * `DesktopDocumentLayoutProps` interface so the layout renders
 * without GraphQL or Apollo plumbing.
 *
 * Stateful: the harness owns the small slice of state that the rail's
 * action-button callbacks mutate (showAnalysesPanel, showExtractsPanel,
 * showAddToCorpusModal). That lets CT tests click a button and assert on
 * the resulting DOM (FloatingAnalysesPanel / FloatingExtractsPanel / the
 * add-to-corpus modal becoming visible) — covering the inline callback
 * bodies in `DesktopDocumentLayout` for both corpus-present and corpus-
 * absent branches.
 */
export const DesktopLayoutHarness: React.FC<DesktopHarnessProps> = ({
  showRightPanel: initialShowRightPanel = false,
  threadCount = 0,
  corpusId = "corpus-1",
  sidebarViewMode: initialSidebarViewMode = "chat",
}) => {
  const [showRightPanel, setShowRightPanel] = useState(initialShowRightPanel);
  const [sidebarViewMode, setSidebarViewMode] = useState(
    initialSidebarViewMode
  );
  const [showAnalysesPanel, setShowAnalysesPanel] = useState(false);
  const [showExtractsPanel, setShowExtractsPanel] = useState(false);
  const [showAddToCorpusModal, setShowAddToCorpusModal] = useState(false);

  return (
    <MemoryRouter>
      <div style={{ height: 800, width: 1280 }}>
        <DesktopDocumentLayout
          {...baseStubProps}
          corpusId={corpusId}
          showRightPanel={showRightPanel}
          setShowRightPanel={setShowRightPanel}
          sidebarViewMode={sidebarViewMode}
          setSidebarViewMode={setSidebarViewMode}
          showAnalysesPanel={showAnalysesPanel}
          setShowAnalysesPanel={setShowAnalysesPanel}
          showExtractsPanel={showExtractsPanel}
          setShowExtractsPanel={setShowExtractsPanel}
          showAddToCorpusModal={showAddToCorpusModal}
          setShowAddToCorpusModal={setShowAddToCorpusModal}
          threadCount={threadCount}
          // Offset the floating controls left of the open SlidingPanel
          // (25% of the 1280px harness viewport) so CT tests can click
          // the analyses/extracts buttons without the panel overlapping
          // them. Doesn't matter when the panel is closed — the rail
          // branch ignores this value.
          floatingControlsState={{ offset: 340, visible: true }}
        />
      </div>
    </MemoryRouter>
  );
};
