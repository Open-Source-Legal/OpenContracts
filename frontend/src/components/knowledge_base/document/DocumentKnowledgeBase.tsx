import React, { useState, useEffect, useCallback, useRef } from "react";
import { useQuery } from "@apollo/client";
import { Button, Header, Modal, Loader } from "semantic-ui-react";
import {
  MessageSquare,
  FileText,
  User,
  Calendar,
  X,
  FileType,
  ArrowLeft,
  Settings,
} from "lucide-react";
import {
  GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
  GetDocumentKnowledgeAndAnnotationsInput,
  GetDocumentKnowledgeAndAnnotationsOutput,
} from "../../../graphql/queries";
import { getDocumentRawText, getPawlsLayer } from "../../annotator/api/rest";
import { CorpusType, LabelType } from "../../../types/graphql-api";
import { AnimatePresence } from "framer-motion";
import { PDFContainer } from "../../annotator/display/viewer/DocumentViewer";
import { PDFDocumentLoadingTask } from "pdfjs-dist";
import { useUISettings } from "../../annotator/hooks/useUISettings";
import useWindowDimensions from "../../hooks/WindowDimensionHook";
import { PDFPageInfo } from "../../annotator/types/pdf";
import { Token, ViewState } from "../../types";
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
import { UnifiedLabelSelector } from "../../annotator/labels/UnifiedLabelSelector";
import { PDF } from "../../annotator/renderers/pdf/PDF";
import TxtAnnotatorWrapper from "../../annotator/components/wrappers/TxtAnnotatorWrapper";
import { useAnnotationControls } from "../../annotator/context/UISettingsAtom";

