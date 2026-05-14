/**
 * Unit-level coverage for TxtAnnotator's URL-annotation flow.
 *
 * Drives ``handleTxtStartCreateLink``, ``handleTxtConfirmCreateLink``,
 * and ``handleTxtCancelCreateLink`` so the Span-based URL creation path
 * is locked in for text/markdown documents. These callbacks share the
 * contract with the PDF flow but live on a separate code path
 * (Span vs Token), so codecov flags them independently.
 *
 * jsdom only partially implements ``Selection``; we stub ``getSelection``
 * to return a deterministic range so ``handleMouseUp`` reaches
 * ``setPendingSelection`` without depending on the browser's text-layout
 * subsystem.
 */
import React from "react";
import { render, fireEvent, act, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

import TxtAnnotator from "../TxtAnnotator";
import { ServerSpanAnnotation } from "../../../types/annotations";
import { LabelType } from "../../../../../types/graphql-api";
import { PermissionTypes } from "../../../../types";
import { OC_URL_LABEL } from "../../../../../assets/configurations/constants";

const mockLabel = {
  id: "label-1",
  text: "TestLabel",
  color: "#3B82F6",
  icon: "tag",
  description: "Test label",
  labelType: LabelType.SpanLabel,
};

const ocUrlLabel = {
  id: "label-url",
  text: OC_URL_LABEL,
  color: "#2563EB",
  icon: "link",
  description: "url",
  labelType: LabelType.SpanLabel,
};

// Stable empty array reused for both ``searchResults`` and ``chatSources``
// props so we don't trip TxtAnnotator's referential-equality memoization
// (a new ``[]`` literal each render would cause infinite re-renders).
const EMPTY = [] as never[];

const defaultProps = {
  searchResults: EMPTY,
  getSpan: vi.fn(
    (sel: { start: number; end: number }) =>
      new ServerSpanAnnotation(
        0,
        mockLabel,
        "hello",
        false,
        { start: sel.start, end: sel.end },
        [PermissionTypes.CAN_READ, PermissionTypes.CAN_UPDATE],
        false,
        false,
        false,
        "local-tmp-id"
      )
  ),
  visibleLabels: null,
  availableLabels: [mockLabel],
  selectedLabelTypeId: mockLabel.id,
  // allowInput=true + read_only=false unlocks the menu's annotation-creation
  // entry points (Apply Label / Add link…), matching the live UX gate.
  read_only: false,
  allowInput: true,
  zoom_level: 1,
  createAnnotation: vi.fn(),
  updateAnnotation: vi.fn(),
  deleteAnnotation: vi.fn(),
  selectedAnnotations: [] as string[],
  setSelectedAnnotations: vi.fn(),
  showStructuralAnnotations: true,
  chatSources: EMPTY,
};

/**
 * Stub ``document.getSelection`` so ``handleMouseUp`` reads a deterministic
 * text range and pushes ``pendingSelection`` into state. The values mirror
 * what jsdom would return after a real ``span.click``+drag, but without
 * depending on jsdom's incomplete layout engine.
 */
function mockSelection(opts: {
  text: string;
  anchorNode: Node;
  anchorOffset: number;
  focusNode: Node;
  focusOffset: number;
}) {
  // ``TxtAnnotator.dismissMenu`` calls ``Selection.removeAllRanges`` after
  // a menu interaction; jsdom's getSelection() shim implements it but the
  // mocked instance does not by default. Provide the full surface area
  // the component touches so the dismissal path doesn't throw.
  const sel = {
    toString: () => opts.text,
    anchorNode: opts.anchorNode,
    focusNode: opts.focusNode,
    anchorOffset: opts.anchorOffset,
    focusOffset: opts.focusOffset,
    removeAllRanges: vi.fn(),
    rangeCount: 1,
  } as unknown as Selection;
  vi.spyOn(document, "getSelection").mockReturnValue(sel);
}

describe("TxtAnnotator URL-annotation flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset menu cooldown by faking the timestamp far enough in the past.
    vi.useFakeTimers({ now: Date.now() + 10_000 });
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("'Add link…' button is only rendered when createUrlAnnotation is provided", async () => {
    // Without ``createUrlAnnotation`` the menu must NOT advertise the
    // link-creation entry point — clicking it would be a no-op confusion.
    const { container, rerender } = render(
      <MemoryRouter>
        <TxtAnnotator {...defaultProps} text="hello world" annotations={[]} />
      </MemoryRouter>
    );

    const wrapper = container.querySelector("div[id]") as HTMLDivElement;
    expect(wrapper).toBeTruthy();

    // Stub selection covering "hello".
    const textNode = wrapper.querySelector("span")?.firstChild ?? wrapper;
    mockSelection({
      text: "hello",
      anchorNode: textNode,
      anchorOffset: 0,
      focusNode: textNode,
      focusOffset: 5,
    });

    act(() => {
      fireEvent.mouseUp(wrapper, { clientX: 50, clientY: 50 });
    });

    // The menu may not render the link button without createUrlAnnotation
    expect(screen.queryByText(/add link/i)).not.toBeInTheDocument();

    // Now re-render with the prop; the button must appear.
    const createUrl = vi.fn(async () => undefined);
    rerender(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text="hello world"
          annotations={[]}
          createUrlAnnotation={createUrl}
        />
      </MemoryRouter>
    );

    const wrapper2 = container.querySelector("div[id]") as HTMLDivElement;
    const textNode2 = wrapper2.querySelector("span")?.firstChild ?? wrapper2;
    mockSelection({
      text: "hello",
      anchorNode: textNode2,
      anchorOffset: 0,
      focusNode: textNode2,
      focusOffset: 5,
    });

    act(() => {
      fireEvent.mouseUp(wrapper2, { clientX: 50, clientY: 50 });
    });

    // "Add link…" should now appear in the menu.
    expect(await screen.findByText(/add link/i)).toBeInTheDocument();
  });

  it("opens the URL modal when 'Add link…' is clicked, then awaits createUrlAnnotation on confirm", async () => {
    const createUrl = vi.fn(async () => undefined);

    const { container } = render(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text="hello world"
          annotations={[]}
          createUrlAnnotation={createUrl}
        />
      </MemoryRouter>
    );

    const wrapper = container.querySelector("div[id]") as HTMLDivElement;
    const textNode = wrapper.querySelector("span")?.firstChild ?? wrapper;
    mockSelection({
      text: "hello",
      anchorNode: textNode,
      anchorOffset: 0,
      focusNode: textNode,
      focusOffset: 5,
    });

    act(() => {
      fireEvent.mouseUp(wrapper, { clientX: 50, clientY: 50 });
    });

    const linkBtn = await screen.findByText(/add link/i);
    act(() => {
      fireEvent.click(linkBtn);
    });

    // CreateUrlAnnotationModal must mount with the placeholder input.
    const urlInput = (await screen.findByPlaceholderText(
      /https:\/\//
    )) as HTMLInputElement;
    act(() => {
      fireEvent.change(urlInput, {
        target: { value: "https://example.com/txt" },
      });
    });

    const confirmBtn = await screen.findByRole("button", {
      name: /create link/i,
    });
    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    expect(createUrl).toHaveBeenCalledTimes(1);
    const callArgs = createUrl.mock.calls[0] as unknown as [unknown, string];
    expect(callArgs[1]).toBe("https://example.com/txt");
  });

  it("renders existing OC_URL annotations as hyperlinks (underline + pointer)", async () => {
    // The renderer's hyperlink-styling block (cursor: pointer + underline)
    // only fires when ``isUrlAnnotation`` matches — i.e. an annotation
    // carries the OC_URL label AND a non-empty linkUrl. Without an OC_URL
    // fixture, those style branches stay unhit.
    const linkAnn = new ServerSpanAnnotation(
      0,
      ocUrlLabel,
      "hello",
      false,
      { start: 0, end: 5 },
      [PermissionTypes.CAN_READ, PermissionTypes.CAN_UPDATE],
      false,
      false,
      false,
      "ann-link-1",
      undefined,
      "https://example.com/anchor"
    );

    const { container } = render(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text="hello world"
          annotations={[linkAnn]}
        />
      </MemoryRouter>
    );

    // The annotated span (covering "hello") must be present with the
    // hyperlink styling derived from ``isUrlAnnotation`` matching.
    const annotatedSpan = container.querySelector(
      '[data-testid^="annotated-span-"]'
    );
    expect(annotatedSpan).toBeTruthy();
    const style = (annotatedSpan as HTMLElement).getAttribute("style") || "";
    // Pointer cursor + underline are the two visible hyperlink signals.
    expect(style.toLowerCase()).toContain("cursor: pointer");
    expect(style.toLowerCase()).toContain("text-decoration: underline");
  });

  it("clicking a hyperlink annotation opens the URL", async () => {
    // Companion to the styling test above: a plain (no shift/meta/ctrl)
    // click on a hyperlink span must route through ``openAnnotationUrl``
    // — which we observe via the mocked ``window.open`` for absolute URLs.
    const openSpy = vi
      .spyOn(window, "open")
      .mockReturnValue(null as unknown as Window);

    const linkAnn = new ServerSpanAnnotation(
      0,
      ocUrlLabel,
      "hello",
      false,
      { start: 0, end: 5 },
      [PermissionTypes.CAN_READ],
      false,
      false,
      false,
      "ann-link-2",
      undefined,
      "https://example.com/click-target"
    );

    const { container } = render(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text="hello world"
          annotations={[linkAnn]}
        />
      </MemoryRouter>
    );

    const annotatedSpan = container.querySelector(
      '[data-testid^="annotated-span-"]'
    ) as HTMLElement;
    expect(annotatedSpan).toBeTruthy();

    act(() => {
      fireEvent.click(annotatedSpan);
    });

    expect(openSpy).toHaveBeenCalledWith(
      "https://example.com/click-target",
      "_blank",
      "noopener,noreferrer"
    );
    openSpy.mockRestore();
  });

  it("cancelling the URL modal does NOT invoke createUrlAnnotation", async () => {
    const createUrl = vi.fn(async () => undefined);

    const { container } = render(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text="hello world"
          annotations={[]}
          createUrlAnnotation={createUrl}
        />
      </MemoryRouter>
    );

    const wrapper = container.querySelector("div[id]") as HTMLDivElement;
    const textNode = wrapper.querySelector("span")?.firstChild ?? wrapper;
    mockSelection({
      text: "hello",
      anchorNode: textNode,
      anchorOffset: 0,
      focusNode: textNode,
      focusOffset: 5,
    });

    act(() => {
      fireEvent.mouseUp(wrapper, { clientX: 50, clientY: 50 });
    });

    const linkBtn = await screen.findByText(/add link/i);
    act(() => {
      fireEvent.click(linkBtn);
    });

    await screen.findByPlaceholderText(/https:\/\//);

    const cancelBtn = await screen.findByRole("button", { name: /^cancel$/i });
    act(() => {
      fireEvent.click(cancelBtn);
    });

    expect(createUrl).not.toHaveBeenCalled();
  });
});
