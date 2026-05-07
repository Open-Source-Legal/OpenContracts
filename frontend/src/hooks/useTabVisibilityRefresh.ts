import { useEffect } from "react";

type RefreshFn = () => Promise<unknown> | unknown;

/**
 * Calls each refresh function once whenever the page becomes visible again.
 * Used to replace fixed-interval polling with on-demand refreshes that hidden
 * tabs do not pay for.
 */
export function useTabVisibilityRefresh(refreshFns: RefreshFn[]): void {
  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") return;
      for (const fn of refreshFns) {
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
  }, [refreshFns]);
}
