import { describe, expect, it } from "vitest";

import {
  CHAT_SOURCE_HIGHLIGHT_COLOR,
  SEARCH_RESULT_HIGHLIGHT_COLOR,
  TEXT_BLOCK_DEEPLINK_ID,
  TEXT_BLOCK_HIGHLIGHT_COLOR,
} from "../../../../assets/configurations/constants";
import { AnnotationLabelType, LabelType } from "../../../../types/graphql-api";
import { PermissionTypes } from "../../../types";
import { ChatMessageSource } from "../../context/ChatSourceAtom";
import {
  RelationGroup,
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../../types/annotations";
import { PDFPageInfo } from "../../types/pdf";
import {
  chatSourceHighlight,
  chatSourceHighlightId,
  draftToAnnotation,
  parseHighlightId,
  searchHighlight,
  searchHighlightId,
  textBlockHighlight,
  toViewerAnnotation,
  toViewerColor,
  toViewerLabel,
  toViewerPawls,
  toViewerRelation,
} from "../convert";

const label: AnnotationLabelType = {
  id: "label-1",
  text: "Clause",
  color: "94a3b8",
  description: "A clause",
  icon: "tag" as AnnotationLabelType["icon"],
  labelType: LabelType.TokenLabel,
};

const pageJson = {
  0: {
    bounds: { top: 1, bottom: 2, left: 3, right: 4 },
    tokensJsons: [{ pageIndex: 0, tokenIndex: 5 }],
    rawText: "hello",
  },
};

function tokenAnnotation(
  overrides: Partial<{ label: AnnotationLabelType }> = {}
) {
  return new ServerTokenAnnotation(
    0,
    overrides.label ?? label,
    "hello",
    false,
    pageJson,
    [PermissionTypes.CAN_READ],
    true,
    false,
    false,
    "ann-1",
    undefined,
    "https://example.com"
  );
}

describe("toViewerColor", () => {
  it("adds the # OpenContracts' bare hex colours lack", () => {
    expect(toViewerColor("94a3b8")).toBe("#94a3b8");
    expect(toViewerColor("abc")).toBe("#aabbcc");
  });

  it("passes other colours through and drops empty ones", () => {
    expect(toViewerColor("#FF0000")).toBe("#FF0000");
    expect(toViewerColor("red")).toBe("red");
    expect(toViewerColor("")).toBeUndefined();
    expect(toViewerColor(null)).toBeUndefined();
  });
});

describe("toViewerAnnotation", () => {
  it("carries the annotation's data, with the source in meta", () => {
    const source = tokenAnnotation();
    const converted = toViewerAnnotation(source);
    expect(converted).toMatchObject({
      id: "ann-1",
      rawText: "hello",
      page: 0,
      json: source.json,
      structural: false,
      approved: true,
      rejected: false,
      linkUrl: "https://example.com",
      annotationLabel: { id: "label-1", text: "Clause", color: "#94a3b8" },
    });
    expect(converted.meta).toBe(source);
  });

  it("returns the same object for the same annotation", () => {
    const source = tokenAnnotation();
    expect(toViewerAnnotation(source)).toBe(toViewerAnnotation(source));
    expect(toViewerAnnotation(tokenAnnotation())).not.toBe(
      toViewerAnnotation(source)
    );
  });

  it("shows the friendly name of an enrichment reference label", () => {
    const converted = toViewerAnnotation(
      tokenAnnotation({ label: { ...label, text: "OC_REF_LAW" } })
    );
    expect(converted.annotationLabel.text).not.toBe("OC_REF_LAW");
  });
});

describe("toViewerLabel and toViewerRelation", () => {
  it("converts a label once", () => {
    expect(toViewerLabel(label)).toBe(toViewerLabel(label));
  });

  it("converts a relation group", () => {
    const relation = new RelationGroup(["a"], ["b"], label, "rel-1", true);
    expect(toViewerRelation(relation)).toEqual({
      id: "rel-1",
      label: toViewerLabel(label),
      sourceIds: ["a"],
      targetIds: ["b"],
      structural: true,
    });
  });
});

describe("toViewerPawls", () => {
  it("describes each page at scale 1 with its resolved tokens", () => {
    const tokens = [{ x: 1, y: 2, width: 3, height: 4, text: "t" }];
    const page = {
      pageNumber: 2,
      getViewport: () => ({ width: 612, height: 792 }),
    };
    expect(toViewerPawls([new PDFPageInfo(page as never, tokens)])).toEqual([
      { page: { width: 612, height: 792, index: 1 }, tokens },
    ]);
  });
});

describe("highlight ids", () => {
  it("reads back search and chat-source ids", () => {
    expect(parseHighlightId(searchHighlightId(3))).toEqual({
      kind: "search",
      matchId: 3,
    });
    expect(parseHighlightId(chatSourceHighlightId("msg.with.dots", 2))).toEqual(
      { kind: "chatSource", sourceIndex: 2 }
    );
  });

  it("names nothing for other ids", () => {
    expect(parseHighlightId(null)).toBeNull();
    expect(parseHighlightId(TEXT_BLOCK_DEEPLINK_ID)).toBeNull();
    expect(parseHighlightId("ann-1")).toBeNull();
  });
});

describe("searchHighlight", () => {
  it("highlights a PDF hit by its token indices", () => {
    const bounds = { 1: { top: 0, bottom: 1, left: 0, right: 1 } };
    expect(
      searchHighlight(
        {
          id: 2,
          tokens: { 1: [{ pageIndex: 1, tokenIndex: 7 }] },
          bounds,
          fullContext: null,
          start_page: 1,
          end_page: 1,
        },
        5
      )
    ).toEqual({
      id: searchHighlightId(2),
      color: SEARCH_RESULT_HIGHLIGHT_COLOR,
      label: "Search Result 2 of 5",
      target: {
        kind: "tokens",
        tokensByPage: { 1: [7] },
        boundsByPage: bounds,
      },
    });
  });

  it("highlights a DOCX hit by its span", () => {
    const highlight = searchHighlight(
      { id: 0, start_index: 4, end_index: 9, text: "x", fullContext: null },
      1
    );
    expect(highlight.target).toEqual({ kind: "span", start: 4, end: 9 });
  });
});

describe("chatSourceHighlight", () => {
  const source: ChatMessageSource = {
    id: "s",
    page: 0,
    label: "1",
    label_id: 0,
    annotation_id: 0,
    rawText: "x",
    tokensByPage: { 0: [{ pageIndex: 0, tokenIndex: 1 }] },
    boundsByPage: { 0: { top: 0, bottom: 1, left: 0, right: 1 } },
    startIndex: 10,
    endIndex: 20,
    isTextBased: true,
  };

  it("uses the tokens on PDF", () => {
    expect(chatSourceHighlight(source, "m", 0, 2, "pdf")).toEqual({
      id: chatSourceHighlightId("m", 0),
      color: CHAT_SOURCE_HIGHLIGHT_COLOR,
      label: "Chat Source 1 of 2",
      target: {
        kind: "tokens",
        tokensByPage: { 0: [1] },
        boundsByPage: source.boundsByPage,
      },
    });
  });

  it("falls back to the bounds on PDF when there are no tokens", () => {
    const highlight = chatSourceHighlight(
      { ...source, tokensByPage: {} },
      "m",
      0,
      1,
      "pdf"
    );
    expect(highlight?.target).toEqual({
      kind: "bounds",
      boundsByPage: source.boundsByPage,
    });
    expect(
      chatSourceHighlight(
        { ...source, tokensByPage: {}, boundsByPage: {} },
        "m",
        0,
        1,
        "pdf"
      )
    ).toBeNull();
  });

  it("uses the span on DOCX, and nothing for a source without one", () => {
    expect(chatSourceHighlight(source, "m", 1, 2, "docx")?.target).toEqual({
      kind: "span",
      start: 10,
      end: 20,
    });
    expect(
      chatSourceHighlight({ ...source, isTextBased: false }, "m", 1, 2, "docx")
    ).toBeNull();
  });
});

describe("textBlockHighlight", () => {
  it("highlights a block of the viewer's own format only", () => {
    const pdfBlock = { type: "pdf" as const, tokensByPage: { 0: [1, 2] } };
    const spanBlock = { type: "span" as const, start: 1, end: 5 };
    expect(textBlockHighlight(pdfBlock, "pdf")).toEqual({
      id: TEXT_BLOCK_DEEPLINK_ID,
      color: TEXT_BLOCK_HIGHLIGHT_COLOR,
      target: { kind: "tokens", tokensByPage: { 0: [1, 2] } },
    });
    expect(textBlockHighlight(spanBlock, "docx")?.target).toEqual({
      kind: "span",
      start: 1,
      end: 5,
    });
    expect(textBlockHighlight(spanBlock, "pdf")).toBeNull();
    expect(textBlockHighlight(pdfBlock, "docx")).toBeNull();
  });
});

describe("draftToAnnotation", () => {
  it("makes a token annotation from a PDF draft", () => {
    const annotation = draftToAnnotation(
      { json: pageJson, rawText: "hello", page: 0 },
      label,
      "pdf"
    );
    expect(annotation).toBeInstanceOf(ServerTokenAnnotation);
    expect(annotation).toMatchObject({
      page: 0,
      rawText: "hello",
      annotationLabel: label,
      json: pageJson,
      structural: false,
    });
  });

  it("makes a span annotation from a DOCX draft", () => {
    const annotation = draftToAnnotation(
      { json: { start: 2, end: 6 }, rawText: "word", page: 0 },
      label,
      "docx"
    );
    expect(annotation).toBeInstanceOf(ServerSpanAnnotation);
    expect(annotation).toMatchObject({
      rawText: "word",
      json: { start: 2, end: 6 },
      annotationLabel: label,
    });
  });
});
