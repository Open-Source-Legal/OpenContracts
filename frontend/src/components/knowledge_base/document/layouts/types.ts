import React, { Dispatch, SetStateAction } from "react";

import { ContentFilters, SortOption, SidebarViewMode } from "../unified_feed";
import { DocumentMetadata } from "../document_kb/HeaderBar";

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
 * Shared prop contract for both DesktopDocumentLayout and MobileDocumentLayout
 * — every value is owned by DocumentKnowledgeBase, which picks the layout based
 * on the current viewport width.
 */
export interface DocumentLayoutProps {
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
