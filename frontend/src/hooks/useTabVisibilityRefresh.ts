import { useEffect, useRef } from "react";

type RefreshFn = () => Promise<unknown> | unknown;

/**
 * Calls each refresh function once whenever the page becomes visible again.
 * Used to replace fixed-interval polling with on-demand refreshes that hidden
 * tabs do not pay for.
 *
 * Internally keeps a ref to the latest ``refreshFns`` array so callers do
 * not need to memoize: the listener is registered once on mount and reads
 * the current array on every visibility transition.
 */
export function useTabVisibilityRefresh(refreshFns: RefreshFn[]): void {
  const refreshFnsRef = useRef(refreshFns);
  refreshFnsRef.current = refreshFns;

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") return;
      for (const fn of refreshFnsRef.current) {
        try {
          const result = fn();
          if (
            result &&
            typeof (result as Promise<unknown>).catch === "function"
          ) {
            (result as Promise<unknown>).catch(() => {
              /* swallow — caller's query state will surface the error */
            });
          }
        } catch {
          /* swallow — sync throw should not break listener */
        }
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, []);
}
