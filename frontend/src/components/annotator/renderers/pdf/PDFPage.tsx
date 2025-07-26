import { useRef, useState, useEffect, useMemo, useLayoutEffect } from "react";
import styled from "styled-components";
import { useAtom } from "jotai";
import { useAtomValue } from "jotai";
import { PageProps, TextSearchTokenResult } from "../../../types";
import { PDFPageRenderer, PageAnnotationsContainer, PageCanvas } from "./PDF";
import { Selection } from "../../display/components/Selection";
import { SearchResult } from "../../display/components/SearchResult";
import { BoundingBox, ServerTokenAnnotation } from "../../types/annotations";
import { usePdfAnnotations } from "../../hooks/AnnotationHooks";
import {
  scrollContainerRefAtom,
  usePages,
  useTextSearchState,
} from "../../context/DocumentAtom";
import {
  useAnnotationControls,
  useAnnotationDisplay,
  useZoomLevel,
  useAnnotationSelection,
} from "../../context/UISettingsAtom";
import { useAnnotationRefs } from "../../hooks/useAnnotationRefs";
import SelectionLayer from "./SelectionLayer";
import { PDFPageInfo } from "../../types/pdf";
import { chatSourcesAtom } from "../../context/ChatSourceAtom";
import { useCorpusState } from "../../context/CorpusAtom";
import { ChatSourceResult } from "../../display/components/ChatSourceResult";
import { useVisibleAnnotations } from "../../hooks/useVisibleAnnotations";
import { pendingScrollAnnotationIdAtom } from "../../context/DocumentAtom";
import { pendingScrollSearchResultIdAtom } from "../../context/DocumentAtom";
import { pendingScrollChatSourceKeyAtom } from "../../context/DocumentAtom";

/**
 * This wrapper is inline-block (shrink-wrapped) and position:relative
 * so that absolutely-positioned elements inside it match the canvas.
 */
const CanvasWrapper = styled.div`
  position: relative;
  display: inline-block;
`;

interface PDFPageProps extends PageProps {
  containerWidth?: number | null;
  createAnnotationHandler: (annotation: ServerTokenAnnotation) => Promise<void>;
}

/**
 * PDFPage Component
 *
 * Renders a single PDF page with annotations, selections, and search results.
 *
 * @param {PDFPageProps} props - Properties for the PDF page.
 * @returns {JSX.Element} The rendered PDF page component.
 */
