/**
 * NetworkStatusHandler - Component that handles network recovery and reconnection.
 *
 * This component monitors page visibility and network status changes, and
 * automatically refetches active Apollo Client queries when:
 * - The page becomes visible after being hidden (e.g., screen unlock on mobile)
 * - The network comes back online after being offline
 *
 * It also displays toast notifications to inform users of connectivity changes.
 *
 * Related to Issue #697 - Error on screen unlock
 */

import { useCallback, useRef } from "react";
import { useApolloClient } from "@apollo/client";
import { toast } from "react-toastify";
import { useNetworkStatus } from "../../hooks/useNetworkStatus";
import { setReconnecting } from "../../utils/networkNotifications";

// ============================================================================
// Constants
// ============================================================================

/** Toast IDs for network status notifications */
const TOAST_IDS = {
  RECONNECTING: "network-reconnecting",
  ONLINE: "network-online",
  OFFLINE: "network-offline",
} as const;

/**
 * Delay (ms) after a reconnect refetch settles before the "reconnecting" grace
 * window is disarmed.
 *
 * Queries that failed-then-(maybe)-succeeded during the reconnect emit a
 * trailing error render as their state settles; keeping the window armed a
 * little longer lets {@link notifyTransientNetworkError} swallow that final
 * flicker instead of flashing a red toast right as we recover.
 */
const RECONNECT_TRAILING_DELAY = 1500;

/**
 * Delay (ms) before refetching after network comes online.
 *
 * This 500ms stabilization delay allows the network connection to fully establish
 * before attempting to refetch queries. Mobile networks often need a brief period
 * after the 'online' event fires to complete handshakes and routing table updates.
 * Testing on various mobile devices showed 500ms provides a good balance between
 * responsiveness and reliability.
 */
const NETWORK_STABILIZATION_DELAY = 500;

/**
 * Props for the NetworkStatusHandler component.
 */
export interface NetworkStatusHandlerProps {
  /** Minimum time (ms) hidden before triggering a refetch (default: 2000) */
  resumeThreshold?: number;
  /** Whether to show toast notifications (default: true) */
  showToasts?: boolean;
  /** Whether to refetch queries on resume (default: true) */
  refetchOnResume?: boolean;
  /** Whether to refetch queries when coming back online (default: true) */
  refetchOnOnline?: boolean;
  /** Debounce interval (ms) for refetch operations to prevent rapid repeated calls (default: 2000) */
  refetchDebounceMs?: number;
}

/**
 * Component that handles network recovery and reconnection.
 *
 * This component should be placed inside the ApolloProvider to have access
 * to the Apollo Client for refetching queries.
 *
 * @example
 * ```tsx
 * <ApolloProvider client={client}>
 *   <NetworkStatusHandler />
 *   <App />
 * </ApolloProvider>
 * ```
 */
