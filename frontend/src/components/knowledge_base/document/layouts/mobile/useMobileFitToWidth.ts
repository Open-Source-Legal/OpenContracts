import { useCallback, useEffect, useRef } from "react";
import {
  usePages,
  useScrollContainerRef,
} from "../../../../annotator/context/DocumentAtom";
import {
  ZOOM_MIN,
  ZOOM_MAX,
  FIT_WIDTH_MARGIN,
} from "../../../../../assets/configurations/constants";

interface UseMobileFitToWidthParams {
  /** Whether the Document surface is the active mobile tab. */
  active: boolean;
  /** Canonical zoom setter (writes the same atom the PDF renderer reads). */
  setZoomLevel: (zoom: number) => void;
}

interface UseMobileFitToWidthReturn {
  /** Imperatively fit the document to the current viewer width. */
  fitToWidth: () => void;
}

/**
 * Fit-to-width zoom for the mobile Document surface.
 *
 * The PDF renderer applies `zoomLevel` directly as the page scale — at the
 * desktop default of 1.0 a letter-size page is ~816px wide, far wider than a
 * ~390px phone viewport, so the document opens unreadably zoomed. This hook
 * computes the scale that makes the first page exactly fill the measured
 * viewer width and applies it:
 *
 *  - **on mount / first measurement** — once both the page geometry and the
 *    container width are known, so the document is readable on load;
 *  - **imperatively** via {@link UseMobileFitToWidthReturn.fitToWidth} — wired
 *    to the toolbar's "Fit width" chip.
 *
 * It does not auto-zoom on every resize: after the initial fit the user owns
 * the zoom (pinch-zoom, the Fit chip). `active` gates the one-shot mount fit so
 * it only fires while the Document tab is showing.
 */
export function useMobileFitToWidth({
  active,
  setZoomLevel,
}: UseMobileFitToWidthParams): UseMobileFitToWidthReturn {
  const { pages } = usePages();
  const { scrollContainerRef } = useScrollContainerRef();
  const didInitialFitRef = useRef(false);

  /** Compute the fit-to-width zoom, or null if geometry isn't ready yet. */
  const computeFitZoom = useCallback((): number | null => {
    const firstPage = pages[0];
    const container = scrollContainerRef?.current;
    if (!firstPage || !container) return null;

    // `firstPage.page` is a PDF.js PDFPageProxy that can be destroyed between
    // this guard and the call (navigation / unmount). A destroyed proxy throws
    // from getViewport — treat that the same as "geometry not ready".
    let pageWidth: number;
    try {
      pageWidth = firstPage.page.getViewport({ scale: 1 }).width;
    } catch {
      return null;
    }
    const containerWidth = container.getBoundingClientRect().width;
    if (!pageWidth || !containerWidth) return null;

    const raw = (containerWidth - FIT_WIDTH_MARGIN) / pageWidth;
    return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, raw));
  }, [pages, scrollContainerRef]);

  const fitToWidth = useCallback(() => {
    const zoom = computeFitZoom();
    if (zoom !== null) setZoomLevel(zoom);
  }, [computeFitZoom, setZoomLevel]);

  // One-shot fit once the document geometry is available on the active tab.
  useEffect(() => {
    if (!active || didInitialFitRef.current) return;
    const zoom = computeFitZoom();
    if (zoom !== null) {
      didInitialFitRef.current = true;
      setZoomLevel(zoom);
    }
  }, [active, computeFitZoom, setZoomLevel]);

  return { fitToWidth };
}
