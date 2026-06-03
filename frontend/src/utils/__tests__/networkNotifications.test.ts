/**
 * Tests for the reconnection-aware network notification helpers.
 *
 * Verifies that transient network-error toasts are suppressed while the app is
 * knowingly reconnecting (mobile screen-unlock) or offline, and that repeated
 * render-time calls de-duplicate via a stable toast id.
 *
 * Related to Issue #697 - Error on screen unlock
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { toast } from "react-toastify";
import {
  notifyTransientNetworkError,
  setReconnecting,
  shouldSuppressNetworkError,
} from "../networkNotifications";
import { isReconnectingVar } from "../../graphql/cache";

vi.mock("react-toastify", () => ({
  toast: {
    error: vi.fn(),
  },
}));

describe("networkNotifications", () => {
  let originalOnLine: PropertyDescriptor | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    // Ensure a clean grace-window state between tests. Go through
    // setReconnecting (not isReconnectingVar directly) so any pending safety
    // timeout left armed by a prior test is force-cleared too.
    setReconnecting(false);

    originalOnLine = Object.getOwnPropertyDescriptor(navigator, "onLine");
    Object.defineProperty(navigator, "onLine", {
      value: true,
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    setReconnecting(false);
    vi.useRealTimers();
    if (originalOnLine) {
      Object.defineProperty(navigator, "onLine", originalOnLine);
    }
  });

  const setOnLine = (value: boolean) =>
    Object.defineProperty(navigator, "onLine", {
      value,
      writable: true,
      configurable: true,
    });

  describe("notifyTransientNetworkError", () => {
    it("shows a toast when online and not reconnecting", () => {
      notifyTransientNetworkError("Boom", { toastId: "boom" });

      expect(toast.error).toHaveBeenCalledWith("Boom", {
        toastId: "boom",
        autoClose: 5000,
      });
    });

    it("defaults the toastId to the message so repeats de-duplicate", () => {
      notifyTransientNetworkError("Same message");

      expect(toast.error).toHaveBeenCalledWith("Same message", {
        toastId: "Same message",
        autoClose: 5000,
      });
    });

    it("emits a stable toast id on every repeat so the toasts de-duplicate", () => {
      // Simulates the same component re-rendering while `error` stays truthy.
      // react-toastify is mocked here, so the actual collapse-into-one happens
      // in the real lib via `toastId`; what we assert is the contract that makes
      // it possible — every call carries the SAME stable id (not a fresh one).
      notifyTransientNetworkError("Unable to fetch corpuses.");
      notifyTransientNetworkError("Unable to fetch corpuses.");
      notifyTransientNetworkError("Unable to fetch corpuses.");

      expect(toast.error).toHaveBeenCalledTimes(3);
      const ids = (toast.error as ReturnType<typeof vi.fn>).mock.calls.map(
        ([, opts]) => (opts as { toastId?: string }).toastId
      );
      expect(new Set(ids)).toEqual(new Set(["Unable to fetch corpuses."]));
    });

    it("suppresses the toast while reconnecting", () => {
      setReconnecting(true);

      notifyTransientNetworkError("Boom", { toastId: "boom" });

      expect(toast.error).not.toHaveBeenCalled();
    });

    it("suppresses the toast while offline", () => {
      setOnLine(false);

      notifyTransientNetworkError("Boom", { toastId: "boom" });

      expect(toast.error).not.toHaveBeenCalled();
    });

    it("resumes showing toasts once the grace window is disarmed", () => {
      setReconnecting(true);
      notifyTransientNetworkError("Boom", { toastId: "boom" });
      expect(toast.error).not.toHaveBeenCalled();

      setReconnecting(false);
      notifyTransientNetworkError("Boom", { toastId: "boom" });
      expect(toast.error).toHaveBeenCalledTimes(1);
    });
  });

  describe("setReconnecting", () => {
    it("toggles the shared reconnecting reactive var", () => {
      expect(isReconnectingVar()).toBe(false);

      setReconnecting(true);
      expect(isReconnectingVar()).toBe(true);
      expect(shouldSuppressNetworkError()).toBe(true);

      setReconnecting(false);
      expect(isReconnectingVar()).toBe(false);
    });

    it("auto-disarms after the safety window so errors are never suppressed forever", () => {
      setReconnecting(true);
      expect(isReconnectingVar()).toBe(true);

      // Advance past the 10s safety window.
      vi.advanceTimersByTime(10000);

      expect(isReconnectingVar()).toBe(false);
    });
  });
});
