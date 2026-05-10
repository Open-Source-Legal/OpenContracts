/**
 * Unit-level coverage for SelectionLayer's document-level mouseup/mousemove
 * fallback during an in-progress selection.
 *
 * The CT in DocumentRenderingCornerCases.ct.tsx exercises the full path
 * end-to-end (mobile drag releases over a SidebarTab, action menu still
 * appears), but a unit test pins the contract that document listeners
 * attach only while a selection is mid-flight and detach after release —
 * preventing a future regression where the listeners stay armed across
 * unrelated mouse activity.
 */
import React from "react";
import { render, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { Provider as JotaiProvider } from "jotai";
import { MemoryRouter } from "react-router-dom";

import SelectionLayer from "../SelectionLayer";
import { PDFPageInfo } from "../../../types/pdf";
import {
  AnnotationLabelType,
  LabelType,
} from "../../../../../types/graphql-api";
import { PermissionTypes } from "../../../../types";

type CorpusStateShape = ReturnType<
  typeof import("../../../context/CorpusAtom").useCorpusState
>;

vi.mock("../../../context/CorpusAtom", () => ({
  useCorpusState: vi.fn(),
}));

vi.mock("../../../hooks/useAnnotationSelection", () => ({
  useAnnotationSelection: () => ({
    setSelectedAnnotations: vi.fn(),
  }),
}));

vi.mock("jotai", async () => {
  const actual = await vi.importActual<typeof import("jotai")>("jotai");
  return {
    ...actual,
    useAtom: vi.fn(() => [false, vi.fn()]),
  };
});

import { useCorpusState } from "../../../context/CorpusAtom";

const mockActiveLabel: AnnotationLabelType = {
  id: "label-1",
  text: "Test Label",
  color: "#0066cc",
  description: "Test label",
  labelType: LabelType.SpanLabel,
  icon: "tag",
  readonly: false,
};

const mockPageInfo = {
  page: { pageNumber: 1 },
  getPageAnnotationJson: vi.fn(() => ({ rawText: "x", tokensJsons: [] })),
  getAnnotationForBounds: vi.fn(() => null),
} as unknown as PDFPageInfo;

const mountLayer = () => {
  const mocked = vi.mocked(useCorpusState);
  mocked.mockReturnValue({
    canUpdateCorpus: true,
    myPermissions: [PermissionTypes.CAN_UPDATE],
    selectedCorpus: { id: "corpus-1" },
    humanSpanLabels: [mockActiveLabel],
    humanTokenLabels: [],
    relationLabels: [],
  } as unknown as CorpusStateShape);

  return render(
    <MemoryRouter>
      <JotaiProvider>
        <SelectionLayer
          pageInfo={mockPageInfo}
          read_only={false}
          activeSpanLabel={mockActiveLabel}
          createAnnotation={vi.fn()}
          pageNumber={1}
        />
      </JotaiProvider>
    </MemoryRouter>
  );
};

describe("SelectionLayer document-level mouseup fallback", () => {
  let addSpy: ReturnType<typeof vi.spyOn>;
  let removeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    addSpy = vi.spyOn(document, "addEventListener");
    removeSpy = vi.spyOn(document, "removeEventListener");
  });

  it("does NOT attach document mouseup/mousemove on mount", () => {
    const { unmount } = mountLayer();

    // Idle (no selection in progress) — the cleanup path must not have
    // armed the global handlers. The escape-key handler is also conditional
    // on localPageSelection so it should not fire here either.
    const armed = addSpy.mock.calls.filter(
      ([type]) => type === "mouseup" || type === "mousemove"
    );
    expect(armed).toHaveLength(0);

    unmount();
    // No leaks on unmount when no selection was started — the cleanup
    // returns from the useEffect early before binding anything.
    const leaked = removeSpy.mock.calls.filter(
      ([type]) => type === "mouseup" || type === "mousemove"
    );
    expect(leaked).toHaveLength(0);
  });

  it("attaches document listeners after a mousedown starts a selection", () => {
    const { container } = mountLayer();
    const layer = container.querySelector("#selection-layer") as HTMLElement;
    expect(layer).toBeInTheDocument();

    addSpy.mockClear();

    // Stub the canvas previousSibling so handleMouseDown's bounding-rect
    // read works inside jsdom.
    const fakeCanvas = document.createElement("canvas");
    Object.defineProperty(fakeCanvas, "getBoundingClientRect", {
      value: () => ({
        left: 0,
        top: 0,
        right: 100,
        bottom: 100,
        width: 100,
        height: 100,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
      configurable: true,
    });
    layer.parentElement?.insertBefore(fakeCanvas, layer);

    act(() => {
      fireEvent.mouseDown(layer, {
        clientX: 10,
        clientY: 10,
        buttons: 1,
      });
    });

    const types = addSpy.mock.calls.map(([t]) => t);
    expect(types).toContain("mouseup");
    expect(types).toContain("mousemove");
    // Plus the keydown for escape handling (also gated on localPageSelection)
    expect(types).toContain("keydown");
  });

  it("detaches document listeners after mouseup completes the selection", () => {
    const { container } = mountLayer();
    const layer = container.querySelector("#selection-layer") as HTMLElement;

    // Same canvas stub as above.
    const fakeCanvas = document.createElement("canvas");
    Object.defineProperty(fakeCanvas, "getBoundingClientRect", {
      value: () => ({
        left: 0,
        top: 0,
        right: 100,
        bottom: 100,
        width: 100,
        height: 100,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
      configurable: true,
    });
    layer.parentElement?.insertBefore(fakeCanvas, layer);

    // Start selection
    act(() => {
      fireEvent.mouseDown(layer, { clientX: 10, clientY: 10, buttons: 1 });
    });

    removeSpy.mockClear();

    // Release at the document level (NOT on the layer) — this is the
    // bug the fix addresses: the mouseup happens over an unrelated element
    // (e.g. a SidebarTab) and must still finalise the selection.
    act(() => {
      fireEvent.mouseUp(document);
    });

    const removedTypes = removeSpy.mock.calls.map(([t]) => t);
    expect(removedTypes).toContain("mouseup");
    expect(removedTypes).toContain("mousemove");
  });
});
