import { useEffect, useRef } from "react";
import { useInView } from "react-cool-inview";

interface FetchMoreOnVisibleProps {
  fetchNextPage?: () => void | any;
  fetchPreviousPage?: () => void | any;
  triggerOnce?: boolean;
  fetchWithoutMotion?: boolean;
  threshold?: number;
  // Prefetch buffer for the IntersectionObserver sentinel.
  rootMargin?: string;
  style?: Record<any, any>;
}

// Suggest this library for directionality:
// https://github.com/wellyshen/react-cool-inview

export const FetchMoreOnVisible = ({
  fetchNextPage,
  fetchPreviousPage,
  triggerOnce,
  threshold = 0.25,
  rootMargin = "200px 0px",
  fetchWithoutMotion,
  style,
}: FetchMoreOnVisibleProps) => {
  // Refs hold the latest callbacks so the effect never invokes a stale closure.
  const fetchNextRef = useRef(fetchNextPage);
  const fetchPrevRef = useRef(fetchPreviousPage);
  fetchNextRef.current = fetchNextPage;
  fetchPrevRef.current = fetchPreviousPage;

  const {
    observe,
    inView,
    scrollDirection: { vertical },
    entry,
  } = useInView({
    threshold,
    rootMargin,
    unobserveOnEnter: triggerOnce,
  });

  // NOTE - react-cool-inview's definition of vertical scroll direction - e.g. up or down -
  // is the opposite of what I'd use. When you're scrolling "up" the document - e.g. from higher
  // numbered pages to lower numbered pages, that is defined as "down". I guess that makes sense
  // because the canvas itself is moving from top to bottom of screen.

  useEffect(() => {
    if (!inView) return;
    if (vertical === undefined && fetchWithoutMotion) {
      if (fetchNextRef.current !== undefined) {
        fetchNextRef.current();
      } else if (fetchPrevRef.current !== undefined) {
        fetchPrevRef.current();
      }
    } else if (vertical !== undefined) {
      if (vertical === "up" && fetchNextRef.current !== undefined) {
        fetchNextRef.current();
      } else if (vertical === "down" && fetchPrevRef.current !== undefined) {
        fetchPrevRef.current();
      }
    }
  }, [entry, vertical, inView, fetchWithoutMotion]);

  return (
    <div
      style={{
        height: "1px",
        ...(style ? style : {}),
      }}
      ref={observe}
      className="FetchMoreOnVisible"
    />
  );
};