export function NetworkStatusHandler({
  resumeThreshold = 2000,
  showToasts = true,
  refetchOnResume = true,
  refetchOnOnline = true,
  refetchDebounceMs = 2000,
}: NetworkStatusHandlerProps = {}) {
  const client = useApolloClient();

  // Track if we've shown the offline toast to avoid duplicates
  const offlineToastShownRef = useRef(false);
  // Track last refetch time to debounce
  const lastRefetchRef = useRef(0);

  /**
   * Refetch all active queries with debouncing.
   */
  const refetchActiveQueries = useCallback(
    async (reason: string) => {
      const now = Date.now();
      // Debounce: don't refetch if we just did within the debounce interval
      if (now - lastRefetchRef.current < refetchDebounceMs) {
        console.debug(
          `[NetworkStatusHandler] Skipping refetch (debounced): ${reason}`
        );
        return;
      }
      lastRefetchRef.current = now;

      // Arm the reconnect grace window: while a reconnect refetch is in flight,
      // the queries it re-runs may briefly fail and trigger component-level
      // error toasts. Suppress those (and errorLink's network-error toast) in
      // favour of the single calm "Reconnecting…" indicator below.
      //
      // Intentionally NOT gated on `showToasts`: the window only suppresses
      // *other* surfaces' toasts (errorLink, per-query card errors), which are
      // global and exist regardless of this handler's `showToasts` prop. A
      // consumer passing `showToasts={false}` only silences this handler's own
      // status toasts, not those independent error surfaces, so the grace
      // window must still arm to keep them quiet during reconnect.
      setReconnecting(true);

      try {
        console.debug(
          `[NetworkStatusHandler] Refetching active queries: ${reason}`
        );

        // Refetch all active (observed) queries
        // This will re-execute queries that components are currently watching
        await client.refetchQueries({
          include: "active",
        });

        console.debug("[NetworkStatusHandler] Refetch completed successfully");
      } catch (error) {
        // Deliberately quiet: a refetch failure here means the connection is
        // still flaky right after resuming/coming online. We do NOT throw a
        // red "reload the page" toast at the user mid-reconnect — the calm
        // "Reconnecting…" indicator already conveys state, and any genuinely
        // persistent failure surfaces (once) via the normal per-query error
        // toasts after the grace window closes.
        console.error(
          "[NetworkStatusHandler] Error refetching queries:",
          error
        );
      } finally {
        // Keep the window armed briefly so the trailing error render from
        // queries that just settled stays suppressed, then disarm.
        setTimeout(() => setReconnecting(false), RECONNECT_TRAILING_DELAY);
      }
    },
    [client, refetchDebounceMs]
  );

  /**
   * Handle page resume (visibility change from hidden to visible).
   */
  const handleResume = useCallback(() => {
    console.debug("[NetworkStatusHandler] Page resumed from background");

    if (!refetchOnResume) {
      return;
    }

    // Check if we're online before attempting refetch
    if (!navigator.onLine) {
      console.debug(
        "[NetworkStatusHandler] Skipping refetch: device is offline"
      );
      return;
    }

    // Refetch active queries to get fresh data
    refetchActiveQueries("page resumed from background");

    // Show a subtle notification that we're reconnecting
    if (showToasts) {
      toast.info("Reconnecting...", {
        toastId: TOAST_IDS.RECONNECTING,
        autoClose: 1500,
        position: "bottom-right",
      });
    }
  }, [refetchOnResume, refetchActiveQueries, showToasts]);

  /**
   * Handle page hide (visibility change from visible to hidden).
   */
  const handleHide = useCallback(() => {
    console.debug("[NetworkStatusHandler] Page hidden");
    // We could optionally pause polling queries here, but for now we just log
  }, []);

  /**
   * Handle network coming back online.
   */
  const handleOnline = useCallback(() => {
    console.debug("[NetworkStatusHandler] Network came online");

    // Clear the offline toast tracking
    offlineToastShownRef.current = false;

    if (showToasts) {
      // Dismiss any offline toast
      toast.dismiss(TOAST_IDS.OFFLINE);

      toast.success("Connection restored", {
        toastId: TOAST_IDS.ONLINE,
        autoClose: 3000,
        position: "bottom-right",
      });
    }

    if (refetchOnOnline) {
      // Slight delay to allow network to stabilize
      setTimeout(() => {
        refetchActiveQueries("network came online");
      }, NETWORK_STABILIZATION_DELAY);
    }
  }, [showToasts, refetchOnOnline, refetchActiveQueries]);

  /**
   * Handle network going offline.
   */
  const handleOffline = useCallback(() => {
    console.debug("[NetworkStatusHandler] Network went offline");

    if (showToasts && !offlineToastShownRef.current) {
      offlineToastShownRef.current = true;

      toast.warning("You appear to be offline. Some features may not work.", {
        toastId: TOAST_IDS.OFFLINE,
        autoClose: false, // Keep visible until online
        position: "bottom-right",
      });
    }
  }, [showToasts]);

  // Set up the network status monitoring
  useNetworkStatus({
    onResume: handleResume,
    onHide: handleHide,
    onOnline: handleOnline,
    onOffline: handleOffline,
    resumeThreshold,
    enabled: true,
  });

  // This component doesn't render anything
  return null;
}

export default NetworkStatusHandler;
