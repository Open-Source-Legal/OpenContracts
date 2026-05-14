/**
 * Unit tests for SelectionBoundary click semantics.
 *
 * Covers the ``clickThroughOnPlainClick`` prop introduced for OC_URL
 * hyperlink annotations: plain (non-shift) clicks must fire ``onClick``
 * when the prop is on, but stay inert otherwise. Exercising both branches
 * pins the behaviour that lets clickable-link annotations open without
 * accidentally invading the normal selection-only semantics.
 */
import React from "react";
import { render, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { SelectionBoundary } from "../SelectionBoundary";

vi.mock("../../../hooks/useAnnotationRefs", () => ({
  useAnnotationRefs: () => ({
    registerRef: vi.fn(),
    unregisterRef: vi.fn(),
  }),
}));

vi.mock("jotai", async () => {
  const actual = await vi.importActual<typeof import("jotai")>("jotai");
  return {
    ...actual,
    // ``isCreatingAnnotation`` is read via ``useAtomValue`` — return
    // ``false`` so the click path is not short-circuited by the
    // "drawing a new selection" branch.
    useAtomValue: vi.fn(() => false),
  };
});

const bounds = { left: 0, top: 0, right: 100, bottom: 50 };

// Required props that every test needs — extracted so the per-test JSX
// stays focused on the prop under test (clickThroughOnPlainClick, etc.).
const baseProps = {
  hidden: false,
  selected: false,
} as const;

describe("SelectionBoundary click semantics", () => {
  it("does NOT call onClick on a plain click by default", () => {
    const onClick = vi.fn();
    const { container } = render(
      <SelectionBoundary
        {...baseProps}
        id="b1"
        color="#0066cc"
        bounds={bounds}
        onClick={onClick}
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    fireEvent.click(span);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("calls onClick on a shift-click (default behaviour)", () => {
    const onClick = vi.fn();
    const { container } = render(
      <SelectionBoundary
        {...baseProps}
        id="b2"
        color="#0066cc"
        bounds={bounds}
        onClick={onClick}
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    fireEvent.click(span, { shiftKey: true });
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("calls onClick on a plain click when clickThroughOnPlainClick is true", () => {
    // OC_URL hyperlink path: the surrounding renderer wires
    // ``clickThroughOnPlainClick`` so a plain click opens the URL.
    const onClick = vi.fn();
    const { container } = render(
      <SelectionBoundary
        {...baseProps}
        id="b3"
        color="#0066cc"
        bounds={bounds}
        onClick={onClick}
        clickThroughOnPlainClick
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    fireEvent.click(span);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("shows pointer cursor when clickThroughOnPlainClick is true", () => {
    // Visible affordance: hyperlink-style annotations must use a pointer
    // cursor so the user knows the span is clickable.
    const { container } = render(
      <SelectionBoundary
        {...baseProps}
        id="b4"
        color="#0066cc"
        bounds={bounds}
        onClick={vi.fn()}
        clickThroughOnPlainClick
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    expect(span.style.cursor).toBe("pointer");
  });

  it("does NOT set pointer cursor when clickThroughOnPlainClick is false", () => {
    const { container } = render(
      <SelectionBoundary
        {...baseProps}
        id="b5"
        color="#0066cc"
        bounds={bounds}
        onClick={vi.fn()}
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    expect(span.style.cursor).toBe("");
  });

  it("noop on mouseDown without onClick prop", () => {
    // ``handleMouseDown``'s early-return when ``!onClick`` is the
    // codecov-flagged guard branch. Just rendering without onClick and
    // firing the event must not throw.
    const { container } = render(
      <SelectionBoundary
        {...baseProps}
        id="b6"
        color="#0066cc"
        bounds={bounds}
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    expect(() => fireEvent.mouseDown(span, { shiftKey: true })).not.toThrow();
  });

  it("stops mouseDown propagation on shift+mousedown", () => {
    // The boundary swallows shift+mousedown so the underlying selection
    // layer doesn't restart a drag-selection over an existing annotation.
    const onClick = vi.fn();
    const parentClick = vi.fn();
    const { container } = render(
      <div onMouseDown={parentClick}>
        <SelectionBoundary
          {...baseProps}
          id="b7"
          color="#0066cc"
          bounds={bounds}
          onClick={onClick}
        />
      </div>
    );
    const span = container.querySelector("span") as HTMLElement;
    fireEvent.mouseDown(span, { shiftKey: true });
    // The parent handler must not see the event due to stopPropagation.
    expect(parentClick).not.toHaveBeenCalled();
  });
});
