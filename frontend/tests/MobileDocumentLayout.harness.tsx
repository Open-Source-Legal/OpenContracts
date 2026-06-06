import React from "react";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { relayStylePagination } from "@apollo/client/utilities";
import { MobileDocumentLayout } from "../src/components/knowledge_base/document/layouts/MobileDocumentLayout";
import type { DesktopDocumentLayoutProps } from "../src/components/knowledge_base/document/layouts/DesktopDocumentLayout";
import { PdfAnnotations } from "../src/components/annotator/types/annotations";
import { GET_DOCUMENT_ANNOTATION_INDEX } from "../src/graphql/queries";
import {
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  OC_SECTION_LABEL,
} from "../src/assets/configurations/constants";

/**
 * Test harness for {@link MobileDocumentLayout}.
 *
 * Supplies a full set of stub props satisfying {@link DesktopDocumentLayoutProps}.
 * Surface contents are placeholder nodes — later tasks wire the real surfaces.
 */
const noop = () => {};

const stubProps: DesktopDocumentLayoutProps = {
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
  // hasCorpus is false so HeaderBar does not render DocumentVersionSelector,
  // which requires a react-router context the CT harness does not provide.
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

// The Sections sheet (MobileSectionsSheet) now loads the document's OC_SECTION
// index via GET_DOCUMENT_ANNOTATION_INDEX, so the layout needs an Apollo
// client once that sheet mounts. The stub document carries no index entries,
// so the mock returns an empty connection (the test expects the empty state).
const indexMock: MockedResponse = {
  request: {
    query: GET_DOCUMENT_ANNOTATION_INDEX,
    variables: {
      documentId: stubProps.documentId,
      corpusId: stubProps.corpusId,
      labelText: OC_SECTION_LABEL,
      first: DOCUMENT_ANNOTATION_INDEX_LIMIT,
    },
  },
  result: {
    data: {
      annotations: {
        totalCount: 0,
        edges: [],
        __typename: "AnnotationTypeConnection",
      },
    },
  },
};

const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          annotations: relayStylePagination([
            "documentId",
            "corpusId",
            "annotationLabel_Text",
          ]),
        },
      },
      AnnotationType: { keyFields: ["id"] },
    },
  });

/**
 * @param queryErrorMessage - when set, the layout is rendered with a
 *   `queryError`. The `Error` is constructed here (browser-side) rather than
 *   passed in: Playwright CT serializes `mount()` props, which strips an
 *   `Error` instance down to an empty object and loses `.message`.
 */
export const MobileLayoutHarness: React.FC<{ queryErrorMessage?: string }> = ({
  queryErrorMessage,
}) => (
  <MemoryRouter>
    <MockedProvider
      mocks={[indexMock, { ...indexMock }]}
      cache={createTestCache()}
      addTypename
    >
      <div style={{ height: 844, width: 390 }}>
        <MobileDocumentLayout
          {...stubProps}
          queryError={
            queryErrorMessage ? new Error(queryErrorMessage) : undefined
          }
        />
      </div>
    </MockedProvider>
  </MemoryRouter>
);
