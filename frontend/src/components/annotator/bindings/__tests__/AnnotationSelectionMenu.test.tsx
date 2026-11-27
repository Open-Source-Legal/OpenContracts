/**
 * The selection menu of the PDF/DOCX viewer. Its gating is OpenContracts'
 * (ported from the old PDF SelectionLayer's permission tests): Copy Text and
 * Copy Link always; creating annotations and links only on an editable
 * document in a corpus the user may update.
 */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { Provider as JotaiProvider, createStore } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SelectionMenuContext } from "@os-legal/react-contract-annotate/core";

import { decodeTextBlock } from "../../../../utils/textBlockEncoding";
import { LabelType } from "../../../../types/graphql-api";
import { PermissionTypes } from "../../../types";
import { activeSpanLabelAtom } from "../../context/AnnotationControlAtoms";
import { corpusStateAtom } from "../../context/CorpusAtom";
import { AnnotationSelectionMenu } from "../AnnotationSelectionMenu";

const label = {
  id: "label-1",
  text: "Clause",
  color: "#0066cc",
  labelType: LabelType.TokenLabel,
} as never;

const pdfPending = {
  json: {
    2: {
      bounds: { top: 0, bottom: 1, left: 0, right: 1 },
      tokensJsons: [
        { pageIndex: 2, tokenIndex: 4 },
        { pageIndex: 2, tokenIndex: 5 },
      ],
      rawText: "two words",
    },
  },
  rawText: "two words",
  page: 2,
  annotationLabel: null,
  anchor: { x: 10, y: 10 },
};

function makeCtx(pending = pdfPending): SelectionMenuContext {
  return {
    pending,
    anchor: pending.anchor,
    commit: vi.fn(),
    clear: vi.fn(),
    copyText: vi.fn(async () => true),
  } as unknown as SelectionMenuContext;
}

interface Setup {
  readOnly?: boolean;
  canUpdate?: boolean;
  activeLabel?: boolean;
  labelSet?: boolean;
  labels?: boolean;
  onStartCreateLink?: (ctx: SelectionMenuContext) => void;
  format?: "pdf" | "docx";
  ctx?: SelectionMenuContext;
}

function renderMenu({
  readOnly = false,
  canUpdate = true,
  activeLabel = true,
  labelSet = true,
  labels = true,
  onStartCreateLink,
  format = "pdf",
  ctx = makeCtx(),
}: Setup = {}) {
  const store = createStore();
  store.set(corpusStateAtom, (prev) => ({
    ...prev,
    selectedCorpus: (labelSet
      ? { id: "c", labelSet: { id: "ls" } }
      : {
          id: "c",
        }) as never,
    myPermissions: canUpdate ? [PermissionTypes.CAN_UPDATE] : [],
    humanTokenLabels: labels ? [label] : [],
  }));
  if (activeLabel) store.set(activeSpanLabelAtom, label);
  render(
    <MemoryRouter initialEntries={["/d/doc?ann=1"]}>
      <JotaiProvider store={store}>
        <AnnotationSelectionMenu
          ctx={ctx}
          format={format}
          readOnly={readOnly}
          onStartCreateLink={onStartCreateLink}
        />
      </JotaiProvider>
    </MemoryRouter>
  );
  return ctx;
}

describe("AnnotationSelectionMenu", () => {
  let writeText: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("offers only copying on a read-only document", () => {
    renderMenu({ readOnly: true });
    expect(screen.getByTestId("copy-text-button")).toBeInTheDocument();
    expect(screen.getByTestId("copy-link-button")).toBeInTheDocument();
    expect(screen.queryByTestId("apply-label-button")).toBeNull();
    expect(screen.getByText("Document is read-only")).toBeInTheDocument();
  });

  it("offers only copying without corpus update permission", () => {
    renderMenu({ canUpdate: false });
    expect(screen.queryByTestId("apply-label-button")).toBeNull();
    expect(screen.getByText("No corpus permissions")).toBeInTheDocument();
  });

  it("applies the active label", () => {
    const ctx = renderMenu();
    const apply = screen.getByTestId("apply-label-button");
    expect(apply).toHaveTextContent("Apply Label: Clause");
    fireEvent.click(apply);
    expect(ctx.commit).toHaveBeenCalledTimes(1);
  });

  it("explains why no label can be applied", () => {
    renderMenu({ activeLabel: false, labelSet: false });
    expect(screen.getByText("No labelset configured")).toBeInTheDocument();
  });

  it("explains that the labelset has no labels", () => {
    renderMenu({ activeLabel: false, labels: false });
    expect(screen.getByText("No labels available")).toBeInTheDocument();
  });

  it("asks for a label to be picked", () => {
    renderMenu({ activeLabel: false });
    expect(screen.getByText("Select a label to annotate")).toBeInTheDocument();
  });

  it("offers Add link… only where links can be made", () => {
    const onStartCreateLink = vi.fn();
    const ctx = renderMenu({ onStartCreateLink });
    fireEvent.click(screen.getByTestId("create-link-button"));
    expect(onStartCreateLink).toHaveBeenCalledWith(ctx);
  });

  it("hides Add link… without a link creator or on a read-only document", () => {
    renderMenu({ readOnly: true, onStartCreateLink: vi.fn() });
    expect(screen.queryByTestId("create-link-button")).toBeNull();
  });

  it("copies the text and closes", () => {
    const ctx = renderMenu();
    fireEvent.click(screen.getByTestId("copy-text-button"));
    expect(ctx.copyText).toHaveBeenCalledTimes(1);
    expect(ctx.clear).toHaveBeenCalledTimes(1);
  });

  it("copies a ?tb= deep link to the selected PDF tokens", () => {
    const ctx = renderMenu();
    fireEvent.click(screen.getByTestId("copy-link-button"));
    const url = new URL(writeText.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/d/doc");
    expect(url.searchParams.get("ann")).toBe("1");
    expect(decodeTextBlock(url.searchParams.get("tb")!)).toEqual({
      type: "pdf",
      tokensByPage: { 2: [4, 5] },
    });
    expect(ctx.clear).toHaveBeenCalled();
  });

  it("copies a ?tb= deep link to the selected DOCX span", () => {
    renderMenu({
      format: "docx",
      ctx: makeCtx({
        ...pdfPending,
        json: { start: 3, end: 9 },
      } as never),
    });
    fireEvent.click(screen.getByTestId("copy-link-button"));
    const url = new URL(writeText.mock.calls[0][0] as string);
    expect(decodeTextBlock(url.searchParams.get("tb")!)).toEqual({
      type: "span",
      start: 3,
      end: 9,
    });
  });

  it("answers the C, A and Escape shortcuts", () => {
    const ctx = renderMenu();
    fireEvent.keyDown(document, { key: "c" });
    expect(ctx.copyText).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "a" });
    expect(ctx.commit).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(ctx.clear).toHaveBeenCalled();
  });

  it("ignores A when no label can be applied", () => {
    const ctx = renderMenu({ readOnly: true });
    fireEvent.keyDown(document, { key: "a" });
    expect(ctx.commit).not.toHaveBeenCalled();
  });

  it("closes on a press outside the menu", () => {
    const ctx = renderMenu();
    fireEvent.mouseDown(document.body);
    expect(ctx.clear).toHaveBeenCalled();
  });
});
