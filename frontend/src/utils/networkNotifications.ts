/**
 * networkNotifications - Centralized, reconnection-aware network toasts.
 *
 * Mobile devices suspend the page while the screen is locked. On unlock a burst
 * of in-flight queries can fail before connectivity re-establishes, producing a
 * stack of alarming red error toasts (see the screen-unlock issue #697 and its
 * follow-up). The helpers here gate transient network-error toasts behind a
 * shared "reconnecting" grace window:
 *
 * - While the app is knowingly reconnecting (page just resumed from background)
 *   or the browser reports being offline, scary error toasts are suppressed in
 *   favour of the single calm "Reconnecting…" indicator shown by
 *   NetworkStatusHandler.
 * - Genuine, persistent failures still surface once the window closes — but
 *   only ONCE, because every toast is given a stable id and therefore
 *   de-duplicates instead of stacking on each re-render.
 *
 * Related to Issue #697 - Error on screen unlock
 */

import { toast, type ToastOptions } from "react-toastify";
import { isReconnectingVar } from "../graphql/cache";

// ============================================================================
// Constants
// ============================================================================

/** Auto-close (ms) for a transient network-error toast shown outside the grace window. */
const TRANSIENT_ERROR_AUTOCLOSE_MS = 5000;

/**
 * Max time (ms) the reconnecting grace window stays armed before force-clearing.
 *
 * Safety net: a reconnect refetch that never settles must not be able to
 * suppress error toasts forever, so the window auto-disarms after this window
 * even if nothing explicitly clears it.
 */
const RECONNECT_MAX_WINDOW_MS = 10000;

// ============================================================================
// Reconnect grace window
// ============================================================================

let forceClearTimeout: ReturnType<typeof setTimeout> | null = null;

/**
 * Arm or disarm the reconnecting grace window.
 *
 * While armed, {@link notifyTransientNetworkError} suppresses alarming toasts.
 * Arming (re)starts a safety timeout that force-disarms the window after
 * {@link RECONNECT_MAX_WINDOW_MS}.
 */
export function setReconnecting(active: boolean): void {
  isReconnectingVar(active);

  if (forceClearTimeout) {
    clearTimeout(forceClearTimeout);
    forceClearTimeout = null;
  }

  if (active) {
    forceClearTimeout = setTimeout(() => {
      isReconnectingVar(false);
      forceClearTimeout = null;
    }, RECONNECT_MAX_WINDOW_MS);
  }
}

/**
 * Whether transient network errors should currently be suppressed.
 *
 * True when we're mid-reconnect, or when the browser reports being offline
 * (the offline state already shows its own single, dedicated toast).
 */
export function shouldSuppressNetworkError(): boolean {
  const offline =
    typeof navigator !== "undefined" && navigator.onLine === false;
  return isReconnectingVar() || offline;
}

// ============================================================================
// Notifications
// ============================================================================

/**
 * Show a network-error toast UNLESS we're mid-reconnect (or offline), in which
 * case the calm "Reconnecting…" / offline indicators already cover the
 * situation and a red error would just be alarming noise.
 *
 * A stable `toastId` (defaulting to the message text) is always set so repeated
 * render-time calls — e.g. `if (error) toast.error(...)` in a component body,
 * which re-fires on every re-render while `error` stays truthy — collapse into
 * a single toast instead of stacking.
 *
 * @param message - User-facing error text.
 * @param options - Standard react-toastify options. `toastId` is a stable
 *   de-dupe id that defaults to `message`; `autoClose` defaults to
 *   {@link TRANSIENT_ERROR_AUTOCLOSE_MS} but, like any other option, may be
 *   overridden by the caller.
 */
export function notifyTransientNetworkError(
  message: string,
  options: Omit<ToastOptions, "toastId"> & { toastId?: string } = {}
): void {
  if (shouldSuppressNetworkError()) {
    return;
  }

  const { toastId, ...rest } = options;
  toast.error(message, {
    autoClose: TRANSIENT_ERROR_AUTOCLOSE_MS,
    ...rest,
    toastId: toastId ?? message,
  });
}