import {
  ContentArea,
  ControlButton,
  ControlButtonGroupLeft,
  ControlButtonWrapper,
  HeaderContainer,
  MainContentArea,
  MetadataRow,
  SlidingPanel,
  EmptyState,
  ResizeHandle,
  ResizeHandleControl,
  WidthControlMenu,
  WidthMenuItem,
  ChatIndicator,
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
import { useAnnotationSelection } from "../../annotator/hooks/useAnnotationSelection";
import styled from "styled-components";
import { Icon } from "semantic-ui-react";
import { useChatSourceState } from "../../annotator/context/ChatSourceAtom";
import { useCreateAnnotation } from "../../annotator/hooks/AnnotationHooks";
import { useScrollContainerRef } from "../../annotator/context/DocumentAtom";
import { useChatPanelWidth } from "../../annotator/context/UISettingsAtom";
import { NoteEditor } from "./NoteEditor";
import { NewNoteModal } from "./NewNoteModal";
import { useUrlAnnotationSync } from "../../../hooks/useUrlAnnotationSync";
import { FloatingSummaryPreview } from "./floating_summary_preview/FloatingSummaryPreview";
import { ZoomControls } from "./ZoomControls";

import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.mjs?url";
import { openedDocument, openedCorpus } from "../../../graphql/cache";
import { selectedAnnotationIds } from "../../../graphql/cache";
import { useAuthReady } from "../../../hooks/useAuthReady";

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

// Setting worker path to worker bundle.
GlobalWorkerOptions.workerSrc = workerSrc;

interface DocumentKnowledgeBaseProps {
  documentId: string;
  corpusId: string;
  /**
   * Optional list of annotation IDs that should be selected when the modal opens.
   * When provided the component will seed `selectedAnnotationsAtom`, triggering
   * the usual scroll-to-annotation behaviour in the PDF/TXT viewers.
   */
  initialAnnotationIds?: string[];
  onClose?: () => void;
  /**
   * When true, disables all editing capabilities and shows only view-only features.
   */
  readOnly?: boolean;
}

const DocumentKnowledgeBase: React.FC<DocumentKnowledgeBaseProps> = ({
  documentId,
  corpusId,
  initialAnnotationIds,
  onClose,
  readOnly = false,
}) => {
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  const { setProgress, zoomLevel, setShiftDown, setZoomLevel } = useUISettings({
    width,
  });

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
    console.log("Panel width calculation - mode:", mode, "width:", width);
    return width;
  };

  // Resize handle state
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragStartWidth, setDragStartWidth] = useState(0);
  const [isMinimized, setIsMinimized] = useState(false);
  const documentAreaRef = useRef<HTMLDivElement>(null);
  const [showWidthMenu, setShowWidthMenu] = useState(false);

  const [showGraph, setShowGraph] = useState(false);

  // This layer state still determines whether to show the knowledge base layout vs document layout
  const [activeLayer, setActiveLayer] = useState<"knowledge" | "document">(
    "document"
  );

  const [viewState, setViewState] = useState<ViewState>(ViewState.LOADING);
  const [showRightPanel, setShowRightPanel] = useState(false);

  // Calculate floating controls offset and visibility
  const calculateFloatingControlsState = () => {
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
  };

  const floatingControlsState = calculateFloatingControlsState();

  const { setDocumentType } = useDocumentType();
  const { setDocument } = useDocumentState();
  const { setDocText } = useDocText();
  const {
    pageTokenTextMaps: pageTextMaps,
    setPageTokenTextMaps: setPageTextMaps,
  } = usePageTokenTextMaps();
  const { setPages } = usePages();
  const [_, setPdfAnnotations] = useAtom(pdfAnnotationsAtom);
  const [, setStructuralAnnotations] = useAtom(structuralAnnotationsAtom);
  const { setCorpus } = useCorpusState();
  const { setInitialAnnotations } = useInitialAnnotations();
  const { searchText, setSearchText } = useSearchText();
  const { setPermissions } = useDocumentPermissions();
  const { setTextSearchState } = useTextSearchState();
  const { activeSpanLabel, setActiveSpanLabel } = useAnnotationControls();
  const { setChatSourceState } = useChatSourceState();
  const { setPdfDoc } = usePdfDoc();

  // Call the hook ONCE here
  const createAnnotationHandler = useCreateAnnotation();

  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [markdownError, setMarkdownError] = useState<boolean>(false);

  const { selectedAnalysis, selectedExtract } = useAnalysisSelection();
  const { selectedAnnotations, setSelectedAnnotations } =
    useAnnotationSelection();

  const {
    dataCells,
    columns,
    analyses,
    extracts,
    onSelectAnalysis,
    onSelectExtract,
  } = useAnalysisManager();

  useTextSearch();

  useEffect(() => {
    setSearchText("");
    setTextSearchState({
      matches: [],
      selectedIndex: 0,
    });
  }, [setTextSearchState]);

  useEffect(() => {
    // Reset or set the default selections.
    onSelectAnalysis(null);
    onSelectExtract(null);
  }, []);

  /**
   * If analysis or annotation is selected, switch to document view.
   */
  useEffect(() => {
    if (selectedAnalysis || (selectedAnnotations?.length ?? 0) > 0) {
      setActiveLayer("document");
    }
  }, [selectedAnalysis, selectedAnnotations]);

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
    console.log("[processAnnotationsData] Received data:", data); // Log received data
    console.log(
      "[processAnnotationsData] Received data.corpus:",
      JSON.stringify(data?.corpus, null, 2)
    ); // Log corpus part specifically
    console.log(
      "[processAnnotationsData] Received data.corpus.myPermissions:",
      data?.corpus?.myPermissions
    ); // Log corpus part specifically
    if (data?.document) {
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

      // Update pdfAnnotations atom
      setPdfAnnotations(
        (prev) =>
          new PdfAnnotations(
            [...processedAnnotations, ...structuralAnnotations],
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
        console.log("[processAnnotationsData] Processing labelSet...");
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
        // Transform RawCorpusType to CorpusType before assigning
        const transformedCorpus: CorpusType = {
          ...data.corpus,
          myPermissions: getPermissions(data.corpus.myPermissions || []),
        } as any;
        corpusUpdatePayload.selectedCorpus = transformedCorpus; // Assign the transformed object
      }

      // Update corpus state using the constructed payload
      if (Object.keys(corpusUpdatePayload).length > 0) {
        console.log(
          "[processAnnotationsData] Corpus update payload:",
          JSON.stringify(corpusUpdatePayload, null, 2) // Log the final payload
        );
        console.log("[processAnnotationsData] Calling setCorpus...");
        setCorpus(corpusUpdatePayload); // Pass the complete payload
        console.log("[processAnnotationsData] setCorpus called.");
      }

      // Keep global navigation vars in sync so router & other components know
      openedDocument(data.document as any);
      if (data.corpus) {
        const transformedCorpus: CorpusType = {
          ...data.corpus,
          myPermissions: getPermissions(data.corpus.myPermissions || []),
        } as any;
        openedCorpus(transformedCorpus);
      }
      setPermissions(data.document.myPermissions ?? []);
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

  // Fetch combined knowledge & annotation data
  const authReady = useAuthReady();
  const {
    data: combinedData,
    loading,
    error: queryError,
    refetch,
  } = useQuery<
    GetDocumentKnowledgeAndAnnotationsOutput,
    GetDocumentKnowledgeAndAnnotationsInput
  >(GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS, {
    skip: !authReady || !documentId || !corpusId,
    variables: {
      documentId,
      corpusId,
      analysisId: undefined,
    },
    onCompleted: (data) => {
      if (!data?.document) {
        console.error("onCompleted: No document data received.");
        setViewState(ViewState.ERROR);
        toast.error("Failed to load document details.");
        return;
      }
      setDocumentType(data.document.fileType ?? "");
      let processedDocData = {
        ...data.document,
        myPermissions: getPermissions(data.document.myPermissions) ?? [],
      };
      setDocument(processedDocData);
      setPermissions(data.document.myPermissions ?? []);
      processAnnotationsData(data);

      if (
        data.document.fileType === "application/pdf" &&
        data.document.pdfFile
      ) {
        setViewState(ViewState.LOADING); // Set loading state
        const loadingTask: PDFDocumentLoadingTask = getDocument(
          data.document.pdfFile
        );
        loadingTask.onProgress = (p: { loaded: number; total: number }) => {
          setProgress(Math.round((p.loaded / p.total) * 100));
        };

        const pawlsPath = data.document.pawlsParseFile || "";

        Promise.all([
          loadingTask.promise,
          getPawlsLayer(pawlsPath), // Fetches PAWLS via REST
        ])
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
            setPages(loadedPages);
            const { doc_text, string_index_token_map } =
              createTokenStringSearch(loadedPages);
            setPageTextMaps({
              ...string_index_token_map,
              ...pageTextMaps,
            });
            setDocText(doc_text);
            setViewState(ViewState.LOADED); // Set loaded state only after everything is done
          })
          .catch((err) => {
            // Log the specific error causing the catch
            console.error("Error during PDF/PAWLS loading Promise.all:", err);
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
        console.log("onCompleted: Loading TXT", data.document.txtExtractFile);
        setViewState(ViewState.LOADING); // Set loading state
        getDocumentRawText(data.document.txtExtractFile)
          .then((txt) => {
            setDocText(txt);
            setViewState(ViewState.LOADED);
          })
          .catch((err) => {
            setViewState(ViewState.ERROR);
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

  useEffect(() => {
    if (!loading) {
      refetch({
        documentId,
        corpusId,
        analysisId: selectedAnalysis?.id,
      });
    }
  }, [selectedAnalysis, corpusId, refetch, loading, documentId]);

  useEffect(() => {
    if (!loading) {
      refetch({
        documentId,
        corpusId,
        analysisId: selectedExtract?.id,
      });
    }
  }, [selectedExtract, corpusId, refetch, loading, documentId]);

  const metadata = combinedData?.document ?? {
    title: "Loading...",
    fileType: "",
    creator: { email: "" },
    created: new Date().toISOString(),
  };

  const notes = combinedData?.document?.allNotes ?? [];
  const docRelationships = combinedData?.document?.allDocRelationships ?? [];

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

  // Close width menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (showWidthMenu && !target.closest("[data-width-menu]")) {
        setShowWidthMenu(false);
      }
    };

    if (showWidthMenu) {
      document.addEventListener("mousedown", handleClickOutside);
      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showWidthMenu]);

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

    return () => {
      document.removeEventListener("wheel", handleWheelZoom);
      document.removeEventListener("keydown", handleKeyboardZoom);
    };
  }, [activeLayer, handleWheelZoom, handleKeyboardZoom]);

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
    annotationFilters: {
      showStructural: false,
    },
    relationshipFilters: {
      showStructural: false,
    },
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

    // Handle unified feed mode
    if (sidebarViewMode === "feed") {
      return (
        <div
          style={{ display: "flex", flexDirection: "column", height: "100%" }}
        >
          {controlBar}
          <UnifiedContentFeed
            notes={notes}
            filters={feedFilters}
            sortBy={feedSortBy}
            isLoading={loading}
            readOnly={readOnly}
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

    // Handle chat mode (default behavior)
    return (
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
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
            read_only={readOnly}
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
          <TxtAnnotatorWrapper readOnly={readOnly} allowInput={!readOnly} />
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
    activeLayer === "knowledge" ? (
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
          flex: 1,
          position: "relative",
          marginRight:
            !isMobile && showRightPanel
              ? `${getPanelWidthPercentage()}%`
              : undefined,
        }}
      >
        {viewerContent}
      </div>
    );

  // Set initial state - ensure chat panel starts with proper width
  useEffect(() => {
    setShowRightPanel(false);
    setActiveLayer("document");
    // Force initial width to half
    if (mode !== "half") {
      setMode("half");
    }
  }, []);

  /* ------------------------------------------------------------------ */
  /* Seed selection atom once if the caller provided initial ids         */
  useEffect(() => {
    if (initialAnnotationIds && initialAnnotationIds.length > 0) {
      setSelectedAnnotations(initialAnnotationIds);
    }
  }, [initialAnnotationIds, setSelectedAnnotations]);

  // keep URL ↔ selection in sync
  useUrlAnnotationSync();

  /* ------------------------------------------------------ */
  /*  Cleanup on unmount – clear document + annotation sel  */
  /* ------------------------------------------------------ */
  useEffect(() => {
    return () => {
      openedDocument(null); // leave corpus intact
      setSelectedAnnotations([]);
      selectedAnnotationIds([]);
      // Clean up zoom indicator timer
      if (zoomIndicatorTimer.current) {
        clearTimeout(zoomIndicatorTimer.current);
      }
    };
  }, [setSelectedAnnotations]);

  /* ------------------------------------------------------------- */
  /* Floating input wrapper (centres input within remaining space) */
  /* ------------------------------------------------------------- */

  const FloatingInputWrapper = styled.div<{ $panelOffset: number }>`
    position: absolute;
    bottom: 2rem;
    left: 0;
    right: ${(props) => props.$panelOffset}px;
    display: flex;
    justify-content: center;
    pointer-events: none; /* allow clicks only on children */
    z-index: 1500;

    @media (max-width: 768px) {
      /* On mobile, let the child component handle its own positioning */
      position: static;
      left: auto;
      right: auto;
      bottom: auto;
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

  const [selectedSummaryContent, setSelectedSummaryContent] = useState<
    string | null
  >(null);

  return (
    <FullScreenModal
      id="knowledge-base-modal"
      open={true}
      onClose={onClose}
      closeIcon
    >
      <HeaderContainer>
        <div>
          <Header as="h2" style={{ margin: 0 }}>
            {metadata.title}
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
      </HeaderContainer>

      <ContentArea id="content-area">
        <MainContentArea id="main-content-area">
          {mainLayerContent}
          <UnifiedLabelSelector
            sidebarWidth="0px"
            activeSpanLabel={activeSpanLabel ?? null}
            setActiveLabel={setActiveSpanLabel}
            showRightPanel={showRightPanel}
            panelOffset={floatingControlsState.offset}
            hideControls={!floatingControlsState.visible}
            readOnly={readOnly}
          />

          {/* Floating Summary Preview - always visible, acts as picture-in-picture for knowledge layer */}
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

          {/* Zoom Controls - only in document layer */}
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

          {/* Zoom Indicator - shows current zoom level when zooming */}
          {showZoomIndicator && activeLayer === "document" && (
            <ZoomIndicator data-testid="zoom-indicator">
              {Math.round(zoomLevel * 100)}%
            </ZoomIndicator>
          )}

          {/* Unified Search/Chat Input - only in document layer */}
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

          {/* Floating Document Controls - only in document layer */}
          <FloatingDocumentControls
            visible={
              activeLayer === "document" && floatingControlsState.visible
            }
            onAnalysesClick={() => setShowAnalysesPanel(!showAnalysesPanel)}
            onExtractsClick={() => setShowExtractsPanel(!showExtractsPanel)}
            analysesOpen={showAnalysesPanel}
            extractsOpen={showExtractsPanel}
            panelOffset={floatingControlsState.offset}
            readOnly={readOnly}
          />

          {/* Floating Analyses Panel */}
          <FloatingAnalysesPanel
            visible={
              showAnalysesPanel &&
              activeLayer === "document" &&
              floatingControlsState.visible
            }
            analyses={analyses}
            onClose={() => setShowAnalysesPanel(false)}
            panelOffset={floatingControlsState.offset}
            readOnly={readOnly}
          />

          {/* Floating Extracts Panel */}
          <FloatingExtractsPanel
            visible={
              showExtractsPanel &&
              activeLayer === "document" &&
              floatingControlsState.visible
            }
            extracts={extracts}
            onClose={() => setShowExtractsPanel(false)}
            panelOffset={floatingControlsState.offset}
            readOnly={readOnly}
          />

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
                >
                  <ResizeHandleControl
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowWidthMenu(!showWidthMenu);
                    }}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                  >
                    <Settings className="settings-icon" />
                  </ResizeHandleControl>
                </ResizeHandle>

                <AnimatePresence>
                  {showWidthMenu && (
                    <WidthControlMenu
                      initial={{ opacity: 0, scale: 0.8, x: -20 }}
                      animate={{ opacity: 1, scale: 1, x: 0 }}
                      exit={{ opacity: 0, scale: 0.8, x: -20 }}
                      transition={{
                        duration: 0.2,
                        ease: [0.4, 0, 0.2, 1],
                      }}
                      data-width-menu
                    >
                      <WidthMenuItem
                        id="compact-width-menu-item"
                        $isActive={mode === "quarter"}
                        onClick={() => {
                          setMode("quarter");
                          setShowWidthMenu(false);
                        }}
                        whileTap={{ scale: 0.98 }}
                      >
                        Compact
                        <span className="percentage">25%</span>
                      </WidthMenuItem>
                      <WidthMenuItem
                        $isActive={mode === "half"}
                        onClick={() => {
                          setMode("half");
                          setShowWidthMenu(false);
                        }}
                        whileTap={{ scale: 0.98 }}
                      >
                        Standard
                        <span className="percentage">50%</span>
                      </WidthMenuItem>
                      <WidthMenuItem
                        id="wide-width-menu-item"
                        $isActive={mode === "full"}
                        onClick={() => {
                          setMode("full");
                          setShowWidthMenu(false);
                        }}
                        whileTap={{ scale: 0.98 }}
                      >
                        Wide
                        <span className="percentage">90%</span>
                      </WidthMenuItem>
                    </WidthControlMenu>
                  )}
                </AnimatePresence>

                <ControlButtonGroupLeft>
                  <ControlButtonWrapper>
                    <ControlButton
                      onClick={() => {
                        setShowRightPanel(false);
                      }}
                      whileHover={{ scale: 1.1 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <div className="energy-core" />
                      <div className="arrow-wrapper">
                        <ArrowLeft strokeWidth={3} />
                      </div>
                    </ControlButton>
                  </ControlButtonWrapper>
                </ControlButtonGroupLeft>
                {rightPanelContent}
              </SlidingPanel>
            )}
          </AnimatePresence>

          {/* Chat indicator when panel is closed */}
          <AnimatePresence>
            {!showRightPanel && (
              <ChatIndicator
                onClick={() => {
                  setSidebarViewMode("chat");
                  setShowRightPanel(true);
                }}
                initial={{ x: 100, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: 100, opacity: 0 }}
                transition={{ type: "spring", damping: 20, stiffness: 300 }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <MessageSquare />
              </ChatIndicator>
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
          <ControlButton onClick={() => setShowGraph(false)}>
            <X size={16} />
          </ControlButton>
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
            <Modal.Header>{selectedNote.title || "Untitled Note"}</Modal.Header>
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
    </FullScreenModal>
  );
};

export default DocumentKnowledgeBase;
