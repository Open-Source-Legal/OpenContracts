import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react-hooks";

/**
 * Mock dependencies before the hook is imported so its module-level
 * references pick up the stubs.
 *   - react-toastify: the hook calls `toast(...)` with a BadgeToast element.
 *   - BadgeToast component: uses icon libraries / styled-components we don't
 *     want to exercise in a unit test.
 */
const toastMock = vi.fn();
vi.mock("react-toastify", () => ({
  toast: (...args: unknown[]) => toastMock(...args),
}));

vi.mock("../../components/badges/BadgeToast", () => ({
  BadgeToast: (props: any) =>
    React.createElement("div", { "data-testid": "toast", ...props }),
}));

import { useBadgeCelebration } from "../useBadgeCelebration";
import type { BadgeNotification } from "../useBadgeNotifications";

function makeBadge(id: string, isAutoAwarded = false): BadgeNotification {
  return {
    id,
    badgeId: "b-" + id,
    badgeName: "Badge " + id,
    badgeDescription: "desc",
    badgeIcon: "Award",
    badgeColor: "#ff0000",
    isAutoAwarded,
    awardedAt: "2024-01-01T00:00:00Z",
  };
}

describe("useBadgeCelebration", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    toastMock.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts with an empty celebration state", () => {
    const { result } = renderHook(() => useBadgeCelebration([]));
    expect(result.current.showModal).toBe(false);
    expect(result.current.currentBadge).toBeNull();
    expect(result.current.queueLength).toBe(0);
  });

  it("enqueues and displays a toast after the queue delay", () => {
    const { result, rerender } = renderHook(
      ({ badges }) => useBadgeCelebration(badges, { queueDelay: 500 }),
      { initialProps: { badges: [] as BadgeNotification[] } }
    );

    rerender({ badges: [makeBadge("1")] });

    // Before the delay, nothing should have toasted yet.
    expect(toastMock).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(toastMock).toHaveBeenCalledTimes(1);
    // Single badge (length === 1) should also trigger the modal.
    expect(result.current.showModal).toBe(true);
    expect(result.current.currentBadge?.id).toBe("1");
  });

  it("opens the celebration modal for auto-awarded badges", () => {
    const { result, rerender } = renderHook(
      ({ badges }) => useBadgeCelebration(badges, { queueDelay: 100 }),
      { initialProps: { badges: [] as BadgeNotification[] } }
    );
    rerender({
      badges: [makeBadge("a", true), makeBadge("b", false)],
    });

    act(() => {
      vi.runAllTimers();
    });

    expect(result.current.showModal).toBe(true);
    expect(result.current.currentBadge?.id).toBe("a");
  });

  it("dedupes badges already shown", () => {
    const { rerender } = renderHook(
      ({ badges }) => useBadgeCelebration(badges, { queueDelay: 10 }),
      { initialProps: { badges: [makeBadge("1")] as BadgeNotification[] } }
    );

    act(() => {
      vi.runAllTimers();
    });
    expect(toastMock).toHaveBeenCalledTimes(1);

    // Providing the same badge again should not re-toast.
    rerender({ badges: [makeBadge("1")] });
    act(() => {
      vi.runAllTimers();
    });
    expect(toastMock).toHaveBeenCalledTimes(1);
  });

  it("respects showToast=false option", () => {
    const { rerender } = renderHook(
      ({ badges }) =>
        useBadgeCelebration(badges, { showToast: false, queueDelay: 10 }),
      { initialProps: { badges: [] as BadgeNotification[] } }
    );
    rerender({ badges: [makeBadge("x")] });
    act(() => {
      vi.runAllTimers();
    });
    expect(toastMock).not.toHaveBeenCalled();
  });

  it("closeModal clears modal state", () => {
    const { result, rerender } = renderHook(
      ({ badges }) => useBadgeCelebration(badges, { queueDelay: 10 }),
      { initialProps: { badges: [] as BadgeNotification[] } }
    );
    rerender({ badges: [makeBadge("m", true)] });
    act(() => {
      vi.runAllTimers();
    });
    expect(result.current.showModal).toBe(true);

    act(() => {
      result.current.closeModal();
    });
    expect(result.current.showModal).toBe(false);
    expect(result.current.currentBadge).toBeNull();
  });

  it("dismissAll empties queue and modal state", () => {
    const { result, rerender } = renderHook(
      ({ badges }) => useBadgeCelebration(badges, { queueDelay: 1000 }),
      { initialProps: { badges: [] as BadgeNotification[] } }
    );
    rerender({
      badges: [makeBadge("a"), makeBadge("b"), makeBadge("c")],
    });
    // Queue has been appended, but modal hasn't opened yet (delay pending).
    expect(result.current.queueLength).toBe(3);

    act(() => {
      result.current.dismissAll();
    });
    expect(result.current.queueLength).toBe(0);
    expect(result.current.showModal).toBe(false);
    expect(result.current.currentBadge).toBeNull();
  });
});
