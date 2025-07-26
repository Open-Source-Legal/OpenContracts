import styled from "styled-components";
import { PDFPageProxy } from "pdfjs-dist/types/src/display/api";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { PDFPage } from "./PDFPage";
import {
  usePages,
  usePdfDoc,
  useSetViewStateError,
  scrollContainerRefAtom,
  pendingScrollAnnotationIdAtom,
  useTextSearchState,
  pendingScrollChatSourceKeyAtom,
} from "../../context/DocumentAtom";
import { ServerTokenAnnotation, BoundingBox } from "../../types/annotations";
import { useAtomValue, useSetAtom } from "jotai";
import {
  useZoomLevel,
  useAnnotationSelection,
} from "../../context/UISettingsAtom";
import { useAllAnnotations } from "../../hooks/useAllAnnotations";
import { pendingScrollSearchResultIdAtom } from "../../context/DocumentAtom";
import { TextSearchTokenResult } from "../../../types";
import { chatSourcesAtom } from "../../context/ChatSourceAtom";

export class PDFPageRenderer {
  private currentRenderTask?: ReturnType<PDFPageProxy["render"]>;
  constructor(
    readonly page: PDFPageProxy,
    readonly canvas: HTMLCanvasElement,
    readonly onError: (e: Error) => void
  ) {}

  cancelCurrentRender() {
    try {
      if (this.currentRenderTask === undefined) {
        return;
      }
      this.currentRenderTask.promise.then(
        () => {},
        (err: any) => {
          if (
            err instanceof Error &&
            err.message.indexOf("Rendering cancelled") !== -1
          ) {
            // Swallow the error that's thrown when the render is canceled.
            return;
          }
          const e = err instanceof Error ? err : new Error(err);
          // this.onError(e);
          console.warn("Issue cancelling render", e);
        }
      );
      this.currentRenderTask.cancel();
    } catch {}
  }

  render(scale: number) {
    const viewport = this.page.getViewport({ scale });

    this.canvas.height = viewport.height;
    this.canvas.width = viewport.width;

    const canvasContext = this.canvas.getContext("2d");
    if (canvasContext === null) {
      throw new Error("No canvas context");
    }
    this.currentRenderTask = this.page.render({ canvasContext, viewport });
    return this.currentRenderTask;
  }

  rescaleAndRender(scale: number) {
    this.cancelCurrentRender();
    return this.render(scale);
  }
}

interface PDFProps {
  read_only: boolean;
  containerWidth?: number | null;
  createAnnotationHandler: (annotation: ServerTokenAnnotation) => Promise<void>;
}

