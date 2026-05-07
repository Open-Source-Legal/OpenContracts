import { useEffect, useRef } from "react";
import { useInView } from "react-cool-inview";

interface FetchMoreOnVisibleProps {
  fetchNextPage?: () => void | any;
  fetchPreviousPage?: () => void | any;
  triggerOnce?: boolean;
  fetchWithoutMotion?: boolean;
  threshold?: number;
  /**
   * IntersectionObserver `rootMargin`. Defaults to `200px 0px` so the sentinel
   * fires before the user reaches the absolute bottom of the list and gives
   * the next page time to load while the user is still scrolling.
   */
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
  // Hold the latest callbacks in refs so the effect below never invokes a
  // stale closure. Parent components routinely re-create these handlers via
  // `useCallback` whenever their loading/data deps change (e.g. Apollo's
  // `loading` toggling true→false during `fetchMore`); without the refs the
  // observer effect — whose deps deliberately don't include the callbacks —
  // would call whichever closure was captured the first time `inView` flipped,
  // which can hold an outdated `loading` flag or cursor and silently no-op.
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
