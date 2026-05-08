import { useCallback, useEffect, useRef, useState } from "react";
import { useScrollContainerRef } from "../../../annotator/context/DocumentAtom";

interface UseContainerWidthReturn {
  /** Most recent measured width of the container, in CSS pixels (null until first measure). */
  containerWidth: number | null;
  /** Ref callback to attach to the container element. */
  containerRefCallback: React.RefCallback<HTMLDivElement>;
}

/**
 * Tracks the live width of the document viewer's container and republishes
 * the element to `scrollContainerRefAtom` so the virtual page renderer can
 * read it for visibility math.
 *
 * The width updates on two triggers:
 * 1. The ref callback fires (mount/unmount) — captures the initial width.
 * 2. A `ResizeObserver` fires when the layout reflows (sidebar open/close,
 *    window resize) — keeps the fit-to-width zoom calculation accurate.
 *
 * On unmount the scroll container ref is cleared so stale element refs
 * don't leak across document navigations.
 */
export function useContainerWidth(): UseContainerWidthReturn {
  const [containerWidth, setContainerWidth] = useState<number | null>(null);
  const { setScrollContainerRef } = useScrollContainerRef();
  const pdfContainerRef = useRef<HTMLDivElement | null>(null);

  const containerRefCallback = useCallback(
    (node: HTMLDivElement | null) => {
      pdfContainerRef.current = node;
      if (node) {
        setContainerWidth(node.getBoundingClientRect().width);
        setScrollContainerRef(pdfContainerRef);
      } else {
        setScrollContainerRef(null);
      }
    },
    [setScrollContainerRef]
  );

  useEffect(() => {
    const node = pdfContainerRef.current;
    if (!node) return;
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    resizeObserver.observe(node);
    return () => resizeObserver.disconnect();
  }, []);

  // Clear on unmount so stale refs are never used.
  useEffect(() => () => setScrollContainerRef(null), [setScrollContainerRef]);

  return { containerWidth, containerRefCallback };
}
