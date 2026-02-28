import React, { useState, useEffect, useCallback, useRef } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import { unstable_batchedUpdates } from "react-dom";
import { Button, Header, Modal, Loader, Message } from "semantic-ui-react";
import {
  MessageSquare,
  FileText,
  User,
  Calendar,
  FileType,
  ArrowLeft,
  Plus,
  Layers,
  Database,
  BarChart3,
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
import { updateAnnotationSelectionParams } from "../../../utils/navigationUtils";
import { routingLogger } from "../../../utils/routingLogger";

import {
  ContentArea,
  HeaderContainer,
  MainContentArea,
  MetadataRow,
  SlidingPanel,
  EmptyState,
  ResizeHandle,
  SidebarTabsContainer,
  SidebarTab,
  TabBadge,
  MobileTabBar,
  MobileTab,
} from "./StyledContainers";

import { useTextSearch } from "../../annotator/hooks/useTextSearch";
import {
  useAnalysisManager,
  useAnalysisSelection,
} from "../../annotator/hooks/AnalysisHooks";

import { FullScreenModal } from "./LayoutComponents";
import { SafeMarkdown } from "../markdown/SafeMarkdown";
import { useAnnotationSelection } from "../../annotator/context/UISettingsAtom";
import { useChatSourceState } from "../../annotator/context/ChatSourceAtom";
import { isTextFileType, isPdfFileType } from "../../../utils/files";
import { useCreateAnnotation } from "../../annotator/hooks/AnnotationHooks";
import { useScrollContainerRef } from "../../annotator/context/DocumentAtom";
import { useChatPanelWidth } from "../../annotator/context/UISettingsAtom";
import { FloatingSummaryPreview } from "./floating_summary_preview/FloatingSummaryPreview";
import { ZoomControls } from "./ZoomControls";

import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.mjs?url";
import { selectedThreadId } from "../../../graphql/cache";
import { useAuthReady } from "../../../hooks/useAuthReady";
import { useCorpusMdDescription } from "../../../hooks/useCorpusMdDescription";

// New imports for unified feed
import { ContentFilters, SortOption, SidebarViewMode } from "./unified_feed";
import { FloatingDocumentControls } from "./FloatingDocumentControls";
import { FloatingDocumentInput } from "./FloatingDocumentInput";
import { FloatingAnalysesPanel } from "./FloatingAnalysesPanel";
import { FloatingExtractsPanel } from "./FloatingExtractsPanel";
import UnifiedKnowledgeLayer from "./layers/UnifiedKnowledgeLayer";
import { DocumentVersionSelector } from "../../documents/DocumentVersionSelector";

// Sub-components extracted from DocumentKnowledgeBase
import {
  HeaderButtonGroup,
  HeaderButton,
  FloatingInputWrapper,
  ZoomIndicator,
} from "./document_kb/styles";
import { useZoomManager } from "./document_kb/useZoomManager";
import { RightPanelContent } from "./document_kb/RightPanelContent";
import { DocumentModals } from "./document_kb/DocumentModals";
import { AnalysisExtractContextBar } from "./document_kb/ContextBar";

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
  const getPanelWidthPercentage = useCallback((): number => {
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
  }, [mode, customWidth]);

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

      if (isPdfFileType(data.document.fileType) && data.document.pdfFile) {
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
        isTextFileType(data.document.fileType) &&
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
        if (isPdfFileType(data.document.fileType) && data.document.pdfFile) {
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

  // Fetch versioned markdown description for corpus info display
  const corpusMdContent = useCorpusMdDescription(
    corpusData?.corpus?.mdDescription
  );

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

  // The main viewer content:
  let viewerContent: JSX.Element = <></>;
  if (isPdfFileType(metadata.fileType)) {
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
  } else if (isTextFileType(metadata.fileType)) {
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
   * NOTE(deferred): Modal annotation seeding needs an approach that doesn't conflict
   * with router-based state — e.g. navigate to URL when opening modal, restore on close.
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
            {hasCorpus && corpusId && (
              <DocumentVersionSelector
                documentId={documentId}
                corpusId={corpusId}
              />
            )}
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
              {(corpusMdContent || corpusData.corpus.description) && (
                <SafeMarkdown>
                  {corpusMdContent || corpusData.corpus.description || ""}
                </SafeMarkdown>
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
                      showLoad={showLoad}
                      setShowLoad={setShowLoad}
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
