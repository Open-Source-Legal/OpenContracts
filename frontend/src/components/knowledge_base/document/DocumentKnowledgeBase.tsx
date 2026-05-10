import React, { useCallback, useEffect, useRef, useState } from "react";
import { useReactiveVar } from "@apollo/client";
import { unstable_batchedUpdates } from "react-dom";
import { Button, Modal, ModalBody, ModalFooter } from "@os-legal/ui";
import {
  ErrorMessage,
  InfoMessage,
  SuccessMessage,
} from "../../widgets/feedback";
import { useFeatureAvailability } from "../../../hooks/useFeatureAvailability";
import { AnimatePresence } from "framer-motion";
import { GlobalWorkerOptions } from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.mjs?url";
import { useUISettings } from "../../annotator/hooks/useUISettings";
import useWindowDimensions from "../../hooks/WindowDimensionHook";
import { ViewState } from "../../types";
import { toast } from "react-toastify";
import {
  useDocText,
  useSearchText,
  useTextSearchState,
} from "../../annotator/context/DocumentAtom";
import { useDocumentPermissions } from "../../annotator/context/DocumentAtom";
import { useAtom, useSetAtom } from "jotai";
import { useAnnotationSelection } from "../../annotator/context/UISettingsAtom";
import { useChatSourceState } from "../../annotator/context/ChatSourceAtom";
import { useCreateAnnotation } from "../../annotator/hooks/AnnotationHooks";
import { ServerTokenAnnotation } from "../../annotator/types/annotations";
import {
  selectedRelationsAtom,
  initialZoomSetAtom,
  useAnnotationControls,
  useChatPanelWidth,
} from "../../annotator/context/UISettingsAtom";
import { useCorpusState } from "../../annotator/context/CorpusAtom";
import { pdfAnnotationsAtom } from "../../annotator/context/AnnotationAtoms";
import { useNavigate, useLocation } from "react-router-dom";
import { updateAnnotationSelectionParams } from "../../../utils/navigationUtils";
import { routingLogger } from "../../../utils/routingLogger";
import { canEditAnnotationsInCorpus } from "../../../utils/annotationPermissions";
import { selectedNoteId, selectedThreadId } from "../../../graphql/cache";
import { useAuthReady } from "../../../hooks/useAuthReady";
import { useCorpusMdDescription } from "../../../hooks/useCorpusMdDescription";
import { useTextSearch } from "../../annotator/hooks/useTextSearch";
import {
  useAnalysisManager,
  useAnalysisSelection,
} from "../../annotator/hooks/AnalysisHooks";

import {
  ContentArea,
  MainContentArea,
  SlidingPanel,
  ResizeHandle,
} from "./StyledContainers";
import { FullScreenModal } from "./LayoutComponents";
import { SafeMarkdown } from "../markdown/SafeMarkdown";
import { EnhancedLabelSelector } from "../../annotator/labels/EnhancedLabelSelector";
import { FloatingSummaryPreview } from "./floating_summary_preview/FloatingSummaryPreview";
import { ZoomControls } from "./ZoomControls";
import { ContentFilters, SortOption, SidebarViewMode } from "./unified_feed";
import { FloatingDocumentControls } from "./FloatingDocumentControls";
import { FloatingDocumentInput } from "./FloatingDocumentInput";
import { FloatingAnalysesPanel } from "./FloatingAnalysesPanel";
import { FloatingExtractsPanel } from "./FloatingExtractsPanel";
import UnifiedKnowledgeLayer from "./layers/UnifiedKnowledgeLayer";

import {
  PANEL_WIDTH_QUARTER_PCT,
  PANEL_WIDTH_HALF_PCT,
  PANEL_WIDTH_FULL_PCT,
} from "../../../assets/configurations/constants";

// Sub-components extracted from DocumentKnowledgeBase
import { FloatingInputWrapper, ZoomIndicator } from "./document_kb/styles";
import { useZoomManager } from "./document_kb/useZoomManager";
import { RightPanelContent } from "./document_kb/RightPanelContent";
import { DocumentModals } from "./document_kb/DocumentModals";
import { AnalysisExtractContextBar } from "./document_kb/ContextBar";
import {
  DesktopSidebarTabs,
  MobileSidebarTabs,
} from "./document_kb/SidebarTabs";
import { DocumentViewer } from "./document_kb/DocumentViewer";
import { useResizeHandle } from "./document_kb/useResizeHandle";
import { useDocumentMarkdown } from "./document_kb/useDocumentMarkdown";
import { useStructuralAnnotations } from "./document_kb/useStructuralAnnotations";
import { useDocumentLoader } from "./document_kb/useDocumentLoader";
import { useContainerWidth } from "./document_kb/useContainerWidth";
import { HeaderBar } from "./document_kb/HeaderBar";

