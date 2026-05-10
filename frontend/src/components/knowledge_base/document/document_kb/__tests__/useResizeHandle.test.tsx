import { renderHook, act } from "../../../../../test-utils/renderHook";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { useResizeHandle } from "../useResizeHandle";

const fireMouse = (type: "mousemove" | "mouseup", clientX = 0) => {
  document.dispatchEvent(
    Object.assign(new Event(type, { bubbles: true }), {
      clientX,
    })
  );
};

const buildArgs = (initialWidthPct = 50) => {
  const setMode = vi.fn();
  const setCustomWidth = vi.fn();
  const getPanelWidthPercentage = vi.fn(() => initialWidthPct);
  return { setMode, setCustomWidth, getPanelWidthPercentage };
};

const startDrag = (
  result: ReturnType<
    typeof renderHook<unknown, ReturnType<typeof useResizeHandle>>
  >["result"],
  clientX = 1000,
  target?: HTMLElement
) => {
  act(() => {
    result.current.handleResizeStart({
      clientX,
      preventDefault: vi.fn(),
      target: target ?? document.createElement("div"),
    } as unknown as React.MouseEvent);
  });
};

describe("useResizeHandle", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", {
      value: 1000,
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("ignores mousedown that originates on a button", () => {
    const args = buildArgs();
    const { result } = renderHook(() => useResizeHandle(args));

    const button = document.createElement("button");
    const target = document.createElement("span");
    button.appendChild(target);
    document.body.appendChild(button);

    startDrag(result, 500, target);

    expect(result.current.isDragging).toBe(false);
    expect(args.getPanelWidthPercentage).not.toHaveBeenCalled();

    document.body.removeChild(button);
  });

  it("flips into dragging state and snapshots the initial width on mousedown", () => {
    const args = buildArgs(50);
    const { result } = renderHook(() => useResizeHandle(args));

    startDrag(result, 800);

    expect(result.current.isDragging).toBe(true);
    expect(args.getPanelWidthPercentage).toHaveBeenCalledTimes(1);
  });

  it("snaps to 'quarter' when mouse delta lands within threshold of 25%", () => {
    const args = buildArgs(50);
    const { result } = renderHook(() => useResizeHandle(args));
    startDrag(result, 800);

    // moving cursor +250px right reduces panel width by 25% (innerWidth=1000)
    // so 50 - 25 = 25%, which snaps to quarter.
    act(() => fireMouse("mousemove", 1050));

    expect(args.setMode).toHaveBeenLastCalledWith("quarter");
    expect(args.setCustomWidth).not.toHaveBeenCalled();
  });

  it("snaps to 'half' near 50% and 'full' near 90%", () => {
    const args = buildArgs(50);
    const { result } = renderHook(() => useResizeHandle(args));
    startDrag(result, 800);

    act(() => fireMouse("mousemove", 800)); // delta=0 → 50%
    expect(args.setMode).toHaveBeenLastCalledWith("half");

    // From 50, push left by 400px (delta=400) → newWidth = 50 + 40 = 90%
    act(() => fireMouse("mousemove", 400));
    expect(args.setMode).toHaveBeenLastCalledWith("full");
  });

  it("commits a custom width when the cursor sits outside any snap band", () => {
    const args = buildArgs(50);
    const { result } = renderHook(() => useResizeHandle(args));
    startDrag(result, 800);

    // delta=100 (cursor moves 100px left) → newWidth = 50 + 10 = 60%
    act(() => fireMouse("mousemove", 700));
    expect(args.setCustomWidth).toHaveBeenLastCalledWith(60);
    expect(args.setMode).not.toHaveBeenCalled();
  });

  it("clamps width between 15% and 95% before snap evaluation", () => {
    const args = buildArgs(50);
    const { result } = renderHook(() => useResizeHandle(args));
    startDrag(result, 800);

    // Massive delta to the right: would compute below 15%, expect clamp.
    act(() => fireMouse("mousemove", 5000));
    expect(args.setCustomWidth).toHaveBeenLastCalledWith(15);

    // Massive delta to the left: would compute above 95%, expect clamp.
    act(() => fireMouse("mousemove", -5000));
    expect(args.setCustomWidth).toHaveBeenLastCalledWith(95);
  });

  it("ignores mousemove until a drag has been started", () => {
    const args = buildArgs(50);
    const { result } = renderHook(() => useResizeHandle(args));

    act(() => fireMouse("mousemove", 50));

    expect(result.current.isDragging).toBe(false);
    expect(args.setMode).not.toHaveBeenCalled();
    expect(args.setCustomWidth).not.toHaveBeenCalled();
  });

  it("releases on mouseup and detaches global listeners", () => {
    const args = buildArgs(50);
    const { result } = renderHook(() => useResizeHandle(args));
    startDrag(result, 800);
    expect(result.current.isDragging).toBe(true);

    act(() => fireMouse("mouseup"));
    expect(result.current.isDragging).toBe(false);

    // After mouseup the move handler must no longer call setters.
    args.setCustomWidth.mockClear();
    args.setMode.mockClear();
    act(() => fireMouse("mousemove", 0));
    expect(args.setCustomWidth).not.toHaveBeenCalled();
    expect(args.setMode).not.toHaveBeenCalled();
  });
});
