/**
 * Unit-level coverage for SelectionLayer's URL-annotation flow.
 *
 * Exercises ``handleStartCreateLink`` → ``CreateUrlAnnotationModal`` →
 * ``handleConfirmCreateLink`` / ``handleCancelCreateLink`` so the
 * URL creation path is locked in without needing a full Playwright
 * component test. These callbacks are entirely unhit by the existing
 * jsdom test suite (which only drives the basic selection lifecycle),
 * so codecov flags them as missed patches.
 */
import React from "react";
import { render, fireEvent, act, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { Provider as JotaiProvider } from "jotai";
import { MemoryRouter } from "react-router-dom";

import SelectionLayer from "../SelectionLayer";
import { PDFPageInfo } from "../../../types/pdf";
import { ServerTokenAnnotation } from "../../../types/annotations";
import {
  AnnotationLabelType,
  LabelType,
} from "../../../../../types/graphql-api";
import { PermissionTypes } from "../../../../types";

vi.mock("../../../context/CorpusAtom", () => ({
  useCorpusState: vi.fn(),
}));

vi.mock("../../../hooks/useAnnotationSelection", () => ({
  useAnnotationSelection: () => ({
    setSelectedAnnotations: vi.fn(),
  }),
}));

// ``useAnnotationRefs`` returns a refs bundle expected to have a
// ``annotationElementRefs.current`` shape; SelectionBoundary (used by
// pending-selection bounds) accesses it during render. Stub it with a
// minimal shape so the SelectionLayer tree renders inside jsdom.
vi.mock("../../../hooks/useAnnotationRefs", () => ({
  useAnnotationRefs: () => ({
    annotationElementRefs: { current: {} },
    textSearchElementRefs: { current: {} },
    chatSourceElementRefs: { current: {} },
    PDFPageCanvasRef: { current: null },
    PDFPageRendererRef: { current: null },
    PDFPageContainerRefs: { current: {} },
    scrollContainerRef: { current: null },
    registerRef: vi.fn(),
    unregisterRef: vi.fn(),
  }),
}));

// SelectionLayer reads ``isCreatingAnnotationAtom`` via ``useAtom`` and
// ``scrollContainerRefAtom`` via ``useAtomValue``. Mock both with safe
// defaults so the component renders without a Jotai store.
vi.mock("jotai", async () => {
  const actual = await vi.importActual<typeof import("jotai")>("jotai");
  return {
    ...actual,
    useAtom: vi.fn(() => [false, vi.fn()]),
    useAtomValue: vi.fn(() => null),
  };
});

import { useCorpusState } from "../../../context/CorpusAtom";

const activeLabel: AnnotationLabelType = {
  id: "label-1",
  text: "Test Label",
  color: "#0066cc",
  description: "Test label",
  labelType: LabelType.SpanLabel,
  icon: "tag",
  readonly: false,
};

/**
 * Mock PDFPageInfo that yields a deterministic annotation payload —
 * required because the URL-confirm handler iterates over the captured
 * pending selections and asks for their PAWLs-format JSON.
 */
function buildPageInfo() {
  return {
    page: { pageNumber: 1 },
    getPageAnnotationJson: vi.fn(() => ({
      bounds: { left: 0, top: 0, right: 10, bottom: 10 },
      rawText: "linked text",
      tokensJsons: [{ pageIndex: 0, tokenIndex: 0 }],
    })),
    getAnnotationForBounds: vi.fn(() => null),
  } as unknown as PDFPageInfo;
}

function mountLayer(opts: {
  createUrlAnnotation?: ReturnType<
    typeof vi.fn<
      (annotation: ServerTokenAnnotation, url: string) => Promise<void>
    >
  >;
  createAnnotation?: ReturnType<
    typeof vi.fn<(annotation: ServerTokenAnnotation) => void>
  >;
}) {
  const corpusMock = vi.mocked(useCorpusState);
  corpusMock.mockReturnValue({
    canUpdateCorpus: true,
    myPermissions: [PermissionTypes.CAN_UPDATE],
    selectedCorpus: { id: "corpus-1" },
    humanSpanLabels: [activeLabel],
    humanTokenLabels: [activeLabel],
    relationLabels: [],
  } as unknown as ReturnType<typeof useCorpusState>);

  const utils = render(
    <MemoryRouter>
      <JotaiProvider>
        <SelectionLayer
          pageInfo={buildPageInfo()}
          read_only={false}
          activeSpanLabel={activeLabel}
          createAnnotation={opts.createAnnotation ?? vi.fn()}
          createUrlAnnotation={opts.createUrlAnnotation}
          pageNumber={1}
        />
      </JotaiProvider>
    </MemoryRouter>
  );

  // Stub the canvas previousSibling so SelectionLayer's mousedown can
  // read a bounding rect from inside jsdom.
  const layer = utils.container.querySelector(
    "#selection-layer"
  ) as HTMLElement;
  const fakeCanvas = document.createElement("canvas");
  Object.defineProperty(fakeCanvas, "getBoundingClientRect", {
    value: () => ({
      left: 0,
      top: 0,
      right: 200,
      bottom: 200,
      width: 200,
      height: 200,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }),
    configurable: true,
  });
  layer.parentElement?.insertBefore(fakeCanvas, layer);

  // Run a synthetic selection so ``pendingSelections`` is non-empty and
  // the action menu (which hosts the "Add link…" button) is rendered.
  // Wrap each lifecycle phase in its own act() so the doc-level listeners
  // (attached only while ``localPageSelection`` is set, via a useEffect
  // dependency) are bound before the mouseup arrives.
  act(() => {
    fireEvent.mouseDown(layer, { clientX: 5, clientY: 5, buttons: 1 });
  });
  act(() => {
    fireEvent.mouseMove(document, { clientX: 100, clientY: 100, buttons: 1 });
  });
  act(() => {
    fireEvent.mouseUp(document, { clientX: 100, clientY: 100 });
  });

  return { ...utils, layer };
}

describe("SelectionLayer URL-annotation flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("clicking 'Add link…' opens the URL modal", async () => {
    const createUrl = vi.fn(async () => undefined);
    mountLayer({ createUrlAnnotation: createUrl });

    // The action menu portals to document.body once the selection lands.
    const linkBtn = await screen.findByTestId("create-link-button");
    expect(linkBtn).toBeInTheDocument();

    act(() => {
      fireEvent.click(linkBtn);
    });

    // After the click the menu collapses and the URL modal mounts.
    // ``CreateUrlAnnotationModal`` renders an input the user can type into.
    const urlInput = await screen.findByPlaceholderText(/https:\/\//);
    expect(urlInput).toBeInTheDocument();
  });

  it("confirming the URL modal invokes createUrlAnnotation with the typed URL", async () => {
    const createUrl = vi.fn(async () => undefined);
    mountLayer({ createUrlAnnotation: createUrl });

    const linkBtn = await screen.findByTestId("create-link-button");
    act(() => {
      fireEvent.click(linkBtn);
    });

    const urlInput = (await screen.findByPlaceholderText(
      /https:\/\//
    )) as HTMLInputElement;

    act(() => {
      fireEvent.change(urlInput, {
        target: { value: "https://example.com/from-test" },
      });
    });

    // ``CreateUrlAnnotationModal`` renders the confirm button with text
    // "Create link" when no initialUrl is supplied — find it by role/name.
    const confirmBtn = await screen.findByRole("button", {
      name: /create link/i,
    });
    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    expect(createUrl).toHaveBeenCalledTimes(1);
    const callArgs = createUrl.mock.calls[0] as unknown as [unknown, string];
    expect(callArgs[1]).toBe("https://example.com/from-test");
  });

  it("cancelling the URL modal does NOT invoke createUrlAnnotation", async () => {
    const createUrl = vi.fn(async () => undefined);
    mountLayer({ createUrlAnnotation: createUrl });

    const linkBtn = await screen.findByTestId("create-link-button");
    act(() => {
      fireEvent.click(linkBtn);
    });

    await screen.findByPlaceholderText(/https:\/\//);

    // Modal's cancel button is rendered with "Cancel" label.
    const cancelBtn = await screen.findByRole("button", { name: /^cancel$/i });
    act(() => {
      fireEvent.click(cancelBtn);
    });

    expect(createUrl).not.toHaveBeenCalled();
  });

  it("does NOT render the 'Add link…' button when createUrlAnnotation is missing", async () => {
    // The button is gated on ``createUrlAnnotation && ...`` so omitting the
    // prop must hide the entry point entirely. Without this gate, users
    // could click into a no-op modal.
    mountLayer({ createUrlAnnotation: undefined });

    expect(screen.queryByTestId("create-link-button")).not.toBeInTheDocument();
  });
});
