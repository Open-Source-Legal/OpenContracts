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
 * The `ResizeObserver` is created/disposed inside the ref callback rather
 * than a `useEffect`, so it correctly reattaches if the container is
 * conditionally re-rendered (e.g. when the user swaps file types).
 *
 * On unmount the scroll container ref is cleared so stale element refs
 * don't leak across document navigations.
 */
export function useContainerWidth(): UseContainerWidthReturn {
  const [containerWidth, setContainerWidth] = useState<number | null>(null);
  const { setScrollContainerRef } = useScrollContainerRef();
  const pdfContainerRef = useRef<HTMLDivElement | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  const containerRefCallback = useCallback(
    (node: HTMLDivElement | null) => {
      // Tear down any previous observer before swapping nodes.
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;

      pdfContainerRef.current = node;
      if (node) {
        setContainerWidth(node.getBoundingClientRect().width);
        setScrollContainerRef(pdfContainerRef);

        const observer = new ResizeObserver((entries) => {
          for (const entry of entries) {
            setContainerWidth(entry.contentRect.width);
          }
        });
        observer.observe(node);
        resizeObserverRef.current = observer;
      } else {
        setScrollContainerRef(null);
      }
    },
    [setScrollContainerRef]
  );

  // Clear on unmount so stale refs are never used and observers don't leak.
  useEffect(
    () => () => {
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
      setScrollContainerRef(null);
    },
    [setScrollContainerRef]
  );

  return { containerWidth, containerRefCallback };
}
