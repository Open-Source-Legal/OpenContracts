import React, { useState, useEffect, useCallback, useRef } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import { unstable_batchedUpdates } from "react-dom";
import { Button, Header, Modal, Loader, Message } from "semantic-ui-react";
import {
  MessageSquare,
  FileText,
  User,
  Calendar,
  X,
  FileType,
  ArrowLeft,
  Settings,
  Plus,
  Layers,
  PanelRightOpen,
  Database,
  BarChart3,
  Download,
} from "lucide-react";
import {
  GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
  GetDocumentKnowledgeAndAnnotationsInput,
  GetDocumentKnowledgeAndAnnotationsOutput,
  GET_DOCUMENT_WITH_STRUCTURE,
  GetDocumentWithStructureInput,
  GetDocumentWithStructureOutput,
  GET_DOCUMENT_ANNOTATIONS_ONLY,
  GetDocumentAnnotationsOnlyInput,
  GetDocumentAnnotationsOnlyOutput,
  GET_CONVERSATIONS,
  GetConversationsInputs,
  GetConversationsOutputs,
} from "../../../graphql/queries";
import { useFeatureAvailability } from "../../../hooks/useFeatureAvailability";
import {
  getDocumentRawText,
  getPawlsLayer,
  getCachedPDFUrl,
} from "../../annotator/api/cachedRest";
import {
  CorpusType,
  LabelType,
  DocumentType,
} from "../../../types/graphql-api";
import { AnimatePresence } from "framer-motion";
import { PDFContainer } from "../../annotator/display/viewer/DocumentViewer";
import { PDFDocumentLoadingTask } from "pdfjs-dist";
import { useUISettings } from "../../annotator/hooks/useUISettings";
import useWindowDimensions from "../../hooks/WindowDimensionHook";
import { PDFPageInfo } from "../../annotator/types/pdf";
import { Token, ViewState, PermissionTypes } from "../../types";
import { toast } from "react-toastify";
import {
  useDocText,
  useDocumentPermissions,
  useDocumentState,
  useDocumentType,
  usePages,
  usePageTokenTextMaps,
  usePdfDoc,
  useSearchText,
  useTextSearchState,
} from "../../annotator/context/DocumentAtom";
import { createTokenStringSearch } from "../../annotator/utils";
import {
  convertToDocTypeAnnotations,
  convertToServerAnnotation,
  getPermissions,
} from "../../../utils/transform";
import {
  PdfAnnotations,
  RelationGroup,
} from "../../annotator/types/annotations";
import {
  pdfAnnotationsAtom,
  structuralAnnotationsAtom,
} from "../../annotator/context/AnnotationAtoms";
import {
  CorpusState,
  useCorpusState,
} from "../../annotator/context/CorpusAtom";
import { useAtom } from "jotai";
import { useInitialAnnotations } from "../../annotator/hooks/AnnotationHooks";
import { EnhancedLabelSelector } from "../../annotator/labels/EnhancedLabelSelector";
import { PDF } from "../../annotator/renderers/pdf/PDF";
import TxtAnnotatorWrapper from "../../annotator/components/wrappers/TxtAnnotatorWrapper";
import {
  useAnnotationControls,
  selectedRelationsAtom,
} from "../../annotator/context/UISettingsAtom";
import { useNavigate, useLocation } from "react-router-dom";
import {
  clearAnnotationSelection,
  updateAnnotationSelectionParams,
} from "../../../utils/navigationUtils";
import { routingLogger } from "../../../utils/routingLogger";

import {
  ContentArea,
  HeaderContainer,
  MainContentArea,
  MetadataRow,
  SlidingPanel,
  EmptyState,
  ResizeHandle,
  ChatIndicator,
  SidebarTabsContainer,
  SidebarTab,
  TabBadge,
  MobileTabBar,
  MobileTab,
} from "./StyledContainers";
import { NoteModal } from "./StickyNotes";

import { useTextSearch } from "../../annotator/hooks/useTextSearch";
import {
  useAnalysisManager,
  useAnalysisSelection,
} from "../../annotator/hooks/AnalysisHooks";

import { FullScreenModal } from "./LayoutComponents";
import { ChatTray } from "./right_tray/ChatTray";
import { SafeMarkdown } from "../markdown/SafeMarkdown";
import { useAnnotationSelection } from "../../annotator/context/UISettingsAtom";
import styled from "styled-components";
import { Icon } from "semantic-ui-react";
import { useChatSourceState } from "../../annotator/context/ChatSourceAtom";
import { useCreateAnnotation } from "../../annotator/hooks/AnnotationHooks";
import { useScrollContainerRef } from "../../annotator/context/DocumentAtom";
import { useChatPanelWidth } from "../../annotator/context/UISettingsAtom";
import { NoteEditor } from "./NoteEditor";
import { NewNoteModal } from "./NewNoteModal";
import { FloatingSummaryPreview } from "./floating_summary_preview/FloatingSummaryPreview";
import { ZoomControls } from "./ZoomControls";

import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.mjs?url";
import {
  openedDocument,
  selectedAnnotationIds,
  selectedAnalysesIds,
  showStructuralAnnotations,
  showSelectedAnnotationOnly,
  showAnnotationBoundingBoxes,
  selectedThreadId,
} from "../../../graphql/cache";
import { useAuthReady } from "../../../hooks/useAuthReady";
import { DocumentDiscussionsContent } from "../../discussions/DocumentDiscussionsContent";

// New imports for unified feed
import {
  UnifiedContentFeed,
  SidebarControlBar,
  ContentFilters,
  SortOption,
  SidebarViewMode,
} from "./unified_feed";
import { FloatingDocumentControls } from "./FloatingDocumentControls";
import { FloatingDocumentInput } from "./FloatingDocumentInput";
import { FloatingAnalysesPanel } from "./FloatingAnalysesPanel";
import { FloatingExtractsPanel } from "./FloatingExtractsPanel";
import UnifiedKnowledgeLayer from "./layers/UnifiedKnowledgeLayer";
import { AddToCorpusModal } from "../../modals/AddToCorpusModal";
import { FeatureUnavailable } from "../../common/FeatureUnavailable";
import { SingleDocumentExtractResults } from "../../annotator/sidebar/SingleDocumentExtractResults";

// Setting worker path to worker bundle.
GlobalWorkerOptions.workerSrc = workerSrc;

/* ------------------------------------------------------------- */
/* Styled components - defined outside component to avoid warnings */
/* ------------------------------------------------------------- */

const HeaderButtonGroup = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
`;

const HeaderButton = styled.button<{ $variant?: "primary" | "secondary" }>`
  height: 36px;
  padding: 0 ${(props) => (props.$variant === "primary" ? "16px" : "10px")};
  background: ${(props) =>
    props.$variant === "primary"
      ? "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
      : "rgba(255, 255, 255, 0.1)"};
  color: ${(props) => (props.$variant === "primary" ? "white" : "#64748b")};
  border: 1px solid
    ${(props) =>
      props.$variant === "primary"
        ? "rgba(102, 126, 234, 0.4)"
        : "rgba(148, 163, 184, 0.2)"};
  border-radius: 10px;
  font-size: ${(props) => (props.$variant === "primary" ? "13px" : "14px")};
  font-weight: ${(props) => (props.$variant === "primary" ? "600" : "500")};
  letter-spacing: ${(props) => (props.$variant === "primary" ? "0.3px" : "0")};
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: ${(props) => (props.$variant === "primary" ? "8px" : "0")};
  backdrop-filter: blur(12px);
  box-shadow: ${(props) =>
    props.$variant === "primary"
      ? "0 4px 16px rgba(102, 126, 234, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.15)"
      : "0 2px 4px rgba(0, 0, 0, 0.04)"};
  position: relative;
  overflow: hidden;

  &::before {
    content: "";
    position: absolute;
    inset: 0;
    background: ${(props) =>
      props.$variant === "primary"
        ? "linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 100%)"
        : "transparent"};
    opacity: 0;
    transition: opacity 0.25s ease;
  }

  &:hover {
    transform: translateY(-2px);
    box-shadow: ${(props) =>
      props.$variant === "primary"
        ? "0 8px 24px rgba(102, 126, 234, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.25)"
        : "0 4px 12px rgba(0, 0, 0, 0.08)"};
    border-color: ${(props) =>
      props.$variant === "primary"
        ? "rgba(102, 126, 234, 0.6)"
        : "rgba(148, 163, 184, 0.3)"};

    &::before {
      opacity: 1;
    }
  }

  &:active {
    transform: translateY(0);
    box-shadow: ${(props) =>
      props.$variant === "primary"
        ? "0 2px 8px rgba(102, 126, 234, 0.3), inset 0 2px 4px rgba(0, 0, 0, 0.1)"
        : "inset 0 1px 2px rgba(0, 0, 0, 0.08)"};
  }

  svg {
    width: ${(props) => (props.$variant === "primary" ? "18px" : "18px")};
    height: ${(props) => (props.$variant === "primary" ? "18px" : "18px")};
    stroke-width: 2.5;
  }
`;

const FloatingInputWrapper = styled.div<{ $panelOffset: number }>`
  position: absolute;
  bottom: 4rem; /* Increased from 2rem to give more space from bottom */
  left: 0;
  right: ${(props) => props.$panelOffset}px;
  display: flex;
  justify-content: center;
  pointer-events: none; /* allow clicks only on children */
  z-index: 850;

  @media (max-width: 768px) {
    /* On mobile, position below zoom controls with higher z-index to prevent covering */
    position: absolute;
    top: 80px; /* Below zoom controls */
    left: 1rem;
    right: auto; /* Don't constrain right side for collapsed state */
    bottom: auto;
    width: auto; /* Let child determine width */
    display: block;
    pointer-events: none;
    box-sizing: border-box;
    /* Fix Issue #1: Increase z-index above zoom controls (900) to prevent mobile tray from covering input */
    z-index: 950;
  }
`;

const ZoomIndicator = styled.div`
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 18px;
  font-weight: 600;
  z-index: 2000;
  pointer-events: none;
  transition: opacity 0.2s ease-in-out;
`;

const ContextBar = styled.div`
  background: linear-gradient(
    90deg,
    rgba(102, 126, 234, 0.95) 0%,
    rgba(118, 75, 162, 0.95) 100%
  );
  backdrop-filter: blur(10px);
  color: white;
  padding: 8px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
  animation: slideDown 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;

const ContextBarContent = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
`;

const ContextBarBadge = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.3px;
  flex-shrink: 0;

  svg,
  i {
    width: 16px;
    height: 16px;
    margin: 0 !important;
  }
`;

const ContextBarLabel = styled.div`
  font-size: 14px;
  font-weight: 500;
  opacity: 0.95;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ContextBarStats = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
  margin-right: 12px;
`;

const StatPill = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;

  svg,
  i {
    width: 14px;
    height: 14px;
    opacity: 0.9;
    margin: 0 !important;
  }
`;

const CloseButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 50%;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;

  &:hover {
    background: rgba(255, 255, 255, 0.25);
    border-color: rgba(255, 255, 255, 0.4);
    transform: scale(1.05);
  }

  &:active {
    transform: scale(0.95);
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const SidebarHeader = styled.div`
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

const SidebarHeaderContent = styled.div`
  flex: 1;
  min-width: 0;
`;

