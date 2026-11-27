/**
 * Converters between OpenContracts' annotator data and the plain inputs of
 * `@os-legal/react-contract-annotate`, which renders PDF and DOCX documents.
 *
 * The library treats its inputs as immutable and memoises its own work by
 * object identity, so an OpenContracts annotation keeps returning the same
 * converted object (`toViewerAnnotation`); a fresh object on every render
 * would redraw every annotation. The OpenContracts object rides along as
 * `meta`, so the library's callbacks hand it back.
 */
import type {
  Annotation,
  AnnotationDraft,
  AnnotationLabel,
  Highlight,
  PawlsPage,
  Relation,
} from "@os-legal/react-contract-annotate/core";

import {
  CHAT_SOURCE_HIGHLIGHT_COLOR,
  CHAT_SOURCE_HIGHLIGHT_ID_PREFIX,
  SEARCH_HIGHLIGHT_ID_PREFIX,
  SEARCH_RESULT_HIGHLIGHT_COLOR,
  TEXT_BLOCK_DEEPLINK_ID,
  TEXT_BLOCK_HIGHLIGHT_COLOR,
} from "../../../assets/configurations/constants";
import { AnnotationLabelType } from "../../../types/graphql-api";
import { isValidHexColor, normalizeHexColor } from "../../../utils/colorUtils";
import { TextBlockReference } from "../../../utils/textBlockEncoding";
import {
  MultipageAnnotationJson,
  SpanAnnotationJson,
  TextSearchSpanResult,
  TextSearchTokenResult,
  TokenId,
} from "../../types";
import { ChatMessageSource } from "../context/ChatSourceAtom";
import {
  RelationGroup,
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../types/annotations";
import { PDFPageInfo } from "../types/pdf";
import { annotationChipLabel } from "../utils/urlAnnotation";

/** The document formats the library renders. */
export type ViewerFormat = "pdf" | "docx";

/** An OpenContracts annotation the viewers can draw. */
export type OcAnnotation = ServerTokenAnnotation | ServerSpanAnnotation;

/** An annotation as the viewer receives it, carrying its source in `meta`. */
export type ViewerAnnotation = Annotation<OcAnnotation>;

/**
 * A label colour the library accepts. OpenContracts stores most label
 * colours as bare hex (`"94a3b8"`), which the library would reject and
 * replace with its default; everything else (a `#` hex, a colour name) is
 * passed as it is.
 */
export function toViewerColor(
  color: string | null | undefined
): string | undefined {
  if (!color) return undefined;
  return isValidHexColor(color) ? normalizeHexColor(color) : color;
}

const labelCache = new WeakMap<AnnotationLabelType, AnnotationLabel>();

export function toViewerLabel(label: AnnotationLabelType): AnnotationLabel {
  let converted = labelCache.get(label);
  if (!converted) {
    converted = {
      id: label.id,
      text: label.text ?? "",
      color: toViewerColor(label.color),
      description: label.description ?? undefined,
      icon: label.icon ?? undefined,
    };
    labelCache.set(label, converted);
  }
  return converted;
}

const annotationCache = new WeakMap<OcAnnotation, ViewerAnnotation>();

/**
 * The viewer's annotation for an OpenContracts one. The chip shows
 * `annotationChipLabel` (friendly names for enrichment reference labels),
 * not the raw label text.
 */
export function toViewerAnnotation(annotation: OcAnnotation): ViewerAnnotation {
  let converted = annotationCache.get(annotation);
  if (!converted) {
    const label = toViewerLabel(annotation.annotationLabel);
    const chipText = annotationChipLabel(annotation);
    converted = {
      id: annotation.id,
      annotationLabel:
        chipText === label.text ? label : { ...label, text: chipText },
      rawText: annotation.rawText,
      page: annotation.page,
      json: annotation.json,
      structural: annotation.structural,
      approved: annotation.approved,
      rejected: annotation.rejected,
      linkUrl: annotation.linkUrl ?? null,
      meta: annotation,
    };
    annotationCache.set(annotation, converted);
  }
  return converted;
}

export function toViewerRelation(relation: RelationGroup): Relation {
  return {
    id: relation.id,
    label: toViewerLabel(relation.label),
    sourceIds: relation.sourceIds,
    targetIds: relation.targetIds,
    structural: relation.structural,
  };
}

/**
 * PAWLS pages for the PDF viewer, built from the pages OpenContracts has
 * already resolved: their tokens are normalised to the page's pdf.js
 * viewport at scale 1, so the viewer's token indices are the ones the
 * search index and text maps were built from.
 */
export function toViewerPawls(pages: PDFPageInfo[]): PawlsPage[] {
  return pages.map((info) => {
    const viewport = info.page.getViewport({ scale: 1 });
    return {
      page: {
        width: viewport.width,
        height: viewport.height,
        index: info.page.pageNumber - 1,
      },
      tokens: info.tokens,
    };
  });
}

function tokenIndicesByPage(
  tokensByPage: Record<number, TokenId[]>
): Record<number, number[]> {
  const out: Record<number, number[]> = {};
  for (const [page, tokens] of Object.entries(tokensByPage)) {
    if (tokens?.length) out[Number(page)] = tokens.map((t) => t.tokenIndex);
  }
  return out;
}

export function searchHighlightId(matchId: number): string {
  return `${SEARCH_HIGHLIGHT_ID_PREFIX}${matchId}`;
}

export function chatSourceHighlightId(
  messageId: string,
  sourceIndex: number
): string {
  return `${CHAT_SOURCE_HIGHLIGHT_ID_PREFIX}${messageId}.${sourceIndex}`;
}

/** What a highlight id names: a search hit or a chat source of the message. */
export type HighlightRef =
  | { kind: "search"; matchId: number }
  | { kind: "chatSource"; sourceIndex: number };

/** Reads back an id made by `searchHighlightId` / `chatSourceHighlightId`. */
export function parseHighlightId(id: string | null): HighlightRef | null {
  if (id?.startsWith(SEARCH_HIGHLIGHT_ID_PREFIX)) {
    const matchId = Number(id.slice(SEARCH_HIGHLIGHT_ID_PREFIX.length));
    return Number.isInteger(matchId) ? { kind: "search", matchId } : null;
  }
  if (id?.startsWith(CHAT_SOURCE_HIGHLIGHT_ID_PREFIX)) {
    const sourceIndex = Number(id.slice(id.lastIndexOf(".") + 1));
    return Number.isInteger(sourceIndex)
      ? { kind: "chatSource", sourceIndex }
      : null;
  }
  return null;
}

/** A search hit: token based on PDF, a character span on DOCX. */
export function searchHighlight(
  match: TextSearchTokenResult | TextSearchSpanResult,
  total: number
): Highlight {
  const base = {
    id: searchHighlightId(match.id),
    color: SEARCH_RESULT_HIGHLIGHT_COLOR,
    label: `Search Result ${match.id} of ${total}`,
  };
  if ("tokens" in match) {
    return {
      ...base,
      target: {
        kind: "tokens",
        tokensByPage: tokenIndicesByPage(match.tokens),
        boundsByPage: match.bounds,
      },
    };
  }
  return {
    ...base,
    target: { kind: "span", start: match.start_index, end: match.end_index },
  };
}

/** A chat source, or null when it has nothing the format can draw. */
export function chatSourceHighlight(
  source: ChatMessageSource,
  messageId: string,
  sourceIndex: number,
  total: number,
  format: ViewerFormat
): Highlight | null {
  const base = {
    id: chatSourceHighlightId(messageId, sourceIndex),
    color: CHAT_SOURCE_HIGHLIGHT_COLOR,
    label: `Chat Source ${source.label} of ${total}`,
  };
  if (format === "docx") {
    if (
      !source.isTextBased ||
      typeof source.startIndex !== "number" ||
      typeof source.endIndex !== "number"
    ) {
      return null;
    }
    return {
      ...base,
      target: { kind: "span", start: source.startIndex, end: source.endIndex },
    };
  }
  const tokensByPage = tokenIndicesByPage(source.tokensByPage ?? {});
  if (Object.keys(tokensByPage).length > 0) {
    return {
      ...base,
      target: {
        kind: "tokens",
        tokensByPage,
        boundsByPage: source.boundsByPage,
      },
    };
  }
  if (source.boundsByPage && Object.keys(source.boundsByPage).length > 0) {
    return {
      ...base,
      target: { kind: "bounds", boundsByPage: source.boundsByPage },
    };
  }
  return null;
}

/** The `?tb=` deep-linked text block, or null when it is for another format. */
export function textBlockHighlight(
  block: TextBlockReference,
  format: ViewerFormat
): Highlight | null {
  const base = {
    id: TEXT_BLOCK_DEEPLINK_ID,
    color: TEXT_BLOCK_HIGHLIGHT_COLOR,
  };
  if (format === "pdf" && block.type === "pdf") {
    return {
      ...base,
      target: { kind: "tokens", tokensByPage: block.tokensByPage },
    };
  }
  if (format === "docx" && block.type === "span") {
    return {
      ...base,
      target: { kind: "span", start: block.start, end: block.end },
    };
  }
  return null;
}

/**
 * An OpenContracts annotation for a selection the user made. Token JSON for
 * PDF, a character span for DOCX; persisted by the caller.
 */
export function draftToAnnotation(
  draft: Pick<AnnotationDraft, "json" | "rawText" | "page">,
  label: AnnotationLabelType,
  format: ViewerFormat
): OcAnnotation {
  if (format === "docx") {
    return new ServerSpanAnnotation(
      0,
      label,
      draft.rawText,
      false,
      draft.json as SpanAnnotationJson,
      [],
      false,
      false
    );
  }
  return new ServerTokenAnnotation(
    draft.page,
    label,
    draft.rawText,
    false,
    draft.json as MultipageAnnotationJson,
    [],
    false,
    false,
    false
  );
}