// Setting worker path to worker bundle.
GlobalWorkerOptions.workerSrc = workerSrc;

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

/**
 * Renders the "Invalid Document" error modal as its own component so the
 * parent `DocumentKnowledgeBase` can short-circuit BEFORE invoking any of
 * its data/UI hooks. Calling hooks above an early return is a Rules-of-Hooks
 * violation; isolating the error path here keeps the parent's hook list
 * stable across renders for any non-empty `documentId`.
 */
const InvalidDocumentIdModal: React.FC<{ onClose?: () => void }> = ({
  onClose,
}) => {
  const navigate = useNavigate();
  const handleClose = useCallback(() => {
    if (onClose) {
      onClose();
      return;
    }
    const historyIdx = (window.history.state as { idx?: number })?.idx ?? 0;
    if (historyIdx > 0) navigate(-1);
    else navigate("/documents");
  }, [onClose, navigate]);

  return (
    <Modal open onClose={handleClose} size="sm">
      <ModalBody>
        <ErrorMessage title="Invalid Document">
          Cannot load document: Invalid document ID
        </ErrorMessage>
      </ModalBody>
      <ModalFooter>
        <Button variant="secondary" onClick={handleClose}>
          Close
        </Button>
      </ModalFooter>
    </Modal>
  );
};

