import React, { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider as JotaiProvider } from "jotai";
import { DesktopDocumentLayout } from "../src/components/knowledge_base/document/layouts/DesktopDocumentLayout";
import type { DocumentLayoutProps } from "../src/components/knowledge_base/document/layouts/types";
import { PdfAnnotations } from "../src/components/annotator/types/annotations";
import { GET_DOCUMENT_SUMMARY_VERSIONS } from "../src/components/knowledge_base/document/floating_summary_preview/graphql/documentSummaryQueries";

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
  floatingControlsState: { offset: 0, visible: true },

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
   * Override corpusId so tests can drive the `!corpusId` branch of the
   * action-button callbacks and gate FloatingSummaryPreview off.
   */
  corpusId?: string;
  /** Initial activeLayer ("knowledge" exercises back-to-document path). */
  activeLayer?: "knowledge" | "document";
  /** Optional Apollo mocks (e.g. summary version stack). */
  mocks?: ReadonlyArray<MockedResponse>;
  /** When true, the right panel is initially open (rail branch is skipped). */
  showRightPanel?: boolean;
  threadCount?: number;
  /** Initial sidebar view mode. */
  sidebarViewMode?: "chat" | "feed" | "index" | "discussions";
}

const createHarnessCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          document: { keyArgs: ["id"] },
        },
      },
    },
  });

/** Convenience mock for `GET_DOCUMENT_SUMMARY_VERSIONS`. */
export const buildSummaryVersionsMock = (
  documentId: string,
  corpusId: string
): MockedResponse => ({
  request: {
    query: GET_DOCUMENT_SUMMARY_VERSIONS,
    variables: { documentId, corpusId },
  },
  result: {
    data: {
      document: {
        id: documentId,
        summaryContent: "Current summary content.",
        currentSummaryVersion: 2,
        summaryRevisions: [
          {
            id: "rev-1",
            version: 1,
            snapshot: "First version snapshot content.",
            created: new Date(Date.now() - 86400000).toISOString(),
            diff: "Initial version",
            author: {
              id: "user-1",
              username: "user1",
              email: "user1@example.com",
            },
          },
          {
            id: "rev-2",
            version: 2,
            snapshot: "Current summary content.",
            created: new Date().toISOString(),
            diff: "Updated summary content",
            author: {
              id: "user-2",
              username: "user2",
              email: "user2@example.com",
            },
          },
        ],
      },
    },
  },
});

/**
 * Test harness for {@link DesktopDocumentLayout}. Provides a complete prop
 * stub satisfying `DocumentLayoutProps` so the layout renders standalone.
 *
 * Owns the slice of layout-driven state that the consolidated bottom-bar
 * (#1735) and right-edge rail (#1734) callbacks mutate, so CT tests can
 * click controls and assert on the resulting DOM shifts.
 */
export const DesktopLayoutHarness: React.FC<DesktopHarnessProps> = ({
  corpusId = "corpus-1",
  activeLayer: initialActiveLayer = "document",
  mocks = [],
  showRightPanel: initialShowRightPanel = false,
  threadCount = 0,
  sidebarViewMode: initialSidebarViewMode = "chat",
}) => {
  const [activeLayer, setActiveLayer] = useState<"knowledge" | "document">(
    initialActiveLayer
  );
  const [showRightPanel, setShowRightPanel] = useState(initialShowRightPanel);
  const [sidebarViewMode, setSidebarViewMode] = useState<
    "chat" | "feed" | "index" | "discussions"
  >(initialSidebarViewMode);
  const [pendingChatMessage, setPendingChatMessage] = useState<
    string | undefined
  >(undefined);
  const [selectedSummaryContent, setSelectedSummaryContent] = useState<
    string | null
  >(null);
  const [showAnalysesPanel, setShowAnalysesPanel] = useState(false);
  const [showExtractsPanel, setShowExtractsPanel] = useState(false);
  const [showAddToCorpusModal, setShowAddToCorpusModal] = useState(false);

  return (
    <MemoryRouter>
      <JotaiProvider>
        <MockedProvider mocks={mocks} cache={createHarnessCache()} addTypename>
          <div style={{ height: 800, width: 1280 }}>
            <DesktopDocumentLayout
              {...baseStubProps}
              corpusId={corpusId}
              activeLayer={activeLayer}
              setActiveLayer={setActiveLayer}
              showRightPanel={showRightPanel}
              setShowRightPanel={setShowRightPanel}
              sidebarViewMode={sidebarViewMode}
              setSidebarViewMode={setSidebarViewMode}
              pendingChatMessage={pendingChatMessage}
              setPendingChatMessage={setPendingChatMessage}
              setSelectedSummaryContent={setSelectedSummaryContent}
              showAnalysesPanel={showAnalysesPanel}
              setShowAnalysesPanel={setShowAnalysesPanel}
              showExtractsPanel={showExtractsPanel}
              setShowExtractsPanel={setShowExtractsPanel}
              showAddToCorpusModal={showAddToCorpusModal}
              setShowAddToCorpusModal={setShowAddToCorpusModal}
              threadCount={threadCount}
              floatingControlsState={{
                offset: showRightPanel ? 340 : 0,
                visible: true,
              }}
            />
            <div
              data-testid="harness-probe"
              data-active-layer={activeLayer}
              data-show-right-panel={String(showRightPanel)}
              data-sidebar-view-mode={sidebarViewMode}
              data-pending-chat-message={pendingChatMessage ?? ""}
              data-selected-summary-content={selectedSummaryContent ?? ""}
              style={{ display: "none" }}
            />
          </div>
        </MockedProvider>
      </JotaiProvider>
    </MemoryRouter>
  );
};
