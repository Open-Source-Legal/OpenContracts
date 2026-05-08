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
 *
 * Notes for callers:
 * - No initial-mount fetch is fired here. Components that mount in an
 *   already-visible tab rely on Apollo's ``cache-and-network`` (or similar)
 *   fetch policy on the underlying queries to populate state on first render;
 *   this hook only handles subsequent ``hidden → visible`` transitions.
 * - Rapid tab-switching can fire multiple ``visibilitychange`` events in
 *   quick succession. There is no internal debounce — Apollo's query
 *   deduplication absorbs concurrent identical refetches in practice.
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
            // Log unconditionally — production swallowing makes a
            // consistently failing refresh (torn-down query, network
            // outage) silent forever. Sentry / browser consoles surface
            // ``console.error`` for diagnosis.
            (result as Promise<unknown>).catch((err) => {
              console.error(
                "[useTabVisibilityRefresh] refresh promise rejected:",
                err
              );
            });
          }
        } catch (err) {
          console.error(
            "[useTabVisibilityRefresh] refresh threw synchronously:",
            err
          );
        }
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, []);
}