const SidebarHeaderTitle = styled.div`
  font-weight: 600;
  font-size: 1rem;
  color: #1e293b;
  max-height: 8.4rem; /* ~6 lines at 1.4 line-height */
  overflow-y: auto;
  line-height: 1.4;

  /* Pretty scrollbar */
  &::-webkit-scrollbar {
    width: 4px;
  }
  &::-webkit-scrollbar-track {
    background: transparent;
  }
  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 2px;
  }
  &::-webkit-scrollbar-thumb:hover {
    background: #94a3b8;
  }

  /* Clean markdown rendering */
  p {
    margin: 0;
    line-height: 1.4;
  }

  strong,
  b {
    font-weight: 700;
  }

  em,
  i {
    font-style: italic;
  }

  code {
    background: #e2e8f0;
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    font-size: 0.875rem;
    font-family: monospace;
  }

  /* Don't let markdown break the layout */
  ul,
  ol,
  h1,
  h2,
  h3,
  h4,
  h5,
  h6 {
    display: none;
  }
`;

const SidebarHeaderSubtitle = styled.div`
  font-size: 0.875rem;
  color: #64748b;
  margin-top: 0.125rem;
`;

const CompactAnnotationFeed = styled.div`
  height: 100%;
  overflow: hidden;

  /* Compact annotation cards for analysis view */
  .highlight-item {
    margin-bottom: 0.75rem !important;
    border-radius: 10px !important;
    background: white !important;
  }

  /* Clean up markdown in annotation cards */
  .annotation-content {
    p {
      margin: 0.25rem 0 !important;
      line-height: 1.5 !important;
    }

    ul,
    ol {
      margin: 0.5rem 0 !important;
      padding-left: 1.5rem !important;
    }

    li {
      margin: 0.25rem 0 !important;
    }

    h1,
    h2,
    h3,
    h4,
    h5,
    h6 {
      margin: 0.5rem 0 0.25rem 0 !important;
      font-size: 0.95rem !important;
      font-weight: 600 !important;
    }

    code {
      background: #f1f5f9 !important;
      padding: 0.125rem 0.375rem !important;
      border-radius: 3px !important;
      font-size: 0.875rem !important;
    }

    pre {
      background: #f8fafc !important;
      padding: 0.75rem !important;
      border-radius: 6px !important;
      overflow-x: auto !important;
      margin: 0.5rem 0 !important;
    }

    blockquote {
      border-left: 3px solid #e2e8f0 !important;
      padding-left: 1rem !important;
      margin: 0.5rem 0 !important;
      color: #64748b !important;
    }

    /* Compact spacing for analysis results */
    & > *:first-child {
      margin-top: 0 !important;
    }

    & > *:last-child {
      margin-bottom: 0 !important;
    }
  }

  /* Hide unnecessary metadata in compact view */
  .annotation-metadata {
    font-size: 0.8125rem !important;
    color: #94a3b8 !important;
  }

  /* Better page headers */
  .page-header {
    background: linear-gradient(to right, #fef3c7 0%, #fef9e7 100%) !important;
    border-left: 3px solid #f59e0b !important;
  }
`;

interface DocumentKnowledgeBaseProps {
  documentId: string;
  corpusId?: string; // Now optional
  /**
   * Optional list of annotation IDs that should be selected when the modal opens.
   * When provided the component will seed `selectedAnnotationsAtom`, triggering
   * the usual scroll-to-annotation behaviour in the PDF/TXT viewers.
   */
  initialAnnotationIds?: string[];
  /**
   * Optional close handler for programmatic modal usage.
   * If not provided, uses navigate(-1) to go back in browser history.
   * @deprecated Prefer routing-based navigation over programmatic modals
   */
  onClose?: () => void;
  /**
   * When true, disables all editing capabilities and shows only view-only features.
   */
  readOnly?: boolean;
  /**
   * Show information about corpus assignment state
   */
  showCorpusInfo?: boolean;
  /**
   * Optional success message to display after corpus assignment
   */
  showSuccessMessage?: string;
}