export const PDFPage = ({
  pageInfo,
  read_only,
  onError,
  containerWidth,
  createAnnotationHandler,
}: PDFPageProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<PDFPageRenderer | null>(null);
  const { pdfAnnotations } = usePdfAnnotations();

  const pageViewport = pageInfo.page.getViewport({ scale: 1 });
  const [pageBounds, setPageBounds] = useState<BoundingBox>({
    left: 0,
    top: 0,
    right: pageViewport.width,
    bottom: pageViewport.height,
  });
  const [hasPdfPageRendered, setPdfPageRendered] = useState(false);
  const [initialZoomSet, setInitialZoomSet] = useState(false);

  const { showSelectedOnly } = useAnnotationDisplay();
  const { zoomLevel, setZoomLevel } = useZoomLevel();
  const { selectedAnnotations, selectedRelations } = useAnnotationSelection();

  const { annotationElementRefs, registerRef, unregisterRef } =
    useAnnotationRefs();
  const pageContainerRef = useRef<HTMLDivElement>(null);

  /* visible annotations (global) */
  const visibleAnnotations = useVisibleAnnotations();

  const [scrollContainerRef] = useAtom(scrollContainerRefAtom);
  const { pages, setPages } = usePages();

  const { textSearchMatches: searchResults, selectedTextSearchMatchIndex } =
    useTextSearchState();
  const { selectedCorpus } = useCorpusState();

  const annotationControls = useAnnotationControls();
  const { spanLabelsToView, activeSpanLabel } = annotationControls;

  const chatState = useAtomValue(chatSourcesAtom);
  const { messages, selectedMessageId, selectedSourceIndex } = chatState;
  const selectedMessage = useMemo(
    () => messages.find((m) => m.messageId === selectedMessageId),
    [messages, selectedMessageId]
  );

  const updatedPageInfo = useMemo(() => {
    return new PDFPageInfo(
      pageInfo.page,
      pageInfo.tokens,
      zoomLevel,
      pageBounds
    );
  }, [pageInfo.page, pageInfo.tokens, zoomLevel, pageBounds]);

  const [pendingScrollId, setPendingScrollId] = useAtom(
    pendingScrollAnnotationIdAtom
  );

  const [pendingScrollSearchId, setPendingScrollSearchId] = useAtom(
    pendingScrollSearchResultIdAtom
  );

  const [pendingScrollChatSourceKey, setPendingScrollChatSourceKey] = useAtom(
    pendingScrollChatSourceKeyAtom
  );

  const lastRenderedZoom = useRef<number | null>(null);

  useEffect(() => {
    setPages((prevPages) => ({
      ...prevPages,
      [pageInfo.page.pageNumber - 1]: updatedPageInfo,
    }));
  }, [updatedPageInfo]);

  useEffect(() => {
    // If this is page #1, and we haven't set initial zoom yet, and containerWidth is known:
    if (!initialZoomSet && containerWidth && pageInfo.page.pageNumber === 1) {
      (async () => {
        try {
          // measure the PDF's natural width
          const viewport = pageInfo.page.getViewport({ scale: 1 });
          const naturalWidth = viewport.width;

          // compute scale
          const scaleToFit = containerWidth / naturalWidth;

          // clamp if you like, e.g. [0.3 ... 3.0]
          const safeScale = Math.min(Math.max(scaleToFit, 0.3), 4.0);
          setZoomLevel(safeScale);

          setInitialZoomSet(true);
        } catch (err) {
          console.warn("Failed computing initial PDF scale:", err);
        }
      })();
    }
  }, [initialZoomSet, containerWidth, pageInfo.page, setZoomLevel]);

  /**
   * Handles resizing of the PDF page canvas.
   */
  const handleResize = () => {
    if (!canvasRef.current || !rendererRef.current) return;
    if (lastRenderedZoom.current === zoomLevel) return;

    const viewport = pageInfo.page.getViewport({ scale: zoomLevel });
    canvasRef.current.width = viewport.width;
    canvasRef.current.height = viewport.height;

    rendererRef.current.rescaleAndRender(zoomLevel);
    lastRenderedZoom.current = zoomLevel;
  };

  useEffect(() => {
    if (!hasPdfPageRendered && canvasRef.current && pageContainerRef.current) {
      const initializePage = async () => {
        try {
          // console.log(`PDFPage ${pageInfo.page.pageNumber}: Starting render`);
          if (pageContainerRef.current && canvasRef.current) {
            // console.log("\tSetup the renderer...");

            rendererRef.current = new PDFPageRenderer(
              pageInfo.page,
              canvasRef.current,
              onError
            );

            // Get viewport with desired zoom level
            const viewport = pageInfo.page.getViewport({ scale: zoomLevel });

            // Set canvas dimensions to match viewport
            canvasRef.current.width = viewport.width;
            canvasRef.current.height = viewport.height;

            // Set page bounds
            setPageBounds({
              left: 0,
              top: 0,
              right: viewport.width,
              bottom: viewport.height,
            });

            // console.log("\tAwait render...");
            await rendererRef.current.render(zoomLevel);

            if (!(pageInfo.page.pageNumber - 1 in pages)) {
              // console.log(`\tAdding pageInfo to ${pageInfo.page.pageNumber}`);
              setPages((prevPages) => ({
                ...prevPages,
                [pageInfo.page.pageNumber - 1]: pageInfo,
              }));
            }

            if (scrollContainerRef && scrollContainerRef.current) {
              // console.log(
              //   `\tAdding resize handler to page ${pageInfo.page.pageNumber}`
              // );
              scrollContainerRef.current.addEventListener(
                "resize",
                handleResize
              );
            }

            registerRef(
              "pdfPageContainer",
              canvasRef,
              pageInfo.page.pageNumber - 1
            );

            setPdfPageRendered(true);
          }
        } catch (error) {
          onError(error instanceof Error ? error : new Error(String(error)));
        }
      };
      initializePage();

      return () => {
        unregisterRef("pdfPageContainer", pageInfo.page.pageNumber - 1);
        if (scrollContainerRef && scrollContainerRef.current) {
          scrollContainerRef.current.removeEventListener(
            "resize",
            handleResize
          );
        }
      };
    } else if (
      hasPdfPageRendered &&
      canvasRef.current &&
      pageContainerRef.current
    ) {
      handleResize();
    }
  }, [zoomLevel, onError, pageInfo.page]);

  // Register and unregister the page container ref
  useEffect(() => {
    registerRef("pdfPageContainer", pageContainerRef, pageInfo.page.pageNumber);
    return () => {
      unregisterRef("pdfPageContainer", pageInfo.page.pageNumber);
    };
  }, [registerRef, unregisterRef, pageInfo.page.pageNumber]);

  /**
   * Determines the annotations to render, including ensuring that any annotation
   * involved in a currently selected relation is visible, regardless of other filters.
   */
  const pageIndex = pageInfo.page.pageNumber - 1;

  const annots_to_render = useMemo(() => {
    return visibleAnnotations.filter((annot) => {
      /* Selection layer renders only token annotations with bounds
         on the current page                                       */
      if (!(annot instanceof ServerTokenAnnotation)) return false;
      const pageData = annot.json[pageIndex];
      return pageData && pageData.bounds;
    });
  }, [visibleAnnotations, pageIndex]);

  const pageAnnotationComponents = useMemo(() => {
    if (!hasPdfPageRendered || !zoomLevel || !pageBounds) return [];

    const isVisible = (annot: ServerTokenAnnotation): boolean => {
      if (showSelectedOnly) {
        return selectedAnnotations.includes(annot.id);
      }
      return true; // existing checks (labels, structural, …) stay here
    };

    return annots_to_render
      .filter(isVisible)
      .map((annotation) => (
        <Selection
          key={annotation.id}
          selected={selectedAnnotations.includes(annotation.id)}
          pageInfo={pageInfo}
          annotation={annotation}
        />
      ));
  }, [
    annots_to_render,
    showSelectedOnly,
    selectedAnnotations,
    hasPdfPageRendered,
    zoomLevel,
    pageBounds,
  ]);

  /**
   * Once the PDF is rendered, scroll to the first chat source (if any)
   */
  const { chatSourceElementRefs } = useAnnotationRefs();
  useEffect(() => {
    if (selectedMessage && hasPdfPageRendered) {
      const index =
        selectedSourceIndex !== null && selectedSourceIndex !== undefined
          ? selectedSourceIndex
          : 0;
      const key = `${selectedMessage.messageId}.${index}`;

      // Add a small delay to ensure DOM is ready and any other effects have completed
      const timeoutId = setTimeout(() => {
        const el = chatSourceElementRefs.current[key];
        if (el) {
          // Use a more precise scroll that should work consistently
          const elementRect = el.getBoundingClientRect();
          const absoluteElementTop = elementRect.top + window.pageYOffset;
          const middle = absoluteElementTop - window.innerHeight / 2;
          window.scrollTo({
            top: middle,
            behavior: "smooth",
          });
        }
      }, 100);

      return () => clearTimeout(timeoutId);
    }
  }, [
    selectedMessage,
    selectedSourceIndex,
    hasPdfPageRendered,
    chatSourceElementRefs,
  ]);

  /* ——— single effect that centres whichever item has precedence ——— */
  useEffect(() => {
    if (!hasPdfPageRendered) return;

    /* 1️⃣  SEARCH (highest priority) */
    if (pendingScrollSearchId) {
      const pageOwnsResult = searchResults
        .filter((m): m is TextSearchTokenResult => "tokens" in m)
        .some(
          (m) =>
            String(m.id) === pendingScrollSearchId &&
            m.tokens[pageInfo.page.pageNumber - 1] !== undefined
        );
      if (!pageOwnsResult) return;

      let cancelled = false;
      const tryScrollSearch = () => {
        if (cancelled) return;
        const el = document.getElementById(
          `SEARCH_RESULT_${pendingScrollSearchId}`
        );
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          setPendingScrollSearchId(null); // done
        } else {
          requestAnimationFrame(tryScrollSearch);
        }
      };
      tryScrollSearch();
      return;
    }

    /* 2️⃣  CHAT SOURCE ------------------------------------------------- */
    if (pendingScrollChatSourceKey) {
      const el = document.getElementById(
        `CHAT_SOURCE_${pendingScrollChatSourceKey}`
      );
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        setPendingScrollChatSourceKey(null);
      }
      return;
    }

    /* 3️⃣  NORMAL ANNOTATION */
    if (pendingScrollId) {
      const pageOwnsAnnotation = visibleAnnotations.some(
        (a) =>
          a instanceof ServerTokenAnnotation &&
          a.id === pendingScrollId &&
          a.json[pageIndex] !== undefined
      );
      if (!pageOwnsAnnotation) return;

      let cancelled = false;
      const tryScrollAnnot = () => {
        if (cancelled) return;
        try {
          const el = document.querySelector(
            `.selection_${pendingScrollId}`
          ) as HTMLElement | null;
          if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "center" });
            setPendingScrollId(null); // done
          } else {
            requestAnimationFrame(tryScrollAnnot);
          }
        } catch (error) {
          console.error("Error scrolling to annotation:", error);
        }
      };
      tryScrollAnnot();
    }
  }, [
    hasPdfPageRendered,
    pendingScrollSearchId,
    pendingScrollChatSourceKey,
    pendingScrollId,
    searchResults,
    visibleAnnotations,
    pageIndex,
    setPendingScrollSearchId,
    setPendingScrollChatSourceKey,
    setPendingScrollId,
    chatSourceElementRefs.current,
  ]);

  useEffect(() => {
    if (!hasPdfPageRendered) return; // page not visible yet
    if (!canvasRef.current || !rendererRef.current) return;

    /* only rerender if zoom actually changed */
    if (lastRenderedZoom.current !== zoomLevel) {
      const viewport = pageInfo.page.getViewport({ scale: zoomLevel });
      canvasRef.current.width = viewport.width;
      canvasRef.current.height = viewport.height;

      rendererRef.current.rescaleAndRender(zoomLevel);
      lastRenderedZoom.current = zoomLevel;
    }
  }, [zoomLevel, hasPdfPageRendered, pageInfo.page]);

  return (
    <PageAnnotationsContainer
      className="PageAnnotationsContainer"
      ref={pageContainerRef}
      style={{ position: "relative" }}
    >
      <CanvasWrapper>
        <PageCanvas ref={canvasRef} />
        <SelectionLayer
          pageInfo={updatedPageInfo}
          read_only={read_only}
          activeSpanLabel={activeSpanLabel ?? null}
          createAnnotation={createAnnotationHandler}
          pageNumber={pageInfo.page.pageNumber - 1}
        />
        {pageAnnotationComponents}

        {zoomLevel &&
          pageBounds &&
          searchResults
            .filter(
              (match): match is TextSearchTokenResult => "tokens" in match
            )
            .filter(
              (match) =>
                match.tokens[pageInfo.page.pageNumber - 1] !== undefined
            )
            .map((match) => {
              const isHidden = match.id !== selectedTextSearchMatchIndex;

              return (
                <SearchResult
                  key={match.id}
                  total_results={searchResults.length}
                  showBoundingBox={true}
                  hidden={isHidden}
                  pageInfo={updatedPageInfo}
                  match={match}
                />
              );
            })}

        {selectedMessage &&
          selectedMessage.sources.map((source, index) => (
            <ChatSourceResult
              refKey={`${selectedMessage.messageId}.${index}`}
              key={source.id}
              total_results={selectedMessage.sources.length}
              showBoundingBox={true}
              hidden={
                selectedSourceIndex !== null && selectedSourceIndex !== index
              }
              pageInfo={updatedPageInfo}
              source={source}
              showInfo={true}
              scrollIntoView={selectedSourceIndex === index}
              selected={selectedSourceIndex === index}
            />
          ))}
      </CanvasWrapper>
    </PageAnnotationsContainer>
  );
};
