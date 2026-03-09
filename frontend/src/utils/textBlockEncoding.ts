/**
 * Text Block Encoding/Decoding Utilities
 *
 * Provides compact URL-safe encoding for text block references that can be used
 * as deep links to specific text locations in documents WITHOUT creating
 * database annotations.
 *
 * Format:
 *   Text spans:  "s{start}-{end}"           e.g., "s100-500"
 *   PDF tokens:  "p{page}:{ranges};..."     e.g., "p0:45-65,70-72;p1:0-23"
 *
 * These are used in the ?tb= URL query parameter.
 */

import {
  BoundingBox,
  MultipageAnnotationJson,
  SinglePageAnnotationJson,
  TokenId,
} from "../components/types";
import { normalizeAnnotationJson } from "./compactFormat";

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

/**
 * A decoded text block reference for text-based documents.
 * Uses character start/end indices.
 */
export interface TextSpanBlock {
  type: "span";
  start: number;
  end: number;
}

/**
 * A decoded text block reference for PDF documents.
 * Uses page indices and token index ranges per page.
 */
export interface PdfTokenBlock {
  type: "pdf";
  /** Map of page index → sorted array of token indices */
  tokensByPage: Record<number, number[]>;
}

/**
 * Union type for all text block references.
 */
export type TextBlockReference = TextSpanBlock | PdfTokenBlock;

// ═══════════════════════════════════════════════════════════════
// Encoding
// ═══════════════════════════════════════════════════════════════

/**
 * Encode a consecutive range of numbers into a compact string.
 * [1, 2, 3, 5, 7, 8, 9] → "1-3,5,7-9"
 */
function encodeTokenRanges(tokens: number[]): string {
  if (tokens.length === 0) return "";
  const sorted = [...tokens].sort((a, b) => a - b);
  const ranges: string[] = [];
  let rangeStart = sorted[0];
  let rangeEnd = sorted[0];

  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === rangeEnd + 1) {
      rangeEnd = sorted[i];
    } else {
      ranges.push(
        rangeStart === rangeEnd ? `${rangeStart}` : `${rangeStart}-${rangeEnd}`
      );
      rangeStart = sorted[i];
      rangeEnd = sorted[i];
    }
  }
  ranges.push(
    rangeStart === rangeEnd ? `${rangeStart}` : `${rangeStart}-${rangeEnd}`
  );
  return ranges.join(",");
}

/** Maximum number of tokens a single range segment may expand to.
 *  Guards against malicious URLs like "0-9999999" creating huge arrays. */
const MAX_RANGE_SPAN = 10_000;

/** Maximum cumulative token count across ALL page segments.
 *  Prevents crafted URLs with many small-but-valid page entries from
 *  allocating a significant amount of memory (e.g., 500 pages × 10k each). */
const MAX_TOTAL_TOKENS = 50_000;

/**
 * Decode a compact token range string back to an array of numbers.
 * "1-3,5,7-9" → [1, 2, 3, 5, 7, 8, 9]
 */
function decodeTokenRanges(rangeStr: string): number[] {
  if (!rangeStr) return [];
  const tokens: number[] = [];
  const parts = rangeStr.split(",");
  for (const part of parts) {
    if (part.includes("-")) {
      const [startStr, endStr] = part.split("-");
      const start = parseInt(startStr, 10);
      const end = parseInt(endStr, 10);
      if (isNaN(start) || isNaN(end)) continue;
      if (end - start > MAX_RANGE_SPAN) continue;
      for (let i = start; i <= end; i++) {
        tokens.push(i);
      }
    } else {
      const num = parseInt(part, 10);
      if (!isNaN(num)) {
        tokens.push(num);
      }
    }
  }
  return tokens;
}

/**
 * Encode a TextSpanBlock to URL parameter value.
 * Returns: "s{start}-{end}"
 */
function encodeSpanBlock(block: TextSpanBlock): string {
  return `s${block.start}-${block.end}`;
}

/**
 * Encode a PdfTokenBlock to URL parameter value.
 * Returns: "p{page}:{ranges};p{page}:{ranges};..."
 */
function encodePdfBlock(block: PdfTokenBlock): string {
  const pageEntries = Object.entries(block.tokensByPage)
    .map(([page, tokens]) => {
      const ranges = encodeTokenRanges(tokens);
      return ranges ? `p${page}:${ranges}` : null;
    })
    .filter(Boolean);
  return pageEntries.join(";");
}

/**
 * Encode a TextBlockReference into a compact URL parameter string.
 */
export function encodeTextBlock(block: TextBlockReference): string {
  if (block.type === "span") {
    return encodeSpanBlock(block);
  }
  return encodePdfBlock(block);
}

/**
 * Decode a URL parameter string into a TextBlockReference.
 * Returns null if the string is invalid.
 */
