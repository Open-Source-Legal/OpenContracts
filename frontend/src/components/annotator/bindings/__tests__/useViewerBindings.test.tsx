/**
 * `useViewerBindings`: how OpenContracts' state becomes the PDF/DOCX
 * viewer's props, and what the viewer's reports do to it. The URL-link
 * flow is ported from the old PDF SelectionLayer's URL tests.
 */
import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { Provider as JotaiProvider, createStore } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AnnotatorCommonProps,
  SelectionMenuContext,
} from "@os-legal/react-contract-annotate/core";

import {
  OC_URL_LABEL,
  TEXT_BLOCK_DEEPLINK_ID,
} from "../../../../assets/configurations/constants";
import {
  highlightedTextBlock,
  showAnnotationLabels,
  showSelectedAnnotationOnly,
} from "../../../../graphql/cache";
import { LabelDisplayBehavior, LabelType } from "../../../../types/graphql-api";
import { encodeTextBlock } from "../../../../utils/textBlockEncoding";
import { PermissionTypes } from "../../../types";
import { activeSpanLabelAtom } from "../../context/AnnotationControlAtoms";
import { pdfAnnotationsAtom } from "../../context/AnnotationAtoms";
import { chatSourcesAtom } from "../../context/ChatSourceAtom";
import { corpusStateAtom } from "../../context/CorpusAtom";
import { textSearchStateAtom } from "../../context/DocumentAtom";
import {
  PdfAnnotations,
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../../types/annotations";
import {
  OcAnnotation,
  searchHighlightId,
  chatSourceHighlightId,
} from "../convert";
import { useViewerBindings, ViewerBindingsOptions } from "../useViewerBindings";

const label = {
  id: "label-1",
  text: "Clause",
  color: "#0066cc",
  labelType: LabelType.TokenLabel,
} as never;

const pageJson = {
  0: {
    bounds: { top: 0, bottom: 1, left: 0, right: 1 },
    tokensJsons: [{ pageIndex: 0, tokenIndex: 1 }],
    rawText: "linked text",
  },
};

const pending = {
  json: pageJson,
  rawText: "linked text",
  page: 0,
  annotationLabel: null,
  anchor: { x: 5, y: 5 },
};

function tokenAnnotation(id: string, permissions: PermissionTypes[]) {
  return new ServerTokenAnnotation(
    0,
    label,
    "x",
    false,
    pageJson,
    permissions,
    false,
    false,
    false,
    id
  );
}

const spanAnnotation = new ServerSpanAnnotation(
  0,
  label,
  "y",
  false,
  { start: 0, end: 1 },
  [],
  false,
  false,
  false,
  "span-1"
);

function makeCtx(): SelectionMenuContext {
  return {
    pending,
    anchor: pending.anchor,
    commit: vi.fn(),
    clear: vi.fn(),
    copyText: vi.fn(async () => true),
  } as unknown as SelectionMenuContext;
}

let latest: AnnotatorCommonProps<OcAnnotation>;

const Harness: React.FC<{
  options: ViewerBindingsOptions;
  ctx?: SelectionMenuContext;
}> = ({ options, ctx }) => {
  const { props, dialogs } = useViewerBindings(options);
  latest = props;
  return (
    <>
      {ctx && props.renderSelectionMenu?.(ctx)}
      {dialogs}
    </>
  );
};

function setup(
  options: Partial<ViewerBindingsOptions> = {},
  seed: (store: ReturnType<typeof createStore>) => void = () => {},
  ctx?: SelectionMenuContext
) {
  const store = createStore();
  store.set(corpusStateAtom, (prev) => ({
    ...prev,
    selectedCorpus: { id: "c", labelSet: { id: "ls" } } as never,
    myPermissions: [PermissionTypes.CAN_UPDATE],
    humanTokenLabels: [label],
  }));
  store.set(activeSpanLabelAtom, label);
  seed(store);
  const createAnnotation = vi.fn(async () => undefined);
  render(
    <MemoryRouter>
      <MockedProvider mocks={[]} addTypename={false}>
        <JotaiProvider store={store}>
          <Harness
            ctx={ctx}
            options={{
              format: "pdf",
              readOnly: false,
              createAnnotation,
              ...options,
            }}
          />
        </JotaiProvider>
      </MockedProvider>
    </MemoryRouter>
  );
  return { store, createAnnotation };
}

beforeEach(() => {
  showSelectedAnnotationOnly(false);
  showAnnotationLabels(LabelDisplayBehavior.ON_HOVER);
  highlightedTextBlock(null);
});

describe("useViewerBindings: Add link…", () => {
  it("opens the URL dialog from the selection menu", async () => {
    setup(
      { createUrlAnnotation: vi.fn(async () => undefined) },
      undefined,
      makeCtx()
    );
    fireEvent.click(screen.getByTestId("create-link-button"));
    expect(
      await screen.findByPlaceholderText(/https:\/\//)
    ).toBeInTheDocument();
    // The menu gives way to the dialog; the selection stays.
    expect(screen.queryByTestId("selection-action-menu")).toBeNull();
  });

  it("creates an OC_URL annotation from the selection with the typed URL", async () => {
    const createUrlAnnotation = vi.fn(async () => undefined);
    const ctx = makeCtx();
    setup({ createUrlAnnotation }, undefined, ctx);
    fireEvent.click(screen.getByTestId("create-link-button"));
    fireEvent.change(await screen.findByPlaceholderText(/https:\/\//), {
      target: { value: "https://example.com/from-test" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /create link/i }));
    });
    expect(createUrlAnnotation).toHaveBeenCalledTimes(1);
    const [annotation, url] = createUrlAnnotation.mock.calls[0] as unknown as [
      ServerTokenAnnotation,
      string,
    ];
    expect(url).toBe("https://example.com/from-test");
    expect(annotation.annotationLabel.text).toBe(OC_URL_LABEL);
    expect(annotation.json).toEqual(pageJson);
    expect(annotation.rawText).toBe("linked text");
    expect(ctx.clear).toHaveBeenCalled();
  });

  it("creates nothing when the dialog is cancelled", async () => {
    const createUrlAnnotation = vi.fn(async () => undefined);
    const ctx = makeCtx();
    setup({ createUrlAnnotation }, undefined, ctx);
    fireEvent.click(screen.getByTestId("create-link-button"));
    await screen.findByPlaceholderText(/https:\/\//);
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(createUrlAnnotation).not.toHaveBeenCalled();
    expect(ctx.clear).toHaveBeenCalled();
  });

  it("offers no link without a link creator", () => {
    setup({}, undefined, makeCtx());
    expect(screen.queryByTestId("create-link-button")).toBeNull();
  });

  it("offers no link on DOCX", () => {
    setup(
      { format: "docx", createUrlAnnotation: vi.fn(async () => undefined) },
      undefined,
      makeCtx()
    );
    expect(screen.queryByTestId("create-link-button")).toBeNull();
  });
});

describe("useViewerBindings: props", () => {
  it("passes the format's own annotations", () => {
    const token = tokenAnnotation("tok-1", []);
    setup({}, (store) =>
      store.set(
        pdfAnnotationsAtom,
        new PdfAnnotations([token, spanAnnotation], [], [])
      )
    );
    expect(latest.annotations.map((a) => a.id)).toEqual(["tok-1"]);
  });

  it("creates an annotation with the active label", async () => {
    const { createAnnotation } = setup();
    await act(async () => {
      await latest.onCreateAnnotation?.(pending);
    });
    expect(createAnnotation).toHaveBeenCalledTimes(1);
    const [annotation] = createAnnotation.mock.calls[0] as unknown as [
      ServerTokenAnnotation,
    ];
    expect(annotation.annotationLabel).toBe(label);
    expect(annotation.json).toEqual(pageJson);
  });

  it("maps the label display setting", () => {
    showAnnotationLabels(LabelDisplayBehavior.ALWAYS);
    setup();
    expect(latest.labelDisplay).toBe("always");
  });

  it("offers Edit and Delete by the annotation's own permissions", () => {
    setup();
    const [edit, remove] = latest.annotationActions!;
    const allowed = {
      meta: tokenAnnotation("a", [
        PermissionTypes.CAN_UPDATE,
        PermissionTypes.CAN_REMOVE,
      ]),
    } as never;
    const denied = { meta: tokenAnnotation("b", []) } as never;
    expect(edit.isVisible!(allowed)).toBe(true);
    expect(remove.isVisible!(allowed)).toBe(true);
    expect(edit.isVisible!(denied)).toBe(false);
    expect(remove.isVisible!(denied)).toBe(false);
  });

  it("paints only the current search hit on PDF and makes it active", () => {
    setup({}, (store) =>
      store.set(textSearchStateAtom, {
        matches: [0, 1].map((id) => ({
          id,
          tokens: { 0: [{ pageIndex: 0, tokenIndex: id }] },
          fullContext: null,
          start_page: 0,
          end_page: 0,
        })),
        selectedIndex: 1,
      })
    );
    expect(latest.highlights!.map((h) => h.id)).toEqual([searchHighlightId(1)]);
    expect(latest.activeHighlightId).toBe(searchHighlightId(1));
  });

  it("shows a selected chat message's sources alone, the first one active", () => {
    setup({}, (store) =>
      store.set(chatSourcesAtom, {
        messages: [
          {
            messageId: "m1",
            content: "",
            timestamp: "",
            sources: [0, 1].map((i) => ({
              id: `s${i}`,
              page: 0,
              label: String(i + 1),
              label_id: 0,
              annotation_id: 0,
              rawText: "",
              tokensByPage: { 0: [{ pageIndex: 0, tokenIndex: i }] },
              boundsByPage: {},
            })),
          },
        ],
        selectedMessageId: "m1",
        selectedSourceIndex: null,
      })
    );
    expect(latest.highlights!.map((h) => h.id)).toEqual([
      chatSourceHighlightId("m1", 0),
      chatSourceHighlightId("m1", 1),
    ]);
    expect(latest.activeHighlightId).toBe(chatSourceHighlightId("m1", 0));
    // On PDF a selected message narrows the annotations to the selected ones.
    expect(latest.showSelectedOnly).toBe(true);
  });

  it("makes the deep-linked text block active when nothing else is", () => {
    highlightedTextBlock(
      encodeTextBlock({ type: "pdf", tokensByPage: { 0: [1] } })
    );
    setup();
    expect(latest.activeHighlightId).toBe(TEXT_BLOCK_DEEPLINK_ID);
  });

  it("writes a clicked search hit back as the current one", () => {
    const { store } = setup({}, (s) =>
      s.set(textSearchStateAtom, { matches: [], selectedIndex: 0 })
    );
    act(() => latest.onActiveHighlightChange?.(searchHighlightId(4)));
    expect(store.get(textSearchStateAtom).selectedIndex).toBe(4);
  });
});