const DocumentKnowledgeBase: React.FC<DocumentKnowledgeBaseProps> = ({
  documentId,
  corpusId,
  initialAnnotationIds,
  onClose,
  readOnly = false,
  showCorpusInfo,
  showSuccessMessage,
}) => {
  routingLogger.debug("[DocumentKnowledgeBase] 🎬 Component render", {
    documentId,
    corpusId,
    hasOnClose: !!onClose,
    timestamp: Date.now(),
  });

  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  const { isFeatureAvailable, getFeatureStatus, hasCorpus } =
    useFeatureAvailability(corpusId);

  // Memoize UI settings config to prevent creating new object reference on every render
  const uiSettingsConfig = React.useMemo(() => ({ width }), [width]);
  const { setProgress, zoomLevel, setShiftDown, setZoomLevel } =
    useUISettings(uiSettingsConfig);

  const navigate = useNavigate();
  const location = useLocation();

  // Track component lifecycle
  useEffect(() => {
    routingLogger.debug("[DocumentKnowledgeBase] 🟢 Component MOUNTED", {
      documentId,
      corpusId,
      pathname: location.pathname,
      search: location.search,
    });

    return () => {
      routingLogger.debug("[DocumentKnowledgeBase] 🔴 Component UNMOUNTING", {
        documentId,
        corpusId,
        pathname: location.pathname,
        search: location.search,
      });
    };
  }, []); // Empty deps - only log on actual mount/unmount

  // Handle close: use provided onClose callback or fallback to /documents
  // Following routing mantra: route components should provide onClose to make navigation decisions
  // This component should NOT read openedCorpus() to decide navigation - that causes race conditions
  const handleClose = useCallback(() => {
    try {
      const timestamp = new Date().toISOString();
      routingLogger.debug(
        `🚪 [DocumentKnowledgeBase] ════════ handleClose START ════════`
      );
      routingLogger.debug("[DocumentKnowledgeBase] Timestamp:", timestamp);
      routingLogger.debug(
        "[DocumentKnowledgeBase] Call stack:",
        new Error().stack?.split("\n").slice(2, 8).join("\n")
      );
      routingLogger.debug("[DocumentKnowledgeBase] Current state:", {
        hasOnClose: !!onClose,
        documentId,
        corpusId,
        currentUrl: window.location.pathname + window.location.search,
      });

      if (onClose) {
        routingLogger.debug(
          "[DocumentKnowledgeBase] ✅ Decision: Calling provided onClose callback"
        );
        onClose();
      } else {
        console.warn(
          "[DocumentKnowledgeBase] ⚠️  Decision: No onClose callback - fallback to /documents"
        );
        console.warn(
          "Route components should pass explicit onClose callbacks to avoid race conditions."
        );
        navigate("/documents");
      }

      routingLogger.debug(
        "[DocumentKnowledgeBase] ════════ handleClose END ════════"
      );
    } catch (error) {
      console.error("[DocumentKnowledgeBase] ❌ ERROR in handleClose:", error);
      console.error("Stack trace:", error);
      // Fallback navigation on error
      navigate("/documents");
    }
  }, [onClose, navigate, documentId, corpusId]);

  // Validate documentId - must be non-empty
  if (!documentId || documentId === "") {
    console.error(
      "DocumentKnowledgeBase: Invalid documentId provided:",
      documentId
    );
    return (
      <Modal open onClose={handleClose}>
        <Modal.Content>
          <Message error>
            <Message.Header>Invalid Document</Message.Header>
            <p>Cannot load document: Invalid document ID</p>
          </Message>
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={handleClose}>Close</Button>
        </Modal.Actions>
      </Modal>
    );
  }

  // Chat panel width management
  const { mode, customWidth, setMode, setCustomWidth, minimize, restore } =
    useChatPanelWidth();

  // Calculate actual panel width based on mode
  const getPanelWidthPercentage = (): number => {
    let width: number;
    switch (mode) {
      case "quarter":
        width = 25;
        break;
      case "half":
        width = 50;
        break;
      case "full":
        width = 90;
        break;
      case "custom":
        width = customWidth || 50;
        break;
      default:
        width = 50;
    }
    routingLogger.debug(
      "Panel width calculation - mode:",
      mode,
      "width:",
      width
    );
    return width;
  };

  // Resize handle state
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragStartWidth, setDragStartWidth] = useState(0);
  const [isMinimized, setIsMinimized] = useState(false);
  const documentAreaRef = useRef<HTMLDivElement>(null);

  const [showGraph, setShowGraph] = useState(false);

  // This layer state still determines whether to show the knowledge base layout vs document layout
  const [activeLayer, setActiveLayer] = useState<"knowledge" | "document">(
    "document"
  );

  const [viewState, setViewState] = useState<ViewState>(ViewState.LOADING);
  const [showRightPanel, setShowRightPanel] = useState(false);
  const [autoZoomEnabled, setAutoZoomEnabled] = useState<boolean>(true);

  // Track base zoom level (when sidebar is closed) for proportional adjustment
  const baseZoomRef = useRef<number>(zoomLevel);
  const isAdjustingZoomRef = useRef<boolean>(false);
  const justToggledAutoZoomRef = useRef<boolean>(false);

  // Calculate floating controls offset and visibility - MEMOIZED to prevent new object on every render
  const floatingControlsState = React.useMemo(() => {
    if (isMobile || !showRightPanel || activeLayer !== "document") {
      return { offset: 0, visible: true };
    }

    const panelWidthPercent = getPanelWidthPercentage();
    const windowWidth = window.innerWidth;
    const panelWidthPx = (panelWidthPercent / 100) * windowWidth;
    const remainingSpacePercent = 100 - panelWidthPercent;
    const remainingSpacePx = windowWidth - panelWidthPx;

    // Hide controls if less than 10% viewport or less than 100px remaining
    const shouldHide = remainingSpacePercent < 10 || remainingSpacePx < 100;

    return {
      offset: shouldHide ? 0 : panelWidthPx,
      visible: !shouldHide,
    };
  }, [isMobile, showRightPanel, activeLayer, mode, customWidth, width]); // Dependencies: all values that affect calculation

  const { setDocumentType } = useDocumentType();
  const { setDocument } = useDocumentState();
  const { setDocText } = useDocText();
  const {
    pageTokenTextMaps: pageTextMaps,
    setPageTokenTextMaps: setPageTextMaps,
  } = usePageTokenTextMaps();
  const { setPages } = usePages();

  const [pdfAnnotations, setPdfAnnotations] = useAtom(pdfAnnotationsAtom);
  const [, setStructuralAnnotations] = useAtom(structuralAnnotationsAtom);

  const {
    setCorpus,
    canUpdateCorpus,
    myPermissions: corpusPermissions,
  } = useCorpusState();

  const { setInitialAnnotations, setInitialRelations } =
    useInitialAnnotations();
  const { searchText, setSearchText } = useSearchText();
  const { setPermissions, permissions } = useDocumentPermissions();
  const { setTextSearchState } = useTextSearchState();
  const { activeSpanLabel, setActiveSpanLabel } = useAnnotationControls();
  const { setChatSourceState } = useChatSourceState();
  const { setPdfDoc } = usePdfDoc();

  // Determine if user can edit based on permissions and corpus context
  const canEdit = React.useMemo(() => {
    // If explicitly marked as readOnly, respect that
    if (readOnly) {
      return false;
    }

    // If no corpus context, can't edit (annotations require corpus)
    if (!corpusId) {
      return false;
    }

    // Check corpus permissions first (these are more readily available)
    if (canUpdateCorpus) {
      return true;
    }

    // Fallback to document permissions
    return permissions.includes(PermissionTypes.CAN_UPDATE);
  }, [readOnly, corpusId, permissions, canUpdateCorpus, corpusPermissions]);

  // Call the hook ONCE here
  const originalCreateAnnotationHandler = useCreateAnnotation();

  // Conditional annotation handlers based on corpus availability
  const createAnnotationHandler = React.useCallback(
    async (annotation: any) => {
      if (!corpusId) {
        toast.info("Add document to corpus to create annotations");
        return;
      }
      return originalCreateAnnotationHandler(annotation);
    },
    [corpusId, originalCreateAnnotationHandler]
  );

  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [markdownError, setMarkdownError] = useState<boolean>(false);

  const { selectedAnalysis, selectedExtract } = useAnalysisSelection();
  const { selectedAnnotations, setSelectedAnnotations } =
    useAnnotationSelection();
  const [, setSelectedRelations] = useAtom(selectedRelationsAtom);

  const {
    dataCells,
    columns,
    analyses,
    extracts,
    onSelectAnalysis,
    onSelectExtract,
  } = useAnalysisManager();

  useTextSearch();

  // Initialize search state on mount only - DO NOT include setters in dependencies as they're unstable!
  useEffect(() => {
    // Batch updates to prevent multiple re-renders
    unstable_batchedUpdates(() => {
      setSearchText("");
      setTextSearchState({
        matches: [],
        selectedIndex: 0,
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty deps = run once on mount

  /**
   * REMOVED: useEffect that cleared analysis/extract selections on mount.
   *
   * This was causing deep link params to be stripped because:
   * 1. CentralRouteManager Phase 2 correctly sets reactive vars from URL
   * 2. DocumentKnowledgeBase mounts
   * 3. This effect called onSelectAnalysis(null) which now updates URL
   * 4. URL params get stripped!
   *
   * The routing system handles initialization:
   * - URL → CentralRouteManager Phase 2 → reactive vars
   * - Reactive vars → AnalysisHooks sync effect → Jotai atoms
   * - No manual clearing needed
   */

  /**
   * If analysis or annotation is selected, switch to document view.
   */
  useEffect(() => {
    if (selectedAnalysis || (selectedAnnotations?.length ?? 0) > 0) {
      setActiveLayer("document");
    }
  }, [selectedAnalysis, selectedAnnotations]);

  /**
   * Auto-switch to extract tab when extract is selected
   * Following routing principles: only READ selectedExtract from hook
   */
  useEffect(() => {
    if (selectedExtract) {
      // Batch updates to prevent cascade of re-renders (especially in mobile)
      unstable_batchedUpdates(() => {
        setActiveLayer("document");
        setShowRightPanel(true);
        setSidebarViewMode("extract");
        // Close floating extracts panel since results now show in sidebar
        setShowExtractsPanel(false);
      });
    }
  }, [selectedExtract]);

  /**
   * Auto-switch to analysis tab when analysis is selected
   * Following routing principles: only READ selectedAnalysis from hook
   */
  useEffect(() => {
    if (selectedAnalysis) {
      // Batch updates to prevent cascade of re-renders (especially in mobile)
      unstable_batchedUpdates(() => {
        setActiveLayer("document");
        setShowRightPanel(true);
        setSidebarViewMode("analysis");
        // Close floating analyses panel since results now show in sidebar
        setShowAnalysesPanel(false);
      });
    }
  }, [selectedAnalysis]);

  /**
   * processAnnotationsData
   *
   * Processes annotation data for the current document, updating state atoms
   * and corpus label sets. Accepts GetDocumentKnowledgeAndAnnotationsOutput,
   * which is what's returned from
   * the GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS query.
   *
   * @param data - The query result containing document + corpus info
   */
  const processAnnotationsData = (
    data: GetDocumentKnowledgeAndAnnotationsOutput
  ) => {
    if (data?.document) {
      // Backend now filters out analysis annotations when analysisId is not provided
      const processedAnnotations =
        data.document.allAnnotations?.map((annotation) =>
          convertToServerAnnotation(annotation)
        ) ?? [];

      const structuralAnnotations =
        data.document.allStructuralAnnotations?.map((annotation) =>
          convertToServerAnnotation(annotation)
        ) ?? [];

      const processedDocTypeAnnotations = convertToDocTypeAnnotations(
        data.document.allAnnotations?.filter(
          (ann) => ann.annotationLabel.labelType === LabelType.DocTypeLabel
        ) ?? []
      );

      // Update pdfAnnotations atom with ONLY non-structural annotations
      // Structural annotations are handled separately via structuralAnnotationsAtom
      setPdfAnnotations(
        (prev) =>
          new PdfAnnotations(
            processedAnnotations, // Don't include structural here
            prev.relations,
            processedDocTypeAnnotations,
            true
          )
      );

      // **Store the initial annotations**
      setInitialAnnotations(processedAnnotations);

      // Process structural annotations
      if (data.document.allStructuralAnnotations) {
        const structuralAnns = data.document.allStructuralAnnotations.map(
          (ann) => convertToServerAnnotation(ann)
        );
        setStructuralAnnotations(structuralAnns);
      }

      // Process relationships - backend now filters out analysis relationships
      const processedRelationships = data.document.allRelationships?.map(
        (rel) =>
          new RelationGroup(
            rel.sourceAnnotations.edges
              .map((edge) => edge?.node?.id)
              .filter((id): id is string => id !== undefined),
            rel.targetAnnotations.edges
              .map((edge) => edge?.node?.id)
              .filter((id): id is string => id !== undefined),
            rel.relationshipLabel,
            rel.id,
            rel.structural
          )
      );

      // Store the initial relations
      setInitialRelations(processedRelationships || []);

      setPdfAnnotations(
        (prev) =>
          new PdfAnnotations(
            prev.annotations,
            processedRelationships || [],
            prev.docTypes,
            true
          )
      );

      // Prepare the update payload for the corpus state atom
      let corpusUpdatePayload: Partial<CorpusState> = {}; // Initialize as Partial<CorpusState>

      // Process corpus permissions if available
      if (data.corpus?.myPermissions) {
        corpusUpdatePayload.myPermissions = getPermissions(
          data.corpus.myPermissions
        );
      }

      // Process labels if labelSet is available
      if (data.corpus?.labelSet) {
        const allLabels = data.corpus.labelSet.allAnnotationLabels ?? [];
        // Filter labels by type
        corpusUpdatePayload.spanLabels = allLabels.filter(
          (label) => label.labelType === LabelType.SpanLabel
        );
        corpusUpdatePayload.humanSpanLabels = corpusUpdatePayload.spanLabels; // Assuming they are the same initially
        corpusUpdatePayload.relationLabels = allLabels.filter(
          (label) => label.labelType === LabelType.RelationshipLabel
        );
        corpusUpdatePayload.docTypeLabels = allLabels.filter(
          (label) => label.labelType === LabelType.DocTypeLabel
        );
        corpusUpdatePayload.humanTokenLabels = allLabels.filter(
          (label) => label.labelType === LabelType.TokenLabel
        );
      }

      // *** ADD THE ACTUAL CORPUS OBJECT TO THE PAYLOAD ***
      if (data.corpus) {
        // Don't transform permissions here - let consuming components handle it
        corpusUpdatePayload.selectedCorpus = data.corpus as CorpusType; // Pass raw corpus
      }

      // Update corpus state using the constructed payload
      if (Object.keys(corpusUpdatePayload).length > 0) {
        setCorpus(corpusUpdatePayload); // Pass the complete payload
      }

      // Note: openedDocument and openedCorpus are managed by CentralRouteManager
      // Components should only READ these reactive vars, not SET them
      setPermissions(getPermissions(data.document.myPermissions));
    }
  };

  // We'll store the measured containerWidth here
  const [containerWidth, setContainerWidth] = useState<number | null>(null);

  /**
   * 1. store container width (existing behaviour)
   * 2. publish the same element to scrollContainerRefAtom
   */
  const { setScrollContainerRef } = useScrollContainerRef();
  const pdfContainerRef = useRef<HTMLDivElement | null>(null);

  const containerRefCallback = useCallback(
    (node: HTMLDivElement | null) => {
      pdfContainerRef.current = node;

      if (node) {
        // ① width for initial zoom calc
        setContainerWidth(node.getBoundingClientRect().width);
        // ② virtual-window needs this ref
        setScrollContainerRef(pdfContainerRef);
      } else {
        setScrollContainerRef(null);
      }
    },
    [setContainerWidth, setScrollContainerRef]
  );

  // Watch for width changes when sidebar opens/closes
  useEffect(() => {
    const node = pdfContainerRef.current;
    if (!node) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const newWidth = entry.contentRect.width;
        setContainerWidth(newWidth);
      }
    });

    resizeObserver.observe(node);
    return () => resizeObserver.disconnect();
  }, [setContainerWidth]);

  /* clear on unmount so stale refs are never used */
  useEffect(() => () => setScrollContainerRef(null), [setScrollContainerRef]);

  // Track previous auto-zoom state to detect when user toggles it
  const prevAutoZoomEnabledRef = useRef<boolean>(autoZoomEnabled);

  // When auto-zoom is toggled ON, capture current zoom as the new base
  useEffect(() => {
    const wasDisabled = !prevAutoZoomEnabledRef.current;
    const isNowEnabled = autoZoomEnabled;

    if (wasDisabled && isNowEnabled) {
      // User just toggled auto-zoom from OFF to ON
      // Capture current zoom as the new base, don't adjust yet
      baseZoomRef.current = zoomLevel;
      justToggledAutoZoomRef.current = true;
      routingLogger.debug(
        "Auto-zoom toggled ON - setting base zoom to current:",
        zoomLevel
      );
    }

    prevAutoZoomEnabledRef.current = autoZoomEnabled;
  }, [autoZoomEnabled, zoomLevel]);

  // Automatically adjust zoom level when sidebar opens/closes to maintain proportional document width
  useEffect(() => {
    // Skip if auto-zoom is disabled
    if (!autoZoomEnabled) {
      return;
    }

    if (isMobile || activeLayer !== "document") {
      return;
    }

    // If user just toggled auto-zoom ON, skip this adjustment cycle
    if (justToggledAutoZoomRef.current) {
      justToggledAutoZoomRef.current = false;
      return;
    }

    // If we're currently auto-adjusting, skip to prevent loops
    if (isAdjustingZoomRef.current) {
      return;
    }

    const panelWidth = getPanelWidthPercentage();

    if (showRightPanel) {
      // Sidebar just opened or resized
      // If we don't have a base zoom yet, store current zoom
      if (baseZoomRef.current === zoomLevel || !baseZoomRef.current) {
        baseZoomRef.current = zoomLevel;
      }

      // Calculate adjusted zoom: reduce proportionally to viewport shrinkage
      const viewportReduction = (100 - panelWidth) / 100;
      const adjustedZoom = baseZoomRef.current * viewportReduction;

      // Clamp to valid zoom range
      const clampedZoom = Math.max(0.5, Math.min(4, adjustedZoom));

      // Only update if there's a meaningful difference
      if (Math.abs(zoomLevel - clampedZoom) > 0.01) {
        isAdjustingZoomRef.current = true;
        setZoomLevel(clampedZoom);
        // Reset flag after state update completes
        setTimeout(() => {
          isAdjustingZoomRef.current = false;
        }, 0);
      }
    } else {
      // Sidebar closed - restore base zoom
      if (
        baseZoomRef.current &&
        Math.abs(zoomLevel - baseZoomRef.current) > 0.01
      ) {
        isAdjustingZoomRef.current = true;
        setZoomLevel(baseZoomRef.current);
        // Reset flag after state update completes
        setTimeout(() => {
          isAdjustingZoomRef.current = false;
        }, 0);
      }
    }
  }, [
    autoZoomEnabled,
    showRightPanel,
    mode,
    customWidth,
    isMobile,
    activeLayer,
    // NOTE: Do NOT include zoomLevel here - it causes auto-zoom to override manual zoom changes
    setZoomLevel,
  ]);

  // When user manually zooms while sidebar is open, update base zoom for proper restoration
  useEffect(() => {
    // Only track manual zoom changes if auto-zoom is enabled
    if (!autoZoomEnabled) {
      return;
    }

    if (
      !isMobile &&
      showRightPanel &&
      activeLayer === "document" &&
      !isAdjustingZoomRef.current
    ) {
      // User manually changed zoom while sidebar is open
      // Back-calculate what the base zoom should be
      const panelWidth = getPanelWidthPercentage();
      const viewportReduction = (100 - panelWidth) / 100;
      const backCalculatedBase = zoomLevel / viewportReduction;

      // Update base zoom so when sidebar closes, it restores to the right level
      baseZoomRef.current = Math.max(0.5, Math.min(4, backCalculatedBase));
    } else if (!showRightPanel && !isAdjustingZoomRef.current) {
      // Sidebar is closed, keep baseZoom in sync with current zoom
      baseZoomRef.current = zoomLevel;
    }
  }, [
    autoZoomEnabled,
    zoomLevel,
    showRightPanel,
    isMobile,
    activeLayer,
    mode,
    customWidth,
  ]);

  const handleKeyUpPress = useCallback(
    (event: { keyCode: any }) => {
      const { keyCode } = event;
      if (keyCode === 16) {
        setShiftDown(false);
      }
    },
    [setShiftDown]
  );

  const handleKeyDownPress = useCallback(
    (event: { keyCode: any }) => {
      const { keyCode } = event;
      if (keyCode === 16) {
        setShiftDown(true);
      }
    },
    [setShiftDown]
  );

  // Show zoom indicator feedback
  const showZoomFeedback = useCallback(() => {
    setShowZoomIndicator(true);

    // Clear existing timer
    if (zoomIndicatorTimer.current) {
      clearTimeout(zoomIndicatorTimer.current);
    }

    // Hide after 1.5 seconds
    zoomIndicatorTimer.current = setTimeout(() => {
      setShowZoomIndicator(false);
    }, 1500);
  }, []);

  // Browser zoom event handlers
  const handleWheelZoom = useCallback(
    (event: WheelEvent) => {
      // Only handle if in document layer and Ctrl/Cmd is pressed
      if (activeLayer !== "document" || (!event.ctrlKey && !event.metaKey)) {
        return;
      }

      // Prevent default browser zoom
      event.preventDefault();

      // Calculate zoom delta (normalize across browsers)
      const delta = event.deltaY > 0 ? -0.1 : 0.1;
      const newZoom = Math.max(0.5, Math.min(4, zoomLevel + delta));

      setZoomLevel(newZoom);
      showZoomFeedback();
    },
    [activeLayer, zoomLevel, setZoomLevel, showZoomFeedback]
  );

  const handleKeyboardZoom = useCallback(
    (event: KeyboardEvent) => {
      // Only handle if in document layer
      if (activeLayer !== "document") return;

      // Check for Ctrl/Cmd modifier
      if (!event.ctrlKey && !event.metaKey) return;

      let handled = false;

      switch (event.key) {
        case "+":
        case "=": // Handle both + and = (same key without shift)
          event.preventDefault();
          setZoomLevel(Math.min(zoomLevel + 0.1, 4));
          handled = true;
          break;
        case "-":
        case "_": // Handle both - and _ (same key without shift)
          event.preventDefault();
          setZoomLevel(Math.max(zoomLevel - 0.1, 0.5));
          handled = true;
          break;
        case "0":
          event.preventDefault();
          setZoomLevel(1); // Reset to 100%
          handled = true;
          break;
      }

      if (handled) {
        showZoomFeedback();
      }
    },
    [activeLayer, zoomLevel, setZoomLevel, showZoomFeedback]
  );

  // Pinch zoom state for mobile
  const [isPinching, setIsPinching] = useState(false);
  const [initialPinchDistance, setInitialPinchDistance] = useState<
    number | null
  >(null);
  const [lastPinchZoom, setLastPinchZoom] = useState<number | null>(null);

  // Helper function to calculate distance between two touch points
  const getTouchDistance = (touches: TouchList): number => {
    if (touches.length < 2) return 0;
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  };

  // Handle touch start for pinch zoom
  const handleTouchStart = useCallback(
    (event: TouchEvent) => {
      // Only handle if in document layer and using two fingers
      if (activeLayer !== "document" || event.touches.length !== 2) {
        return;
      }

      // Initialize pinch zoom
      const distance = getTouchDistance(event.touches);
      setIsPinching(true);
      setInitialPinchDistance(distance);
      setLastPinchZoom(zoomLevel);

      // Prevent default to avoid scrolling
      event.preventDefault();
    },
    [activeLayer, zoomLevel]
  );

  // Handle touch move for pinch zoom
  const handleTouchMove = useCallback(
    (event: TouchEvent) => {
      // Only handle if we're pinching with two fingers
      if (
        !isPinching ||
        event.touches.length !== 2 ||
        !initialPinchDistance ||
        lastPinchZoom === null
      ) {
        return;
      }

      // Calculate new zoom based on pinch distance
      const currentDistance = getTouchDistance(event.touches);
      const scale = currentDistance / initialPinchDistance;

      // Apply zoom with limits
      const newZoom = Math.max(0.5, Math.min(4, lastPinchZoom * scale));
      setZoomLevel(newZoom);

      // Show zoom feedback
      showZoomFeedback();

      // Prevent default to avoid scrolling
      event.preventDefault();
    },
    [
      isPinching,
      initialPinchDistance,
      lastPinchZoom,
      setZoomLevel,
      showZoomFeedback,
    ]
  );

  // Handle touch end for pinch zoom
  const handleTouchEnd = useCallback((event: TouchEvent) => {
    // Reset pinch state when touches end
    if (event.touches.length < 2) {
      setIsPinching(false);
      setInitialPinchDistance(null);
      setLastPinchZoom(null);
    }
  }, []);

  // Fetch document data - either with corpus context or without
  const authReady = useAuthReady();

  // Query for document with corpus
  const {
    data: corpusData,
    loading: corpusLoading,
    error: corpusError,
    refetch: refetchWithCorpus,
  } = useQuery<
    GetDocumentKnowledgeAndAnnotationsOutput,
    GetDocumentKnowledgeAndAnnotationsInput
  >(GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS, {
    skip: !authReady || !documentId || !corpusId,
    variables: {
      documentId,
      corpusId: corpusId!,
      analysisId: undefined,
    },
    onCompleted: (data) => {
      if (!data?.document) {
        console.error("onCompleted: No document data received.");
        setViewState(ViewState.ERROR);
        toast.error("Failed to load document details.");
        return;
      }

      // Batch initial state updates to prevent cascading re-renders
      routingLogger.debug("[onCompleted] 🔄 Batching initial state updates");
      unstable_batchedUpdates(() => {
        setDocumentType(data.document.fileType ?? "");
        let processedDocData = {
          ...data.document,
          // Keep permissions as raw strings for consistency
          myPermissions: data.document.myPermissions ?? [],
        };
        setDocument(processedDocData as any);
        setPermissions(getPermissions(data.document.myPermissions));
        processAnnotationsData(data);
      });

      if (
        data.document.fileType === "application/pdf" &&
        data.document.pdfFile
      ) {
        routingLogger.debug("\n=== DOCUMENT LOAD START ===");
        routingLogger.debug("Type: PDF");
        routingLogger.debug("Document ID:", data.document.id);
        routingLogger.debug("Hash:", data.document.pdfFileHash || "no hash");
        setViewState(ViewState.LOADING); // Set loading state

        const pawlsPath = data.document.pawlsParseFile || "";
        const pdfHash = data.document.pdfFileHash || "";
        const docId = data.document.id;

        // First get the cached or fresh PDF URL
        getCachedPDFUrl(data.document.pdfFile, docId, pdfHash)
          .then((pdfUrl) => {
            const loadingTask: PDFDocumentLoadingTask = getDocument(pdfUrl);
            loadingTask.onProgress = (p: { loaded: number; total: number }) => {
              setProgress(Math.round((p.loaded / p.total) * 100));
            };

            return Promise.all([
              loadingTask.promise,
              getPawlsLayer(pawlsPath, docId), // Fetches PAWLS via REST with caching
            ]);
          })
          .then(([pdfDocProxy, pawlsData]) => {
            // --- DETAILED LOGGING FOR PAWLS DATA ---
            if (!pawlsData) {
              console.error(
                "onCompleted: PAWLS data received is null or undefined!"
              );
            }
            // --- END DETAILED LOGGING ---

            if (!pdfDocProxy) {
              throw new Error("PDF document proxy is null or undefined.");
            }
            setPdfDoc(pdfDocProxy);

            const loadPagesPromises: Promise<PDFPageInfo>[] = [];
            for (let i = 1; i <= pdfDocProxy.numPages; i++) {
              const pageNum = i; // Capture page number for logging
              loadPagesPromises.push(
                pdfDocProxy.getPage(pageNum).then((p) => {
                  let pageTokens: Token[] = [];
                  const pageIndex = p.pageNumber - 1;

                  if (
                    !pawlsData ||
                    !Array.isArray(pawlsData) ||
                    pageIndex >= pawlsData.length
                  ) {
                    console.warn(
                      `Page ${pageNum}: PAWLS data index out of bounds. Index: ${pageIndex}, Length: ${pawlsData.length}`
                    );
                    pageTokens = [];
                  } else {
                    const pageData = pawlsData[pageIndex];

                    if (!pageData) {
                      pageTokens = [];
                    } else if (typeof pageData.tokens === "undefined") {
                      pageTokens = [];
                    } else if (!Array.isArray(pageData.tokens)) {
                      console.error(
                        `Page ${pageNum}: CRITICAL - pageData.tokens is not an array at index ${pageIndex}! Type: ${typeof pageData.tokens}`
                      );
                      pageTokens = [];
                    } else {
                      pageTokens = pageData.tokens;
                    }
                  }
                  return new PDFPageInfo(p, pageTokens, zoomLevel);
                }) as unknown as Promise<PDFPageInfo>
              );
            }
            return Promise.all(loadPagesPromises);
          })
          .then((loadedPages) => {
            // Batch PDF completion state updates to prevent cascading re-renders
            routingLogger.debug(
              "[PDF Load] 🔄 Batching PDF completion state updates"
            );
            unstable_batchedUpdates(() => {
              setPages(loadedPages);
              const { doc_text, string_index_token_map } =
                createTokenStringSearch(loadedPages);
              setPageTextMaps({
                ...string_index_token_map,
                ...pageTextMaps,
              });
              setDocText(doc_text);
              setViewState(ViewState.LOADED); // Set loaded state only after everything is done
            });
            routingLogger.debug("=== DOCUMENT LOAD COMPLETE ===");
          })
          .catch((err) => {
            // Log the specific error causing the catch
            console.error("Error during PDF/PAWLS loading Promise.all:", err);
            routingLogger.debug("=== DOCUMENT LOAD FAILED ===");
            setViewState(ViewState.ERROR);
            toast.error(
              `Error loading PDF details: ${
                err instanceof Error ? err.message : String(err)
              }`
            );
          });
      } else if (
        (data.document.fileType === "application/txt" ||
          data.document.fileType === "text/plain") &&
        data.document.txtExtractFile
      ) {
        routingLogger.debug("\n=== DOCUMENT LOAD START ===");
        routingLogger.debug("Type: TEXT");
        routingLogger.debug("Document ID:", data.document.id);
        routingLogger.debug("Hash:", data.document.pdfFileHash || "no hash");
        routingLogger.debug("File URL:", data.document.txtExtractFile);
        setViewState(ViewState.LOADING); // Set loading state
        const docId = data.document.id;
        const textHash = data.document.pdfFileHash; // Can use same hash field for text files
        getDocumentRawText(
          data.document.txtExtractFile,
          docId,
          textHash ?? undefined
        )
          .then((txt) => {
            // Batch text file completion state updates
            routingLogger.debug(
              "[Text Load] 🔄 Batching text completion state updates"
            );
            unstable_batchedUpdates(() => {
              setDocText(txt);
              setViewState(ViewState.LOADED);
            });
            routingLogger.debug("=== DOCUMENT LOAD COMPLETE ===");
          })
          .catch((err) => {
            setViewState(ViewState.ERROR);
            routingLogger.debug("=== DOCUMENT LOAD FAILED ===");
            toast.error(
              `Error loading text content: ${
                err instanceof Error ? err.message : String(err)
              }`
            );
          });
      } else {
        console.warn(
          "onCompleted: Unsupported file type or missing file path.",
          data.document.fileType
        );
        setViewState(ViewState.ERROR); // Treat unsupported as error
      }
    },
    onError: (error) => {
      // If the backend hasn\'t yet indexed/authorised this doc the first
      // request may come back with "Document matching query does not exist.".
      // We silently ignore this **once** and keep the loader visible; a
      // follow-up refetch (triggered when Apollo receives the updated auth
      // headers) will succeed and onCompleted will take over.
      const benign404 =
        error?.graphQLErrors?.length === 1 &&
        error.graphQLErrors[0].message.includes(
          "Document matching query does not exist"
        );

      if (benign404) {
        console.warn("Initial 404 for document – will retry automatically");
        return; // keep LOADING state
      }

      // Otherwise treat as real error
      console.error("GraphQL Query Error fetching document data:", error);
      toast.error(`Failed to load document details: ${error.message}`);
      setViewState(ViewState.ERROR);
    },
    fetchPolicy: "network-only",
    nextFetchPolicy: "no-cache",
  });

  // Query for document with structure but without corpus
  routingLogger.debug(
    "[GraphQL] 🔵 DocumentKnowledgeBase: GET_DOCUMENT_WITH_STRUCTURE query state",
    {
      skip: !authReady || !documentId || Boolean(corpusId),
      authReady,
      documentId,
      corpusId,
    }
  );

  const {
    data: documentOnlyData,
    loading: documentLoading,
    error: documentError,
    refetch: refetchDocumentOnly,
  } = useQuery<GetDocumentWithStructureOutput, GetDocumentWithStructureInput>(
    GET_DOCUMENT_WITH_STRUCTURE,
    {
      skip: !authReady || !documentId || Boolean(corpusId),
      variables: {
        documentId,
      },
      onCompleted: (data) => {
        routingLogger.debug(
          "[GraphQL] ✅ DocumentKnowledgeBase: GET_DOCUMENT_WITH_STRUCTURE completed",
          {
            documentId,
            hasDocument: !!data?.document,
            hasStructuralAnnotations:
              data?.document?.allStructuralAnnotations?.length ?? 0,
          }
        );
        if (!data?.document) {
          console.error("onCompleted: No document data received.");
          setViewState(ViewState.ERROR);
          toast.error("Failed to load document details.");
          return;
        }

        // Batch initial state updates to prevent cascading re-renders
        routingLogger.debug(
          "[onCompleted] 🔄 Batching initial state updates (document-only)"
        );
        unstable_batchedUpdates(() => {
          setDocumentType(data.document.fileType ?? "");
          let processedDocData = {
            ...data.document,
            // Keep permissions as raw strings for consistency
            myPermissions: data.document.myPermissions ?? [],
          };
          setDocument(processedDocData as any);
          setPermissions(getPermissions(data.document.myPermissions));
        });

        // Load PDF/TXT content
        if (
          data.document.fileType === "application/pdf" &&
          data.document.pdfFile
        ) {
          setViewState(ViewState.LOADING);
          const loadingTask: PDFDocumentLoadingTask = getDocument(
            data.document.pdfFile
          );
          loadingTask.onProgress = (p: { loaded: number; total: number }) => {
            setProgress(Math.round((p.loaded / p.total) * 100));
          };

          const pawlsPath = data.document.pawlsParseFile || "";

          Promise.all([loadingTask.promise, getPawlsLayer(pawlsPath)])
            .then(([pdfDocProxy, pawlsData]) => {
              if (!pawlsData) {
                console.error(
                  "onCompleted: PAWLS data received is null or undefined!"
                );
              }

              if (!pdfDocProxy) {
                throw new Error("PDF document proxy is null or undefined.");
              }
              setPdfDoc(pdfDocProxy);

              const loadPagesPromises: Promise<PDFPageInfo>[] = [];
              for (let i = 1; i <= pdfDocProxy.numPages; i++) {
                const pageNum = i;
                loadPagesPromises.push(
                  pdfDocProxy.getPage(pageNum).then((p) => {
                    let pageTokens: Token[] = [];
                    const pageIndex = p.pageNumber - 1;

                    if (
                      !pawlsData ||
                      !Array.isArray(pawlsData) ||
                      pageIndex >= pawlsData.length
                    ) {
                      console.warn(
                        `Page ${pageNum}: PAWLS data index out of bounds. Index: ${pageIndex}, Length: ${pawlsData.length}`
                      );
                      pageTokens = [];
                    } else {
                      const pageData = pawlsData[pageIndex];

                      if (!pageData) {
                        pageTokens = [];
                      } else if (typeof pageData.tokens === "undefined") {
                        pageTokens = [];
                      } else if (!Array.isArray(pageData.tokens)) {
                        console.error(
                          `Page ${pageNum}: CRITICAL - pageData.tokens is not an array at index ${pageIndex}! Type: ${typeof pageData.tokens}`
                        );
                        pageTokens = [];
                      } else {
                        pageTokens = pageData.tokens;
                      }
                    }
                    return new PDFPageInfo(p, pageTokens, zoomLevel);
                  }) as unknown as Promise<PDFPageInfo>
                );
              }
              return Promise.all(loadPagesPromises);
            })
            .then((loadedPages) => {
              // Batch PDF completion state updates (document-only)
              routingLogger.debug(
                "[PDF Load] 🔄 Batching PDF completion state updates (document-only)"
              );
              unstable_batchedUpdates(() => {
                setPages(loadedPages);
                const { doc_text, string_index_token_map } =
                  createTokenStringSearch(loadedPages);
                setPageTextMaps({
                  ...string_index_token_map,
                  ...pageTextMaps,
                });
                setDocText(doc_text);
                setViewState(ViewState.LOADED);
              });
            })
            .catch((err) => {
              console.error("Error during PDF/PAWLS loading Promise.all:", err);
              routingLogger.debug("=== DOCUMENT LOAD FAILED ===");
              setViewState(ViewState.ERROR);
              toast.error(
                `Error loading PDF details: ${
                  err instanceof Error ? err.message : String(err)
                }`
              );
            });
        } else if (
          (data.document.fileType === "application/txt" ||
            data.document.fileType === "text/plain") &&
          data.document.txtExtractFile
        ) {
          routingLogger.debug("\n=== DOCUMENT LOAD START ===");
          routingLogger.debug("Type: TEXT");
          routingLogger.debug("Document ID:", data.document.id);
          routingLogger.debug("Hash:", data.document.pdfFileHash || "no hash");
          routingLogger.debug("File URL:", data.document.txtExtractFile);
          setViewState(ViewState.LOADING);
          getDocumentRawText(data.document.txtExtractFile)
            .then((txt) => {
              // Batch text file completion state updates (document-only)
              routingLogger.debug(
                "[Text Load] 🔄 Batching text completion state updates (document-only)"
              );
              unstable_batchedUpdates(() => {
                setDocText(txt);
                setViewState(ViewState.LOADED);
              });
              routingLogger.debug("=== DOCUMENT LOAD COMPLETE ===");
            })
            .catch((err) => {
              setViewState(ViewState.ERROR);
              routingLogger.debug("=== DOCUMENT LOAD FAILED ===");
              toast.error(
                `Error loading text content: ${
                  err instanceof Error ? err.message : String(err)
                }`
              );
            });
        } else {
          console.warn(
            "onCompleted: Unsupported file type or missing file path.",
            data.document.fileType
          );
          setViewState(ViewState.ERROR);
        }

        // Note: openedDocument is managed by CentralRouteManager, not set here

        // Batch structural annotation updates (document-only)
        routingLogger.debug(
          "[onCompleted] 🔄 Batching structural annotation updates (document-only)"
        );
        unstable_batchedUpdates(() => {
          // Process structural annotations even without corpus
          if (data.document.allStructuralAnnotations) {
            const structuralAnns = data.document.allStructuralAnnotations.map(
              (ann) => convertToServerAnnotation(ann)
            );
            setStructuralAnnotations(structuralAnns);
          } else {
            setStructuralAnnotations([]);
          }

          // Process structural relationships even without corpus
          const processedRelationships = data.document.allRelationships?.map(
            (rel) =>
              new RelationGroup(
                rel.sourceAnnotations.edges
                  .map((edge) => edge?.node?.id)
                  .filter((id): id is string => id !== undefined),
                rel.targetAnnotations.edges
                  .map((edge) => edge?.node?.id)
                  .filter((id): id is string => id !== undefined),
                rel.relationshipLabel,
                rel.id,
                rel.structural
              )
          );

          // Set annotations with structural relationships (no regular annotations without corpus)
          setPdfAnnotations(
            new PdfAnnotations([], processedRelationships || [], [], true)
          );
        });
      },
      onError: (error) => {
        console.error("GraphQL Query Error fetching document data:", error);
        toast.error(`Failed to load document details: ${error.message}`);
        setViewState(ViewState.ERROR);
      },
      fetchPolicy: "network-only",
      nextFetchPolicy: "no-cache",
    }
  );

  // Lightweight query for fetching just annotations when switching analyses
  const { refetch: refetchAnnotationsOnly } = useQuery<
    GetDocumentAnnotationsOnlyOutput,
    GetDocumentAnnotationsOnlyInput
  >(GET_DOCUMENT_ANNOTATIONS_ONLY, {
    skip: true, // We'll manually trigger this
    fetchPolicy: "network-only",
  });

  // Query for thread count (for discussions tab badge)
  const { data: threadCountData } = useQuery<
    GetConversationsOutputs,
    GetConversationsInputs
  >(GET_CONVERSATIONS, {
    variables: {
      documentId: documentId,
      conversationType: "THREAD",
      limit: 1, // We only need the count
    },
    skip: !documentId,
    fetchPolicy: "cache-and-network",
  });

  const threadCount = threadCountData?.conversations?.totalCount ?? 0;

  // Combine query results
  const loading = corpusLoading || documentLoading;
  const queryError = corpusError || documentError;
  const combinedData = corpusId ? corpusData : documentOnlyData;
  const refetch = corpusId ? refetchWithCorpus : refetchDocumentOnly;

  // Process lightweight annotations data (used when switching analyses)
  const processAnnotationsOnlyData = (
    data: GetDocumentAnnotationsOnlyOutput
  ) => {
    if (data?.document) {
      const processedAnnotations =
        data.document.allAnnotations?.map((annotation) =>
          convertToServerAnnotation(annotation)
        ) ?? [];

      const structuralAnnotations =
        data.document.allStructuralAnnotations?.map((annotation) =>
          convertToServerAnnotation(annotation)
        ) ?? [];

      // Update pdfAnnotations atom with ONLY non-structural annotations
      // Structural annotations are handled separately via structuralAnnotationsAtom
      setPdfAnnotations(
        (prev) =>
          new PdfAnnotations(
            processedAnnotations, // Don't include structural here
            prev.relations, // Keep existing relations initially
            prev.docTypes, // Keep existing doc types
            true
          )
      );

      // Process structural annotations
      if (data.document.allStructuralAnnotations) {
        const structuralAnns = data.document.allStructuralAnnotations.map(
          (ann) => convertToServerAnnotation(ann)
        );
        setStructuralAnnotations(structuralAnns);
      }

      // Process relationships
      const processedRelationships = data.document.allRelationships?.map(
        (rel) =>
          new RelationGroup(
            rel.sourceAnnotations.edges
              .map((edge) => edge?.node?.id)
              .filter((id): id is string => id !== undefined),
            rel.targetAnnotations.edges
              .map((edge) => edge?.node?.id)
              .filter((id): id is string => id !== undefined),
            rel.relationshipLabel,
            rel.id,
            rel.structural
          )
      );

      setPdfAnnotations(
        (prev) =>
          new PdfAnnotations(
            prev.annotations,
            processedRelationships || [],
            prev.docTypes,
            true
          )
      );
    }
  };

  useEffect(() => {
    if (!loading && corpusId) {
      // Use lightweight query for annotation updates only
      refetchAnnotationsOnly({
        documentId,
        corpusId,
        analysisId: selectedAnalysis?.id || null,
      }).then(({ data }) => {
        if (data) {
          processAnnotationsOnlyData(data);
        }
      });
    }
  }, [selectedAnalysis, corpusId, loading, documentId]);

  useEffect(() => {
    if (!loading && corpusId) {
      // Use lightweight query for annotation updates only
      refetchAnnotationsOnly({
        documentId,
        corpusId,
        analysisId: selectedExtract?.id || null,
      }).then(({ data }) => {
        if (data) {
          processAnnotationsOnlyData(data);
        }
      });
    }
  }, [selectedExtract, corpusId, loading, documentId]);

  const metadata = combinedData?.document ?? {
    title: "Loading...",
    fileType: "",
    creator: { email: "" },
    created: new Date().toISOString(),
  };

  const notes = corpusId
    ? corpusData?.document?.allNotes ?? []
    : documentOnlyData?.document?.allNotes ?? [];
  const docRelationships = corpusId
    ? corpusData?.document?.allDocRelationships ?? []
    : [];

  // Resize handlers
  const handleResizeStart = (e: React.MouseEvent) => {
    // Don't start resize if clicking on a button
    const target = e.target as HTMLElement;
    if (target.closest("button")) {
      return;
    }

    setIsDragging(true);
    setDragStartX(e.clientX);
    setDragStartWidth(getPanelWidthPercentage());
    e.preventDefault();
  };

  const handleResizeMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging) return;

      const deltaX = dragStartX - e.clientX;
      const windowWidth = window.innerWidth;
      const deltaPercentage = (deltaX / windowWidth) * 100;
      const newWidth = Math.max(
        15,
        Math.min(95, dragStartWidth + deltaPercentage)
      );

      // Snap to preset widths if close
      const snapThreshold = 3;
      if (Math.abs(newWidth - 25) < snapThreshold) {
        setMode("quarter");
      } else if (Math.abs(newWidth - 50) < snapThreshold) {
        setMode("half");
      } else if (Math.abs(newWidth - 90) < snapThreshold) {
        setMode("full");
      } else {
        setCustomWidth(newWidth);
      }
    },
    [isDragging, dragStartX, dragStartWidth, setMode, setCustomWidth]
  );

  const handleResizeEnd = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Add resize event listeners
  useEffect(() => {
    if (isDragging) {
      document.addEventListener("mousemove", handleResizeMove);
      document.addEventListener("mouseup", handleResizeEnd);
      return () => {
        document.removeEventListener("mousemove", handleResizeMove);
        document.removeEventListener("mouseup", handleResizeEnd);
      };
    }
  }, [isDragging, handleResizeMove, handleResizeEnd]);

  // Auto-minimize logic
  const handleDocumentMouseEnter = useCallback(() => {
    // Desktop: no auto-collapse – user controls size fully.
    if (!isMobile) return;

    // Mobile / small-screen responsive mode: close the panel when the user
    // interacts with the document to maximise canvas real-estate.
    if (showRightPanel && !isDragging) {
      setShowRightPanel(false);
    }
  }, [showRightPanel, isDragging, isMobile, setShowRightPanel]);

  const handlePanelMouseEnter = useCallback(() => {
    // Restoration logic only relevant on desktop where we allow minimised width
    if (!isMobile && isMinimized) {
      restore();
      setIsMinimized(false);
    }
  }, [isMinimized, restore, isMobile]);

  // Reset minimized state when panel closes
  useEffect(() => {
    if (!showRightPanel) {
      setIsMinimized(false);
    }
  }, [showRightPanel]);

  // Load MD summary if available
  useEffect(() => {
    const fetchMarkdownContent = async () => {
      if (!combinedData?.document?.mdSummaryFile) {
        setMarkdownContent(null);
        return;
      }
      try {
        const response = await fetch(combinedData.document.mdSummaryFile);
        if (!response.ok) throw new Error("Failed to fetch markdown content");
        const text = await response.text();
        setMarkdownContent(text);
        setMarkdownError(false);
      } catch (error) {
        console.error("Error fetching markdown content:", error);
        setMarkdownContent(null);
        setMarkdownError(true);
      }
    };
    fetchMarkdownContent();
  }, [combinedData?.document?.mdSummaryFile]);

  // Browser zoom event handling
  useEffect(() => {
    // Only attach listeners if we're in document view
    if (activeLayer !== "document") return;

    // Add wheel listener with passive: false to allow preventDefault
    document.addEventListener("wheel", handleWheelZoom, { passive: false });
    document.addEventListener("keydown", handleKeyboardZoom);

    // Add touch listeners for pinch zoom with passive: false
    document.addEventListener("touchstart", handleTouchStart, {
      passive: false,
    });
    document.addEventListener("touchmove", handleTouchMove, { passive: false });
    document.addEventListener("touchend", handleTouchEnd, { passive: false });

    return () => {
      document.removeEventListener("wheel", handleWheelZoom);
      document.removeEventListener("keydown", handleKeyboardZoom);
      document.removeEventListener("touchstart", handleTouchStart);
      document.removeEventListener("touchmove", handleTouchMove);
      document.removeEventListener("touchend", handleTouchEnd);
    };
  }, [
    activeLayer,
    handleWheelZoom,
    handleKeyboardZoom,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  ]);

  const [selectedNote, setSelectedNote] = useState<(typeof notes)[0] | null>(
    null
  );
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [showNewNoteModal, setShowNewNoteModal] = useState(false);

  // Unified feed state
  const [sidebarViewMode, setSidebarViewMode] =
    useState<SidebarViewMode["mode"]>("chat");
  const [feedFilters, setFeedFilters] = useState<ContentFilters>({
    contentTypes: new Set(["note", "annotation", "relationship", "search"]),
    // Note: annotationFilters and relationshipFilters are now managed via atoms
    // in useAnnotationDisplay() for consistency across all components
  });
  const [feedSortBy, setFeedSortBy] = useState<SortOption>("page");

  // Add new state for floating panels
  const [showAnalysesPanel, setShowAnalysesPanel] = useState(false);
  const [showExtractsPanel, setShowExtractsPanel] = useState(false);
  const [showLoad, setShowLoad] = useState(false);
  const [pendingChatMessage, setPendingChatMessage] = useState<string>();
  const [showZoomIndicator, setShowZoomIndicator] = useState(false);
  const zoomIndicatorTimer = useRef<NodeJS.Timeout>();

  // Clear pending message after passing it to ChatTray
  useEffect(() => {
    if (pendingChatMessage) {
      // Clear after a short delay to ensure ChatTray has received it
      const timer = setTimeout(() => setPendingChatMessage(undefined), 100);
      return () => clearTimeout(timer);
    }
  }, [pendingChatMessage]);

  // Auto-open sidebar when ?thread= param detected
  const threadId = useReactiveVar(selectedThreadId);
  useEffect(() => {
    if (threadId && combinedData?.document) {
      unstable_batchedUpdates(() => {
        setShowRightPanel(true);
        setMode("half"); // 50% width to keep document visible
        setSidebarViewMode("discussions");
      });
    }
  }, [threadId, combinedData?.document]);

  const rightPanelContent = (() => {
    if (!showRightPanel) return null;

    // First, add the control bar for switching between chat and feed modes
    const controlBar = (
      <SidebarControlBar
        viewMode={sidebarViewMode}
        onViewModeChange={setSidebarViewMode}
        filters={feedFilters}
        onFiltersChange={setFeedFilters}
        sortBy={feedSortBy}
        onSortChange={setFeedSortBy}
        hasActiveSearch={!!searchText}
      />
    );

    // Handle extract mode - show extract results
    if (sidebarViewMode === "extract" && selectedExtract) {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "1rem 1.5rem",
              borderBottom: "1px solid #e2e8f0",
              background: "#f8fafc",
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
            }}
          >
            <Database size={20} style={{ color: "#8b5cf6" }} />
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontWeight: 600,
                  fontSize: "1rem",
                  color: "#1e293b",
                }}
              >
                {selectedExtract.name}
              </div>
              <div
                style={{
                  fontSize: "0.875rem",
                  color: "#64748b",
                }}
              >
                Data Extract Results
              </div>
            </div>
          </div>
          <div style={{ flex: 1, overflow: "hidden" }}>
            <SingleDocumentExtractResults
              datacells={dataCells}
              columns={columns}
            />
          </div>
        </div>
      );
    }

    // Handle analysis mode - show analysis annotations
    if (sidebarViewMode === "analysis" && selectedAnalysis) {
      const annotationCount = selectedAnalysis.annotations?.totalCount || 0;
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          <SidebarHeader>
            <BarChart3 size={20} style={{ color: "#f59e0b" }} />
            <SidebarHeaderContent>
              <SidebarHeaderTitle>
                <SafeMarkdown>
                  {selectedAnalysis.analyzer.description ||
                    selectedAnalysis.analyzer.id}
                </SafeMarkdown>
              </SidebarHeaderTitle>
              <SidebarHeaderSubtitle>
                {annotationCount} annotation
                {annotationCount !== 1 ? "s" : ""} • Analysis Results
              </SidebarHeaderSubtitle>
            </SidebarHeaderContent>
          </SidebarHeader>
          <CompactAnnotationFeed>
            <UnifiedContentFeed
              notes={notes}
              filters={{
                contentTypes: new Set(["annotation", "relationship"]),
              }}
              sortBy="page"
              isLoading={loading}
              readOnly={readOnly}
              documentId={documentId}
              onItemSelect={(item) => {
                // Annotations from analysis
                if (
                  item.type === "annotation" ||
                  item.type === "relationship"
                ) {
                  // Already in document view, annotations will scroll into view
                }
              }}
            />
          </CompactAnnotationFeed>
        </div>
      );
    }

    // Handle unified feed mode
    if (sidebarViewMode === "feed") {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          {controlBar}
          <UnifiedContentFeed
            notes={notes}
            filters={feedFilters}
            sortBy={feedSortBy}
            isLoading={loading}
            readOnly={readOnly}
            documentId={documentId}
            onItemSelect={(item) => {
              // Handle item selection based on type
              if (item.type === "annotation" || item.type === "relationship") {
                setActiveLayer("document");
              }
              // For notes, we could open the note modal
              if (item.type === "note" && "creator" in item.data) {
                setSelectedNote(item.data as (typeof notes)[0]);
              }
            }}
          />
        </div>
      );
    }

    // Handle discussions mode
    if (sidebarViewMode === "discussions") {
      return (
        <DocumentDiscussionsContent
          documentId={documentId}
          corpusId={corpusId}
        />
      );
    }

    // Handle chat mode (default behavior)
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        {controlBar}
        <ChatTray
          setShowLoad={setShowLoad}
          showLoad={showLoad}
          documentId={documentId}
          onMessageSelect={() => {
            setActiveLayer("document");
          }}
          corpusId={corpusId}
          initialMessage={pendingChatMessage}
          readOnly={readOnly}
        />
      </div>
    );
  })();

  // The main viewer content:
  let viewerContent: JSX.Element = <></>;
  if (metadata.fileType === "application/pdf") {
    viewerContent = (
      <PDFContainer id="pdf-container" ref={containerRefCallback}>
        {viewState === ViewState.LOADED ? (
          <PDF
            read_only={!canEdit}
            containerWidth={containerWidth}
            createAnnotationHandler={createAnnotationHandler}
          />
        ) : viewState === ViewState.LOADING ? (
          <Loader active inline="centered" content="Loading PDF..." />
        ) : (
          <EmptyState
            icon={<FileText size={40} />}
            title="Error Loading PDF"
            description="Could not load the PDF document."
          />
        )}
      </PDFContainer>
    );
  } else if (
    metadata.fileType === "application/txt" ||
    metadata.fileType === "text/plain"
  ) {
    viewerContent = (
      <PDFContainer id="pdf-container" ref={containerRefCallback}>
        {viewState === ViewState.LOADED ? (
          <TxtAnnotatorWrapper readOnly={!canEdit} allowInput={canEdit} />
        ) : viewState === ViewState.LOADING ? (
          <Loader active inline="centered" content="Loading Text..." />
        ) : (
          <EmptyState
            icon={<FileText size={40} />}
            title="Error Loading Text"
            description="Could not load the text file."
          />
        )}
      </PDFContainer>
    );
  } else {
    viewerContent = (
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
          <Loader active inline="centered" content="Loading Document..." />
        ) : (
          <EmptyState
            icon={<FileText size={40} />}
            title="Unsupported File"
            description="This document type can't be displayed."
          />
        )}
      </div>
    );
  }

  // Decide which content is in the center based on activeLayer
  const mainLayerContent =
    activeLayer === "knowledge" && corpusId ? (
      <UnifiedKnowledgeLayer
        documentId={documentId}
        corpusId={corpusId}
        metadata={metadata}
        parentLoading={loading}
        readOnly={readOnly}
      />
    ) : (
      <div
        id="document-layer"
        ref={documentAreaRef}
        onMouseEnter={handleDocumentMouseEnter}
        style={{
          position: "relative",
          width:
            !isMobile && showRightPanel
              ? `${100 - getPanelWidthPercentage()}%`
              : "100%",
          height: "100%",
          overflow: "hidden",
          transition: "width 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        {viewerContent}
      </div>
    );

  // Set initial state - ensure chat panel starts with proper width
  useEffect(() => {
    // Batch updates to prevent multiple re-renders
    unstable_batchedUpdates(() => {
      setShowRightPanel(false);
      setActiveLayer("document");
      // Force initial width to half
      if (mode !== "half") {
        setMode("half");
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty deps = run once on mount

  // Auto-show right panel with feed view when annotations are available
  // TEMPORARILY DISABLED: This auto-open behavior breaks tests that expect manual sidebar opening
  // useEffect(() => {
  //   if (
  //     corpusId &&
  //     combinedData?.document?.allAnnotations &&
  //     combinedData.document.allAnnotations.length > 0
  //   ) {
  //     setShowRightPanel(true);
  //     setSidebarViewMode("feed");
  //   }
  // }, [corpusId, combinedData?.document?.allAnnotations, setSidebarViewMode]);

  /* ------------------------------------------------------------------ */
  /* NOTE: Initial annotation seeding removed - incompatible with router-based state
   *
   * With router-based architecture, annotation selection is controlled by URL params.
   * For route-based usage: URL already contains ?ann=... via CentralRouteManager
   * For modal usage: This needs refactoring - calling setSelectedAnnotations navigates
   * the URL which is wrong for modals. Future fix should use a different approach for
   * modal contexts (e.g., navigate to URL when opening modal, restore on close).
   *
   * TODO: Implement proper modal annotation seeding that doesn't conflict with routing
   */

  /* ------------------------------------------------------------------ */
  /* NOTE: useUrlAnnotationSync removed - redundant with CentralRouteManager
   *
   * CentralRouteManager handles ALL URL ↔ State synchronization:
   * - Phase 2: URL query params → reactive vars (selectedAnnotationIds, etc.)
   * - Phase 4: Reactive vars → URL updates
   *
   * useUrlAnnotationSync created competing sync loops causing infinite navigation cycles.
   * See routing_system.md for architecture details.
   */

  /* ------------------------------------------------------ */
  /*  Cleanup on unmount                                    */
  /* ------------------------------------------------------ */
  useEffect(() => {
    return () => {
      // DO NOT call setSelectedAnnotations([]) - it navigates the URL during unmount!
      // CentralRouteManager handles clearing state when routes change.

      // Clear selected relationships (local Jotai atom, not URL-driven)
      setSelectedRelations([]);

      // Clean up zoom indicator timer
      if (zoomIndicatorTimer.current) {
        clearTimeout(zoomIndicatorTimer.current);
      }
    };
  }, [setSelectedRelations]);

  const [selectedSummaryContent, setSelectedSummaryContent] = useState<
    string | null
  >(null);

  const [showAddToCorpusModal, setShowAddToCorpusModal] = useState(false);

  // Handler to clear analysis/extract selection via URL update
  // Following routing system principles: Component → URL → CentralRouteManager → Reactive Var
  const handleClearAnalysisExtractSelection = useCallback(() => {
    updateAnnotationSelectionParams(location, navigate, {
      analysisIds: [],
      extractIds: [],
    });
    // CentralRouteManager Phase 2 will detect URL change and clear selectedAnalysesIds/selectedExtractIds

    // Close sidebar and switch back to feed view when clearing
    setShowRightPanel(false);
    setSidebarViewMode("feed");
  }, [location, navigate]);

  return (
    <FullScreenModal
      id="knowledge-base-modal"
      open={true}
      onClose={handleClose}
    >
      <HeaderContainer>
        <div
          style={{
            flex: 1,
            minWidth: 0,
            overflow: "hidden",
          }}
        >
          <Header
            as="h2"
            style={{
              margin: 0,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              maxWidth: "100%",
            }}
          >
            <span title={metadata.title || "Untitled Document"}>
              {metadata.title || "Untitled Document"}
            </span>
          </Header>
          <MetadataRow>
            <span>
              <FileType size={16} /> {metadata.fileType}
            </span>
            <span>
              <User size={16} /> {metadata.creator?.email}
            </span>
            <span>
              <Calendar size={16} /> Created:{" "}
              {new Date(metadata.created).toLocaleDateString()}
            </span>
          </MetadataRow>
        </div>

        <HeaderButtonGroup>
          {!hasCorpus && !readOnly && (
            <HeaderButton
              $variant="primary"
              onClick={() => setShowAddToCorpusModal(true)}
              title="Add this document to a corpus to unlock collaborative features"
              data-testid="add-to-corpus-button"
            >
              <Plus />
              Add to Corpus
            </HeaderButton>
          )}
          <HeaderButton
            onClick={(e) => {
              routingLogger.debug(
                `🖱️  [DocumentKnowledgeBase] ════════ BACK BUTTON CLICKED ════════`
              );
              routingLogger.debug(
                "[DocumentKnowledgeBase] Button click event:",
                {
                  timestamp: new Date().toISOString(),
                  button: e.button,
                  currentTarget: e.currentTarget,
                  target: e.target,
                  currentUrl: window.location.pathname + window.location.search,
                }
              );
              handleClose();
            }}
            title="Go back"
            data-testid="back-button"
          >
            <ArrowLeft />
          </HeaderButton>
        </HeaderButtonGroup>
      </HeaderContainer>

      {/* Context Bar - shows when analysis or extract is selected */}
      {(selectedAnalysis || selectedExtract) && (
        <ContextBar data-testid="context-bar">
          <ContextBarContent>
            <ContextBarBadge>
              {selectedAnalysis ? (
                <>
                  <Icon name="chart line" />
                  ANALYSIS
                </>
              ) : (
                <>
                  <Icon name="table" />
                  EXTRACT
                </>
              )}
            </ContextBarBadge>
            <ContextBarLabel>
              {selectedAnalysis
                ? selectedAnalysis.analyzer.description ||
                  selectedAnalysis.analyzer.id
                : selectedExtract?.fieldset?.name || "Data Extract"}
            </ContextBarLabel>
            <ContextBarStats>
              <StatPill title="Annotations visible">
                <Icon name="tag" />
                {pdfAnnotations?.annotations?.length || 0}
              </StatPill>
              {selectedAnalysis && (
                <StatPill title="Total analyses available">
                  <Icon name="chart line" />
                  {analyses.length}
                </StatPill>
              )}
              {selectedExtract && (
                <StatPill title="Total extracts available">
                  <Icon name="table" />
                  {extracts.length}
                </StatPill>
              )}
            </ContextBarStats>
          </ContextBarContent>
          <CloseButton
            onClick={handleClearAnalysisExtractSelection}
            data-testid="clear-analysis-extract-button"
            title="Clear filter"
          >
            <X />
          </CloseButton>
        </ContextBar>
      )}

      {/* Error message for GraphQL failures - show prominently and prevent other content */}
      {queryError ? (
        <ContentArea id="content-area">
          <div style={{ padding: "2rem", textAlign: "center" }}>
            <Message negative size="large">
              <Message.Header>Error loading document</Message.Header>
              <p>{queryError.message}</p>
            </Message>
          </div>
        </ContentArea>
      ) : (
        <>
          {/* Corpus info display */}
          {showCorpusInfo && corpusData?.corpus && (
            <Message info>
              <Message.Header>Corpus: {corpusData.corpus.title}</Message.Header>
              {corpusData.corpus.description && (
                <p>{corpusData.corpus.description}</p>
              )}
            </Message>
          )}

          {/* Success message if just added to corpus */}
          {showSuccessMessage && (
            <Message success onDismiss={() => {}}>
              <Message.Header>{showSuccessMessage}</Message.Header>
            </Message>
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
                  isMobile={isMobile}
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
                isMobile={isMobile}
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

              {/* Sidebar View Mode Tabs - always visible, outside panel when closed, on panel edge when open */}
              {!showRightPanel && (
                <SidebarTabsContainer $panelOpen={false}>
                  <SidebarTab
                    $isActive={sidebarViewMode === "chat"}
                    $panelOpen={false}
                    onClick={() => {
                      setSidebarViewMode("chat");
                      setShowRightPanel(true);
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    data-testid="view-mode-chat"
                  >
                    <MessageSquare />
                    <span className="tab-label">Chat</span>
                  </SidebarTab>
                  <SidebarTab
                    $isActive={sidebarViewMode === "feed"}
                    $panelOpen={false}
                    onClick={() => {
                      setSidebarViewMode("feed");
                      setShowRightPanel(true);
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    data-testid="view-mode-feed"
                  >
                    <Layers />
                    <span className="tab-label">Feed</span>
                  </SidebarTab>
                  {/* Extract tab - only visible when extract is selected */}
                  {selectedExtract && (
                    <SidebarTab
                      $isActive={sidebarViewMode === "extract"}
                      $panelOpen={false}
                      onClick={() => {
                        setSidebarViewMode("extract");
                        setShowRightPanel(true);
                      }}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      data-testid="view-mode-extract"
                    >
                      <Database />
                      <span className="tab-label">Extract</span>
                    </SidebarTab>
                  )}
                  {/* Analysis tab - only visible when analysis is selected */}
                  {selectedAnalysis && (
                    <SidebarTab
                      $isActive={sidebarViewMode === "analysis"}
                      $panelOpen={false}
                      onClick={() => {
                        setSidebarViewMode("analysis");
                        setShowRightPanel(true);
                      }}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      data-testid="view-mode-analysis"
                    >
                      <BarChart3 />
                      <span className="tab-label">Analysis</span>
                    </SidebarTab>
                  )}
                  {/* Discussions tab - always visible */}
                  <SidebarTab
                    $isActive={sidebarViewMode === "discussions"}
                    $panelOpen={false}
                    onClick={() => {
                      setSidebarViewMode("discussions");
                      setShowRightPanel(true);
                      setMode("half"); // Keep document visible
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    data-testid="view-mode-discussions"
                    aria-label="Document discussions"
                  >
                    {threadCount > 0 && (
                      <TabBadge $isActive={sidebarViewMode === "discussions"}>
                        {threadCount}
                      </TabBadge>
                    )}
                    <MessageSquare />
                    <span className="tab-label">Discussions</span>
                  </SidebarTab>
                </SidebarTabsContainer>
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
                    <MobileTabBar>
                      <MobileTab
                        $active={sidebarViewMode === "chat"}
                        onClick={() => {
                          if (sidebarViewMode === "chat") {
                            setShowRightPanel(false);
                          } else {
                            setSidebarViewMode("chat");
                          }
                        }}
                        data-testid="mobile-view-mode-chat"
                      >
                        <MessageSquare />
                        <span>Chat</span>
                      </MobileTab>
                      <MobileTab
                        $active={sidebarViewMode === "feed"}
                        onClick={() => {
                          if (sidebarViewMode === "feed") {
                            setShowRightPanel(false);
                          } else {
                            setSidebarViewMode("feed");
                          }
                        }}
                        data-testid="mobile-view-mode-feed"
                      >
                        <Layers />
                        <span>Feed</span>
                      </MobileTab>
                      {selectedExtract && (
                        <MobileTab
                          $active={sidebarViewMode === "extract"}
                          onClick={() => {
                            if (sidebarViewMode === "extract") {
                              setShowRightPanel(false);
                            } else {
                              setSidebarViewMode("extract");
                            }
                          }}
                          data-testid="mobile-view-mode-extract"
                        >
                          <Database />
                          <span>Extract</span>
                        </MobileTab>
                      )}
                      {selectedAnalysis && (
                        <MobileTab
                          $active={sidebarViewMode === "analysis"}
                          onClick={() => {
                            if (sidebarViewMode === "analysis") {
                              setShowRightPanel(false);
                            } else {
                              setSidebarViewMode("analysis");
                            }
                          }}
                          data-testid="mobile-view-mode-analysis"
                        >
                          <BarChart3 />
                          <span>Analysis</span>
                        </MobileTab>
                      )}
                      <MobileTab
                        $active={sidebarViewMode === "discussions"}
                        onClick={() => {
                          if (sidebarViewMode === "discussions") {
                            setShowRightPanel(!showRightPanel);
                          } else {
                            setSidebarViewMode("discussions");
                            setShowRightPanel(true);
                            setMode("full");
                          }
                        }}
                        aria-label="Document discussions"
                      >
                        <MessageSquare />
                        <span>
                          Discussions
                          {threadCount > 0 ? ` (${threadCount})` : ""}
                        </span>
                      </MobileTab>
                    </MobileTabBar>

                    {/* Tabs when panel is open - positioned on left edge of panel (desktop only) */}
                    <SidebarTabsContainer $panelOpen={true}>
                      <SidebarTab
                        $isActive={sidebarViewMode === "chat"}
                        $panelOpen={true}
                        onClick={() => {
                          if (sidebarViewMode === "chat") {
                            // Clicking active tab closes the panel
                            setShowRightPanel(false);
                          } else {
                            // Switch to chat mode
                            setSidebarViewMode("chat");
                          }
                        }}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        data-testid="view-mode-chat"
                      >
                        <MessageSquare />
                        <span className="tab-label">Chat</span>
                      </SidebarTab>
                      <SidebarTab
                        $isActive={sidebarViewMode === "feed"}
                        $panelOpen={true}
                        onClick={() => {
                          if (sidebarViewMode === "feed") {
                            // Clicking active tab closes the panel
                            setShowRightPanel(false);
                          } else {
                            // Switch to feed mode
                            setSidebarViewMode("feed");
                          }
                        }}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        data-testid="view-mode-feed"
                      >
                        <Layers />
                        <span className="tab-label">Feed</span>
                      </SidebarTab>
                      {/* Extract tab - only visible when extract is selected */}
                      {selectedExtract && (
                        <SidebarTab
                          $isActive={sidebarViewMode === "extract"}
                          $panelOpen={true}
                          onClick={() => {
                            if (sidebarViewMode === "extract") {
                              // Clicking active tab closes the panel
                              setShowRightPanel(false);
                            } else {
                              // Switch to extract mode
                              setSidebarViewMode("extract");
                            }
                          }}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                          data-testid="view-mode-extract"
                        >
                          <Database />
                          <span className="tab-label">Extract</span>
                        </SidebarTab>
                      )}
                      {/* Analysis tab - only visible when analysis is selected */}
                      {selectedAnalysis && (
                        <SidebarTab
                          $isActive={sidebarViewMode === "analysis"}
                          $panelOpen={true}
                          onClick={() => {
                            if (sidebarViewMode === "analysis") {
                              // Clicking active tab closes the panel
                              setShowRightPanel(false);
                            } else {
                              // Switch to analysis mode
                              setSidebarViewMode("analysis");
                            }
                          }}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                          data-testid="view-mode-analysis"
                        >
                          <BarChart3 />
                          <span className="tab-label">Analysis</span>
                        </SidebarTab>
                      )}
                      {/* Discussions tab - always visible */}
                      <SidebarTab
                        $isActive={sidebarViewMode === "discussions"}
                        $panelOpen={true}
                        onClick={() => {
                          if (sidebarViewMode === "discussions") {
                            // Clicking active tab closes the panel
                            setShowRightPanel(false);
                          } else {
                            // Switch to discussions mode
                            setSidebarViewMode("discussions");
                            setMode("half"); // Keep document visible
                          }
                        }}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        data-testid="view-mode-discussions"
                        aria-label="Document discussions"
                      >
                        {threadCount > 0 && (
                          <TabBadge
                            $isActive={sidebarViewMode === "discussions"}
                          >
                            {threadCount}
                          </TabBadge>
                        )}
                        <MessageSquare />
                        <span className="tab-label">Discussions</span>
                      </SidebarTab>
                    </SidebarTabsContainer>

                    {rightPanelContent}
                  </SlidingPanel>
                )}
              </AnimatePresence>
            </MainContentArea>
          </ContentArea>

          <Modal
            open={showGraph}
            onClose={() => setShowGraph(false)}
            size="large"
            basic
          >
            <Modal.Content>
              {/* Graph or relationship visualization */}
            </Modal.Content>
            <Modal.Actions>
              <Button onClick={() => setShowGraph(false)}>
                <X size={16} />
                Close
              </Button>
            </Modal.Actions>
          </Modal>

          <NoteModal
            id={`note-modal_${selectedNote?.id}`}
            closeIcon
            open={!!selectedNote}
            onClose={() => setSelectedNote(null)}
            size="large"
          >
            {selectedNote && (
              <>
                <Modal.Header>
                  {selectedNote.title || "Untitled Note"}
                </Modal.Header>
                <Modal.Content>
                  <SafeMarkdown>{selectedNote.content}</SafeMarkdown>
                </Modal.Content>
                <Modal.Actions>
                  {!readOnly && (
                    <Button
                      primary
                      onClick={() => {
                        setEditingNoteId(selectedNote.id);
                        setSelectedNote(null);
                      }}
                    >
                      <Icon name="edit" />
                      Edit Note
                    </Button>
                  )}
                  <Button onClick={() => setSelectedNote(null)}>Close</Button>
                </Modal.Actions>
                <div className="meta">
                  Added by {selectedNote.creator.email} on{" "}
                  {new Date(selectedNote.created).toLocaleString()}
                </div>
              </>
            )}
          </NoteModal>

          {!readOnly && editingNoteId && (
            <NoteEditor
              noteId={editingNoteId}
              isOpen={true}
              onClose={() => setEditingNoteId(null)}
              onUpdate={() => {
                // Refetch the document data to get updated notes
                refetch();
              }}
            />
          )}

          {!readOnly && (
            <NewNoteModal
              isOpen={showNewNoteModal}
              onClose={() => setShowNewNoteModal(false)}
              documentId={documentId}
              corpusId={corpusId}
              onCreated={() => {
                // Refetch the document data to get the new note
                refetch();
              }}
            />
          )}

          <AddToCorpusModal
            documentId={documentId}
            open={showAddToCorpusModal}
            onClose={() => setShowAddToCorpusModal(false)}
            onSuccess={(newCorpusId, newCorpus) => {
              // Reload with corpus context - prefer slug URL if available
              const document = combinedData?.document;
              if (
                newCorpus?.creator?.slug &&
                newCorpus?.slug &&
                document?.slug
              ) {
                // Use new /d/ prefix for document routes
                window.location.href = `/d/${newCorpus.creator.slug}/${newCorpus.slug}/${document.slug}`;
              } else {
                // Fallback shouldn't happen with new system, but keep safe
                console.warn("Missing slugs for navigation:", {
                  newCorpus,
                  document,
                });
                window.location.href = "/documents";
              }
            }}
          />
        </>
      )}
    </FullScreenModal>
  );
};

// REMOVED React.memo - was preventing proper unmounting during route transitions
// When navigating away, we need the component to unmount immediately, but React.memo
// was keeping stale instances alive briefly, causing flickering during state changes
export default DocumentKnowledgeBase;