export function decodeTextBlock(param: string): TextBlockReference | null {
  if (!param) return null;

  // Text span: "s{start}-{end}"
  if (param.startsWith("s")) {
    const match = param.match(/^s(\d+)-(\d+)$/);
    if (!match) return null;
    const start = parseInt(match[1], 10);
    const end = parseInt(match[2], 10);
    if (start > end) return null;
    return { type: "span", start, end };
  }

  // PDF tokens: "p{page}:{ranges};p{page}:{ranges};..."
  if (param.startsWith("p")) {
    const tokensByPage: Record<number, number[]> = {};
    let totalTokens = 0;
    const pageSegments = param.split(";");
    for (const segment of pageSegments) {
      const pageMatch = segment.match(/^p(\d+):(.+)$/);
      if (!pageMatch) continue;
      const pageIdx = parseInt(pageMatch[1], 10);
      const tokens = decodeTokenRanges(pageMatch[2]);
      if (tokens.length > 0) {
        totalTokens += tokens.length;
        if (totalTokens > MAX_TOTAL_TOKENS) break;
        tokensByPage[pageIdx] = tokens;
      }
    }
    if (Object.keys(tokensByPage).length === 0) return null;
    return { type: "pdf", tokensByPage };
  }

  return null;
}

// ═══════════════════════════════════════════════════════════════
// Conversion helpers: Source data → TextBlockReference
// ═══════════════════════════════════════════════════════════════

/**
 * Create a TextBlockReference from text span data (character indices).
 */
export function textBlockFromSpan(start: number, end: number): TextSpanBlock {
  return { type: "span", start, end };
}

/**
 * Create a TextBlockReference from MultipageAnnotationJson (PAWLS tokens).
 */
export function textBlockFromMultipageJson(
  json: MultipageAnnotationJson
): PdfTokenBlock {
  // Normalize in case compact format is passed
  const normalized = normalizeAnnotationJson(json) ?? {};
  const tokensByPage: Record<number, number[]> = {};
  for (const [pageKey, pageData] of Object.entries(normalized)) {
    const pageIdx = parseInt(pageKey, 10);
    if (isNaN(pageIdx)) continue;
    const data = pageData as SinglePageAnnotationJson;
    if (data.tokensJsons?.length) {
      tokensByPage[pageIdx] = data.tokensJsons.map((t) => t.tokenIndex);
    }
  }
  return { type: "pdf", tokensByPage };
}

/**
 * Create a TextBlockReference from TokenId arrays per page
 * (the format used by ChatMessageSource.tokensByPage).
 */
export function textBlockFromTokensByPage(
  tokensByPage: Record<number, TokenId[]>
): PdfTokenBlock {
  const result: Record<number, number[]> = {};
  for (const [pageKey, tokens] of Object.entries(tokensByPage)) {
    const pageIdx = parseInt(pageKey, 10);
    if (isNaN(pageIdx) || !tokens.length) continue;
    result[pageIdx] = tokens.map((t) => t.tokenIndex);
  }
  return { type: "pdf", tokensByPage: result };
}

// ═══════════════════════════════════════════════════════════════
// Rendering helpers: TextBlockReference → display data
// ═══════════════════════════════════════════════════════════════

/**
 * Convert a PdfTokenBlock back to TokenId arrays per page,
 * suitable for rendering with ChatSourceTokens or similar components.
 */
export function textBlockToTokenIds(
  block: PdfTokenBlock
): Record<number, TokenId[]> {
  const result: Record<number, TokenId[]> = {};
  for (const [pageKey, tokenIndices] of Object.entries(block.tokensByPage)) {
    const pageIdx = parseInt(pageKey, 10);
    result[pageIdx] = tokenIndices.map((tokenIndex) => ({
      pageIndex: pageIdx,
      tokenIndex,
    }));
  }
  return result;
}

/**
 * Compute bounding boxes for a PdfTokenBlock given page token data.
 * This looks up token geometry from the page's token array.
 *
 * @param block - The PDF text block reference
 * @param pageTokens - Map of page index → token array (from PAWLS data)
 * @returns Map of page index → bounding box
 */
export function textBlockToBounds(
  block: PdfTokenBlock,
  pageTokens: Record<
    number,
    { x: number; y: number; width: number; height: number }[]
  >
): Record<number, BoundingBox> {
  const result: Record<number, BoundingBox> = {};
  for (const [pageKey, tokenIndices] of Object.entries(block.tokensByPage)) {
    const pageIdx = parseInt(pageKey, 10);
    const tokens = pageTokens[pageIdx];
    if (!tokens) continue;

    let top = Infinity;
    let left = Infinity;
    let bottom = -Infinity;
    let right = -Infinity;

    for (const idx of tokenIndices) {
      const token = tokens[idx];
      if (!token) continue;
      top = Math.min(top, token.y);
      left = Math.min(left, token.x);
      bottom = Math.max(bottom, token.y + token.height);
      right = Math.max(right, token.x + token.width);
    }

    if (top !== Infinity) {
      result[pageIdx] = { top, left, bottom, right };
    }
  }
  return result;
}