export const PDF: React.FC<PDFProps> = ({
  read_only,
  containerWidth,
  createAnnotationHandler,
}) => {
  const { pages } = usePages();
  const setViewStateError = useSetViewStateError();
  const { zoomLevel } = useZoomLevel();
  const { selectedAnnotations } = useAnnotationSelection();
  const { pdfDoc } = usePdfDoc();
  const { textSearchMatches, selectedTextSearchMatchIndex } =
    useTextSearchState();
  const setPendingScrollId = useSetAtom(pendingScrollAnnotationIdAtom);
  const setPendingScrollSearchId = useSetAtom(pendingScrollSearchResultIdAtom);
  const chatState = useAtomValue(chatSourcesAtom);
  const setPendingScrollChatSourceId = useSetAtom(
    pendingScrollChatSourceKeyAtom
  );
  const { messages, selectedMessageId, selectedSourceIndex } = chatState;
  /* ------------------------------------------------------------------ */
  /* reference to the scrolling element                                 */
  const scrollContainerRef = useAtomValue(scrollContainerRefAtom);
  const [pageHeights, setPageHeights] = useState<number[]>([]);
  const allAnnotations = useAllAnnotations();

  /* ---------- build index & heights ---------------------------------- */
  const pageInfos = useMemo(
    () =>
      Object.values(pages).sort(
        (a, b) => a.page.pageNumber - b.page.pageNumber
      ),
    [pages]
  );

  /**
   * Returns the zero-based page index of the first selected annotation, or undefined if
   * no annotation is selected or the annotation cannot be found.
   */
  const selectedPageIdx = useMemo(() => {
    if (selectedAnnotations.length === 0) return undefined;
    const annot = allAnnotations.find((a) => a.id === selectedAnnotations[0]);
    return annot?.page; // undefined if not found
  }, [selectedAnnotations, allAnnotations]);

  /* page index that owns the selected match */
  const selectedSearchPageIdx = useMemo(() => {
    const hit = textSearchMatches.find(
      (m) => m.id === selectedTextSearchMatchIndex
    ) as TextSearchTokenResult;
    if (!hit) return undefined;
    return hit.start_page; // first page of the match
  }, [textSearchMatches, selectedTextSearchMatchIndex]);

  const selectedChatSourcePageIdx = useMemo(() => {
    if (!selectedMessageId || selectedSourceIndex === null) return undefined;
    const message = messages.find((m) => m.messageId === selectedMessageId);
    const source = message?.sources?.[selectedSourceIndex ?? -1];
    if (!source) return undefined;
    return Math.min(...Object.keys(source.boundsByPage).map(Number));
  }, [messages, selectedMessageId, selectedSourceIndex]);

  /* build the cache once per zoom level */
  useEffect(() => {
    if (!pdfDoc) return;
    (async () => {
      const h: number[] = [];
      for (let i = 1; i <= pdfDoc.numPages; i++) {
        const page = await pdfDoc.getPage(i);
        h.push(page.getViewport({ scale: zoomLevel }).height + 32);
      }
      setPageHeights(h); // updates state → re-render
    })();
  }, [pdfDoc, zoomLevel]);

  /* prefix sums for quick offset lookup */
  const cumulative = useMemo(() => {
    const out: number[] = [0];
    for (let i = 0; i < pageHeights.length; i++) {
      out.push(out[i] + pageHeights[i]);
    }
    return out; // length = pageCount + 1
  }, [pageHeights]);

  /* ------------------------------------------------------------------ */
  /* utility: pick the element that actually scrolls ------------------- */
  const getScrollElement = useCallback((): HTMLElement | Window => {
    const el = scrollContainerRef?.current;
    if (el && el.scrollHeight > el.clientHeight) return el;
    // fallback – the page itself scrolls
    return window;
  }, [scrollContainerRef]);

  /* ---------- visible window tracking -------------------------------- */
  const [range, setRange] = useState<[number, number]>([0, 0]); // [startIdx, endIdx]

  const calcRange = useCallback(() => {
    const el = getScrollElement();
    const scroll =
      el instanceof Window
        ? window.scrollY || document.documentElement.scrollTop
        : el.scrollTop;
    const viewH = el instanceof Window ? window.innerHeight : el.clientHeight;

    // binary search for first page whose bottom >= scrollTop
    let lo = 0,
      hi = cumulative.length - 1;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (cumulative[mid + 1] < scroll) lo = mid + 1;
      else hi = mid;
    }
    const first = lo;

    // find last page whose top <= scrollTop + viewH
    lo = first;
    hi = cumulative.length - 2;
    const limit = scroll + viewH;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      if (cumulative[mid] <= limit) lo = mid;
      else hi = mid - 1;
    }
    const last = lo;

    const overscan = 2;
    let start = Math.max(0, first - overscan);
    let end = Math.min(pageInfos.length - 1, last + overscan);

    /* ensure the page that owns the selection is mounted */
    if (selectedPageIdx !== undefined) {
      start = Math.min(start, selectedPageIdx);
      end = Math.max(end, selectedPageIdx);
    }

    /* 1. virtual-window must keep that page mounted */
    if (selectedSearchPageIdx !== undefined) {
      start = Math.min(start, selectedSearchPageIdx);
      end = Math.max(end, selectedSearchPageIdx);
    }

    /* 🪟 ensure the page is mounted */
    if (selectedChatSourcePageIdx !== undefined) {
      start = Math.min(start, selectedChatSourcePageIdx);
      end = Math.max(end, selectedChatSourcePageIdx);
    }

    setRange([start, end]);
  }, [
    getScrollElement,
    cumulative,
    pageInfos.length,
    selectedPageIdx,
    selectedSearchPageIdx,
    selectedChatSourcePageIdx,
  ]);

  /* attach / detach scroll listener(s) */
  useEffect(() => {
    const elWindow = window;
    const elContainer = scrollContainerRef?.current;
    calcRange(); // initial
    const onScroll = () => requestAnimationFrame(calcRange);
    elWindow.addEventListener("scroll", onScroll, { passive: true });
    elContainer?.addEventListener("scroll", onScroll, { passive: true });

    return () => {
      elWindow.removeEventListener("scroll", onScroll);
      elContainer?.removeEventListener("scroll", onScroll);
    };
  }, [scrollContainerRef, calcRange]);

  /* update window when zoom changes */
  useEffect(calcRange, [zoomLevel, calcRange]);

  /**
   * Scroll to the selected annotation's page whenever:
   * 1. A new annotation is selected, OR
   * 2. The page heights become available, OR
   * 3. The zoom level changes (which affects page positions)
   *
   * This effect handles the first part of the scroll-to-annotation process:
   * - Scroll the container so the correct PAGE is visible
   * - Set pendingScrollId so the PDFPage component can center the specific annotation
   */
  useEffect(() => {
    // No selection or no height data yet - can't scroll properly
    if (selectedAnnotations.length === 0 || pageHeights.length === 0) return;
    if (selectedPageIdx === undefined) return;

    const targetId = selectedAnnotations[0];

    // 1. Scroll the container/window so the target page is visible
    const topOffset = Math.max(0, cumulative[selectedPageIdx] - 32);
    getScrollElement().scrollTo({ top: topOffset, behavior: "smooth" });

    // 2. Tell the PDFPage components to look for and center this annotation
    setPendingScrollId(targetId);
  }, [
    selectedAnnotations,
    selectedPageIdx,
    pageHeights,
    cumulative,
    zoomLevel,
    getScrollElement,
    setPendingScrollId,
  ]);

  /* 2. scroll container & notify pages (mirrors annotation logic) */
  useEffect(() => {
    if (
      selectedSearchPageIdx === undefined ||
      pageHeights.length === 0 ||
      selectedTextSearchMatchIndex === null
    )
      return;

    const topOffset = Math.max(0, cumulative[selectedSearchPageIdx] - 32);
    getScrollElement().scrollTo({ top: topOffset, behavior: "smooth" });

    setPendingScrollSearchId(String(selectedTextSearchMatchIndex));
  }, [
    selectedSearchPageIdx,
    selectedTextSearchMatchIndex,
    pageHeights,
    cumulative,
    getScrollElement,
    setPendingScrollSearchId,
  ]);

  /* 🚚 scroll the container and set the pending-scroll atom */
  useEffect(() => {
    if (
      selectedChatSourcePageIdx === undefined ||
      pageHeights.length === 0 ||
      selectedSourceIndex === null
    )
      return;

    const topOffset = Math.max(0, cumulative[selectedChatSourcePageIdx] - 32);
    getScrollElement().scrollTo({ top: topOffset, behavior: "smooth" });

    setPendingScrollChatSourceId(`${selectedMessageId}.${selectedSourceIndex}`);
  }, [
    selectedChatSourcePageIdx,
    selectedMessageId,
    selectedSourceIndex,
    pageHeights,
    cumulative,
    getScrollElement,
    setPendingScrollChatSourceId,
  ]);

  /* ---------- render -------------------------------------------------- */
  if (pageInfos.length === 0) return null;

  return (
    <div data-testid="pdf-annotator" style={{ position: "relative" }}>
      {pageInfos.map((pInfo, idx) => {
        const top = cumulative[idx];
        const height = pageHeights[idx];
        const visible = idx >= range[0] && idx <= range[1];

        return (
          <div
            key={pInfo.page.pageNumber}
            style={{
              position: "absolute",
              top,
              height,
              width: "100%",
            }}
          >
            {visible && (
              <PDFPage
                pageInfo={pInfo}
                read_only={read_only}
                onError={setViewStateError}
                containerWidth={containerWidth}
                createAnnotationHandler={createAnnotationHandler}
              />
            )}
          </div>
        );
      })}
      {/* spacer so the scroll container has correct total height */}
      <div style={{ height: cumulative[cumulative.length - 1] }} />
    </div>
  );
};

export const PageAnnotationsContainer = styled.div`
  position: relative;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  width: 100%;
  margin: 1rem 0;

  @media (max-width: 768px) {
    margin: 0.5rem 0;
    min-width: fit-content;
    /* Ensure container expands to fit content but allows scrolling */
    width: auto;
    justify-content: flex-start;
  }
`;

export const PageCanvas = styled.canvas`
  // Remove max-width so the canvas can exceed its parent's width
  // max-width: 100%;
  // height: auto;

  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(0, 0, 0, 0.1);
`;
