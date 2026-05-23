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
   * Override corpusId so tests can drive corpus-less branches (e.g. the
   * FloatingSummaryPreview is gated on `corpusId` truthiness).
   */
  corpusId?: string;
  /**
   * Optional initial activeLayer — pass "knowledge" to test the
   * back-to-document callback path on FloatingSummaryPreview.
   */
  activeLayer?: "knowledge" | "document";
  /**
   * Optional Apollo mocks for FloatingSummaryPreview's version query so
   * tests can populate the version stack and exercise the
   * `onSwitchToKnowledge(content)` branch via a version-chip click.
   */
  mocks?: ReadonlyArray<MockedResponse>;
}

/**
 * Default no-op cache — MockedProvider always needs one; an empty
 * InMemoryCache is sufficient when tests don't provide mocks.
 */
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

/**
 * Convenience mock for `GET_DOCUMENT_SUMMARY_VERSIONS` — exported so tests
 * can opt-in to a populated version stack without redefining the shape
 * from scratch.
 */
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
 * stub that satisfies `DocumentLayoutProps` so the layout can render
 * standalone (no GraphQL, no Apollo data loaders).
 *
 * Owns the small slice of layout-driven state — activeLayer,
 * showRightPanel, sidebarViewMode, pendingChatMessage — that the
 * `DocumentBottomBar` inline callbacks mutate, so CT tests can click the
 * chat input / summary preview and assert on the resulting DOM shifts.
 * Used to cover the bottom-bar consolidation logic (issue #1735).
 */
export const DesktopLayoutHarness: React.FC<DesktopHarnessProps> = ({
  corpusId = "corpus-1",
  activeLayer: initialActiveLayer = "document",
  mocks = [],
}) => {
  const [activeLayer, setActiveLayer] = useState<"knowledge" | "document">(
    initialActiveLayer
  );
  const [showRightPanel, setShowRightPanel] = useState(false);
  const [sidebarViewMode, setSidebarViewMode] = useState<
    "chat" | "feed" | "index" | "discussions"
  >("chat");
  const [pendingChatMessage, setPendingChatMessage] = useState<
    string | undefined
  >(undefined);
  const [selectedSummaryContent, setSelectedSummaryContent] = useState<
    string | null
  >(null);

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