const DocumentKnowledgeBase: React.FC<DocumentKnowledgeBaseProps> = ({
  documentId,
  corpusId,
  initialAnnotationIds,
  onClose,
  readOnly = false,
  showCorpusInfo,
  showSuccessMessage,
}) => {
  // Validate documentId BEFORE invoking any hooks. Returning the error modal
  // from a sibling component keeps this component's hook list stable across
  // renders (prevents Rules-of-Hooks violation when the prop transitions
  // between empty and non-empty).
  if (!documentId || documentId === "") {
    console.error(
      "DocumentKnowledgeBase: Invalid documentId provided:",
      documentId
    );
    return <InvalidDocumentIdModal onClose={onClose} />;
  }

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
  const { setProgress, zoomLevel, setZoomLevel } =
    useUISettings(uiSettingsConfig);

  // Reset initial zoom flag when navigating to a different document so the
  // fit-to-width calculation in PDFPage fires again for the new document.
  const setInitialZoomSet = useSetAtom(initialZoomSetAtom);
  useEffect(() => {
    setInitialZoomSet(false);
  }, [documentId, setInitialZoomSet]);

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

  // Handle close: use provided onClose callback or fallback using browser history
  // Following routing mantra: route components should provide onClose to make navigation decisions
  // This component should NOT read openedCorpus() to decide navigation - that causes race conditions
  const handleClose = useCallback(() => {
    // Helper to navigate back or fallback to /documents
    // Uses React Router's history index to determine if there's history to go back to
    const navigateBackOrFallback = () => {
      // React Router v6 stores history index in window.history.state.idx
      // idx = 0 means this is the first page in the session (no back history)
      // idx > 0 means there's at least one page to go back to
      const historyIdx = (window.history.state as { idx?: number })?.idx ?? 0;

      if (historyIdx > 0) {
        routingLogger.debug(
          `[DocumentKnowledgeBase] Navigating back (historyIdx=${historyIdx})`
        );
        navigate(-1);
      } else {
        routingLogger.debug(
          "[DocumentKnowledgeBase] Navigating to /documents (no history)"
        );
        navigate("/documents");
      }
    };

    try {
      const timestamp = new Date().toISOString();
      routingLogger.debug(
        `🚪 [DocumentKnowledgeBase] ════════ handleClose START ════════`
      );
      routingLogger.debug("[DocumentKnowledgeBase] Timestamp:", timestamp);
      routingLogger.debug("[DocumentKnowledgeBase] Current state:", {
        hasOnClose: !!onClose,
        documentId,
        corpusId,
        currentUrl: window.location.pathname + window.location.search,
        historyIdx: (window.history.state as { idx?: number })?.idx ?? 0,
      });

      if (onClose) {
        routingLogger.debug(
          "[DocumentKnowledgeBase] ✅ Decision: Calling provided onClose callback"
        );
        onClose();
      } else {
        console.warn(
          "[DocumentKnowledgeBase] ⚠️  Decision: No onClose callback - using browser history fallback"
        );
        navigateBackOrFallback();
      }

      routingLogger.debug(
        "[DocumentKnowledgeBase] ════════ handleClose END ════════"
      );
    } catch (error) {
      console.error("[DocumentKnowledgeBase] ❌ ERROR in handleClose:", error);
      console.error("Stack trace:", error);
      // Fallback navigation on error
      navigateBackOrFallback();
    }
  }, [onClose, navigate, documentId, corpusId]);

  // Chat panel width management
  const { mode, customWidth, setMode, setCustomWidth, minimize, restore } =
    useChatPanelWidth();

  // Calculate actual panel width based on mode
  const getPanelWidthPercentage = useCallback((): number => {
    let panelWidth: number;
    switch (mode) {
      case "quarter":
        panelWidth = PANEL_WIDTH_QUARTER_PCT;
        break;
      case "half":
        panelWidth = PANEL_WIDTH_HALF_PCT;
        break;
      case "full":
        panelWidth = PANEL_WIDTH_FULL_PCT;
        break;
      case "custom":
        panelWidth = customWidth || PANEL_WIDTH_HALF_PCT;
        break;
      default:
        panelWidth = PANEL_WIDTH_HALF_PCT;
    }
    routingLogger.debug(
      "Panel width calculation - mode:",
      mode,
      "width:",
      panelWidth
    );
    return panelWidth;
  }, [mode, customWidth]);

  // Resize drag state — see useResizeHandle for the snap/clamp logic.
  const { isDragging, handleResizeStart } = useResizeHandle({
    getPanelWidthPercentage,
    setMode,
    setCustomWidth,
  });
  const [isMinimized, setIsMinimized] = useState(false);
  const documentAreaRef = useRef<HTMLDivElement>(null);

  const [showGraph, setShowGraph] = useState(false);

  // This layer state still determines whether to show the knowledge base layout vs document layout
  const [activeLayer, setActiveLayer] = useState<"knowledge" | "document">(
    "document"
  );

  const [showRightPanel, setShowRightPanel] = useState(false);

  // Calculate floating controls offset and visibility - MEMOIZED to prevent new object on every render
  const floatingControlsState = React.useMemo(() => {
    if (isMobile || !showRightPanel || activeLayer !== "document") {
      return { offset: 0, visible: true };
    }

    const panelWidthPercent = getPanelWidthPercentage();
    // Use the tracked viewport width from useWindowDimensions so this memo
    // stays in sync with `width` in the dep array — reading window.innerWidth
    // directly would silently snapshot the wrong size when only `width`
    // (without an isMobile crossing) updates.
    const panelWidthPx = (panelWidthPercent / 100) * width;
    const remainingSpacePercent = 100 - panelWidthPercent;
    const remainingSpacePx = width - panelWidthPx;

    // Hide controls if less than 10% viewport or less than 100px remaining
    const shouldHide = remainingSpacePercent < 10 || remainingSpacePx < 100;

    return {
      offset: shouldHide ? 0 : panelWidthPx,
      visible: !shouldHide,
    };
  }, [isMobile, showRightPanel, activeLayer, mode, customWidth, width]); // Dependencies: all values that affect calculation

  // Zoom management (keyboard, wheel, pinch, auto-zoom on sidebar toggle)
  const {
    showZoomIndicator,
    autoZoomEnabled,
    setAutoZoomEnabled,
    showZoomFeedback,
  } = useZoomManager({
    zoomLevel,
    setZoomLevel,
    activeLayer,
    showRightPanel,
    isMobile,
    mode,
    customWidth,
    getPanelWidthPercentage,
  });

  // pdfAnnotations is read-only here (the loader hook owns updates).
  // We need the value for the AnalysisExtractContextBar's annotation count.
  const [pdfAnnotations] = useAtom(pdfAnnotationsAtom);

  const { canUpdateCorpus } = useCorpusState();
  const { searchText, setSearchText } = useSearchText();
  const { permissions } = useDocumentPermissions();
  const { setTextSearchState } = useTextSearchState();
  const { activeSpanLabel, setActiveSpanLabel } = useAnnotationControls();
  const { setChatSourceState } = useChatSourceState();

  // Determine if user can edit based on permissions and corpus context
  const canEdit = React.useMemo(
    () =>
      canEditAnnotationsInCorpus({
        readOnly: Boolean(readOnly),
        corpusId,
        canUpdateCorpus,
        documentPermissions: permissions,
      }),
    [readOnly, corpusId, permissions, canUpdateCorpus]
  );

  // Call the hook ONCE here
  const originalCreateAnnotationHandler = useCreateAnnotation();

  // Conditional annotation handlers based on corpus availability
  const createAnnotationHandler = React.useCallback(
    async (annotation: ServerTokenAnnotation): Promise<void> => {
      if (!corpusId) {
        toast.info("Add document to corpus to create annotations");
        return;
      }
      await originalCreateAnnotationHandler(annotation);
    },
    [corpusId, originalCreateAnnotationHandler]
  );

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

  // Lazy-load structural annotations (headers/sections/paragraphs) — keep
  // them out of the main payload since large documents have thousands and
  // they're hidden by default.
  useStructuralAnnotations(documentId);

  // Container width tracking for fit-to-width zoom.
  const { containerWidth, containerRefCallback } = useContainerWidth();

  // Document data + body loading + thread count + analysis/extract refetch.
  const authReady = useAuthReady();
  const {
    corpusData,
    documentOnlyData,
    combinedData,
    loading,
    queryError,
    refetch,
    viewState,
    threadCount,
  } = useDocumentLoader({
    documentId,
    corpusId,
    authReady,
    zoomLevel,
    setProgress,
    selectedAnalysisId: selectedAnalysis?.id ?? null,
    selectedExtractId: selectedExtract?.id ?? null,
  });

  // Fetch versioned markdown description for corpus info display
  const corpusMdContent = useCorpusMdDescription(
    corpusData?.corpus?.mdDescription
  );

  const metadata = combinedData?.document ?? {
    title: "Loading...",
    fileType: "",
    creator: { id: "", slug: "" },
    created: new Date().toISOString(),
  };

  const notes = corpusId
    ? corpusData?.document?.allNotes ?? []
    : documentOnlyData?.document?.allNotes ?? [];
  const docRelationships = corpusId
    ? corpusData?.document?.allDocRelationships ?? []
    : [];

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
  const { markdownContent } = useDocumentMarkdown(
    combinedData?.document?.mdSummaryFile
  );

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
  // showLoad was lifted onto chatTrayStateAtom — see ChatTray.tsx and
  // UISettingsAtom.tsx (ChatTrayPersist.showLoad). Owning it here as a
  // useState made ChatTray's mount-time setShowLoad(false) call a
  // cross-component setState during render, which React flagged as a
  // "Cannot update a component (DocumentKnowledgeBase) while rendering
  // a different component (ChatTray)" warning.
  const [pendingChatMessage, setPendingChatMessage] = useState<string>();

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

  // Auto-open the note detail modal when ?note= deep-link is present.
  const deepLinkedNoteId = useReactiveVar(selectedNoteId);
  useEffect(() => {
    // Wait until the document query has resolved before deciding the
    // ?note=<id> param is unresolvable — `notes` is empty during the
    // loading window too, and clearing then would race the load.
    if (!deepLinkedNoteId || !combinedData?.document) return;
    const target = notes.find((n) => n.id === deepLinkedNoteId);
    if (target) setSelectedNote(target);
    // Clear regardless of match: once the document is loaded, a missing
    // target means the note is inaccessible, deleted, or the ID is stale —
    // leaving the var set would pin ?note=<id> in the URL forever via
    // CentralRouteManager.
    selectedNoteId(null);
  }, [deepLinkedNoteId, combinedData?.document, notes]);

  // The main viewer content:
  const viewerContent = (
    <DocumentViewer
      fileType={metadata.fileType ?? ""}
      viewState={viewState}
      canEdit={canEdit}
      containerWidth={containerWidth}
      containerRefCallback={containerRefCallback}
      createAnnotationHandler={createAnnotationHandler}
    />
  );

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
   * NOTE(deferred): Modal annotation seeding needs an approach that doesn't conflict
   * with router-based state — e.g. navigate to URL when opening modal, restore on close.
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
            combinedDocumentData={combinedData?.document}
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
