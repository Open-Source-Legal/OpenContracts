/**
 * Compact PAWLS & annotation JSON format converters.
 *
 * Provides bidirectional conversion between legacy verbose format and compact
 * format for PAWLS token data and annotation JSON.
 *
 * ## Compact PAWLS token: 5-element array
 *   [x, y, width, height, text]
 *
 * ## Compact page:
 *   { p: [width, height, index], t: [[...], ...], im?: { "5": {...} } }
 *
 * ## Compact annotation JSON:
 *   { "0": { b: [left, top, right, bottom], t: [3, 4, 5], r: "text" } }
 */

import {
  Token,
  Page,
  PageTokens,
  BoundingBox,
  TokenId,
  SinglePageAnnotationJson,
  MultipageAnnotationJson,
} from "../components/types";

// ═══════════════════════════════════════════════════════════════
// Array position constants
// ═══════════════════════════════════════════════════════════════

// Token array: [x, y, width, height, text]
const TX = 0;
const TY = 1;
const TW = 2;
const TH = 3;
const TT = 4;

// Bounds array: [left, top, right, bottom]
const BL = 0;
const BT = 1;
const BR = 2;
const BB = 3;

// Page array: [width, height, index]
const PW = 0;
const PH = 1;
const PI = 2;

// Image metadata compact keys → legacy keys
const IM_KEYS_REVERSE: Record<string, string> = {
  p: "image_path",
  f: "format",
  h: "content_hash",
  ow: "original_width",
  oh: "original_height",
  it: "image_type",
  d: "base64_data",
};

// ═══════════════════════════════════════════════════════════════
// Compact page/token types (for type safety)
// ═══════════════════════════════════════════════════════════════

type CompactToken = [number, number, number, number, string];

interface CompactImageMeta {
  p?: string; // image_path
  f?: string; // format
  h?: string; // content_hash
  ow?: number; // original_width
  oh?: number; // original_height
  it?: string; // image_type
  d?: string; // base64_data
}

interface CompactPage {
  p: [number, number, number]; // [width, height, index]
  t: CompactToken[];
  im?: Record<string, CompactImageMeta>;
}

interface CompactSinglePageAnnotation {
  b: [number, number, number, number]; // [left, top, right, bottom]
  t: number[]; // token indices
  r: string; // rawText
}

// ═══════════════════════════════════════════════════════════════
// Format detection
// ═══════════════════════════════════════════════════════════════

export function isCompactPawls(pages: unknown[]): boolean {
  if (!pages || pages.length === 0) return false;
  const first = pages[0] as Record<string, unknown>;
  return (
    typeof first === "object" &&
    first !== null &&
    "p" in first &&
    !("page" in first)
  );
}

export function isCompactAnnotationJson(
  json: Record<string | number, unknown>
): boolean {
  if (!json) return false;
  for (const pageData of Object.values(json)) {
    if (typeof pageData === "object" && pageData !== null) {
      return "b" in pageData && !("bounds" in pageData);
    }
  }
  return false;
}

// ═══════════════════════════════════════════════════════════════
// PAWLS conversion: compact → legacy
// ═══════════════════════════════════════════════════════════════

function expandToken(arr: CompactToken): Token {
  return {
    x: arr[TX],
    y: arr[TY],
    width: arr[TW],
    height: arr[TH],
    text: arr[TT],
  };
}

function expandImageMeta(meta: CompactImageMeta): Partial<Token> {
  const result: Partial<Token> = { is_image: true };
  for (const [shortKey, longKey] of Object.entries(IM_KEYS_REVERSE)) {
    if (shortKey in meta) {
      (result as Record<string, unknown>)[longKey] =
        meta[shortKey as keyof CompactImageMeta];
    }
  }
  return result;
}

function expandPage(compact: CompactPage): PageTokens {
  const page: Page = {
    width: compact.p[PW],
    height: compact.p[PH],
    index: compact.p[PI],
  };

  const imageMeta = compact.im || {};
  const tokens: Token[] = compact.t.map((arr, idx) => {
    const token = expandToken(arr);
    const idxStr = String(idx);
    if (idxStr in imageMeta) {
      Object.assign(token, expandImageMeta(imageMeta[idxStr]));
    }
    return token;
  });

  return { page, tokens };
}

/**
 * Accept either format and always return legacy PageTokens[].
 * This is the primary entry point for loading PAWLS data.
 */
export function normalizePawls(pages: unknown[]): PageTokens[] {
  if (!pages || pages.length === 0) return [];
  if (isCompactPawls(pages)) {
    return (pages as CompactPage[]).map(expandPage);
  }
  return pages as PageTokens[];
}

// ═══════════════════════════════════════════════════════════════
// Annotation JSON conversion: compact → legacy
// ═══════════════════════════════════════════════════════════════

function expandSinglePageAnnotation(
  pageIndex: number,
  compact: CompactSinglePageAnnotation
): SinglePageAnnotationJson {
  return {
    bounds: {
      left: compact.b[BL],
      top: compact.b[BT],
      right: compact.b[BR],
      bottom: compact.b[BB],
    },
    tokensJsons: compact.t.map((tokenIndex) => ({
      pageIndex,
      tokenIndex,
    })),
    rawText: compact.r,
  };
}

/**
 * Accept either format and always return legacy MultipageAnnotationJson.
 * This is the primary entry point for loading annotation JSON.
 */
export function normalizeAnnotationJson(
  json: Record<string | number, unknown> | null | undefined
): MultipageAnnotationJson | null {
  if (json === null || json === undefined) return null;
  if (Object.keys(json).length === 0) return {};

  if (isCompactAnnotationJson(json)) {
    const result: MultipageAnnotationJson = {};
    for (const [pageKey, pageData] of Object.entries(json)) {
      const pageIdx = parseInt(pageKey, 10);
      if (isNaN(pageIdx)) continue;
      result[pageIdx] = expandSinglePageAnnotation(
        pageIdx,
        pageData as CompactSinglePageAnnotation
      );
    }
    return result;
  }

  // Already legacy format
  return json as MultipageAnnotationJson;
}

// ═══════════════════════════════════════════════════════════════
// PAWLS conversion: legacy → compact (for writing/saving)
// ═══════════════════════════════════════════════════════════════

const IM_KEYS: Record<string, string> = {
  image_path: "p",
  format: "f",
  content_hash: "h",
  original_width: "ow",
  original_height: "oh",
  image_type: "it",
  base64_data: "d",
};

function r2(v: number): number {
  const rounded = Math.round(v * 100) / 100;
  return rounded;
}

function compactToken(token: Token): CompactToken {
  return [
    r2(token.x),
    r2(token.y),
    r2(token.width),
    r2(token.height),
    token.text,
  ];
}

function compactImageMeta(token: Token): CompactImageMeta {
  const meta: CompactImageMeta = {};
  for (const [longKey, shortKey] of Object.entries(IM_KEYS)) {
    const val = (token as unknown as Record<string, unknown>)[longKey];
    if (val !== undefined) {
      (meta as Record<string, unknown>)[shortKey] = val;
    }
  }
  return meta;
}

/**
 * Convert a legacy PageTokens to compact format for storage.
 */
export function compactPage(pageTokens: PageTokens): CompactPage {
  const compact: CompactPage = {
    p: [
      r2(pageTokens.page.width),
      r2(pageTokens.page.height),
      pageTokens.page.index,
    ],
    t: [],
  };

  const imageMeta: Record<string, CompactImageMeta> = {};

  pageTokens.tokens.forEach((token, idx) => {
    compact.t.push(compactToken(token));
    if (token.is_image) {
      const meta = compactImageMeta(token);
      if (Object.keys(meta).length > 0) {
        imageMeta[String(idx)] = meta;
      }
    }
  });

  if (Object.keys(imageMeta).length > 0) {
    compact.im = imageMeta;
  }

  return compact;
}

/**
 * Convert legacy PageTokens[] to compact format for storage.
 */
export function toCompactPawls(pages: PageTokens[]): CompactPage[] {
  return pages.map(compactPage);
}

// ═══════════════════════════════════════════════════════════════
// Annotation JSON conversion: legacy → compact (for writing/saving)
// ═══════════════════════════════════════════════════════════════

function compactSinglePageAnnotation(
  annotation: SinglePageAnnotationJson
): CompactSinglePageAnnotation {
  return {
    b: [
      r2(annotation.bounds.left),
      r2(annotation.bounds.top),
      r2(annotation.bounds.right),
      r2(annotation.bounds.bottom),
    ],
    t: annotation.tokensJsons.map((tid) => tid.tokenIndex),
    r: annotation.rawText,
  };
}

/**
 * Convert a legacy MultipageAnnotationJson to compact format for storage.
 */
export function toCompactAnnotationJson(
  json: MultipageAnnotationJson | null | undefined
): Record<string, CompactSinglePageAnnotation> | null {
  if (json === null || json === undefined) return null;
  if (Object.keys(json).length === 0) return {};

  const result: Record<string, CompactSinglePageAnnotation> = {};
  for (const [pageKey, pageData] of Object.entries(json)) {
    result[pageKey] = compactSinglePageAnnotation(pageData);
  }
  return result;
}

// ═══════════════════════════════════════════════════════════════
// Bounding box helpers
// ═══════════════════════════════════════════════════════════════

export function isCompactBoundingBox(
  bbox: unknown
): bbox is [number, number, number, number] {
  return Array.isArray(bbox) && bbox.length === 4;
}

export function normalizeBoundingBox(
  bbox: BoundingBox | [number, number, number, number]
): BoundingBox {
  if (isCompactBoundingBox(bbox)) {
    return { left: bbox[BL], top: bbox[BT], right: bbox[BR], bottom: bbox[BB] };
  }
  return bbox;
}

// ═══════════════════════════════════════════════════════════════
// TokenId helpers (standalone, outside annotation JSON)
// ═══════════════════════════════════════════════════════════════

export function isCompactTokenId(tid: unknown): tid is [number, number] {
  return Array.isArray(tid) && tid.length === 2;
}

export function normalizeTokenId(tid: TokenId | [number, number]): TokenId {
  if (isCompactTokenId(tid)) {
    return { pageIndex: tid[0], tokenIndex: tid[1] };
  }
  return tid;
}

export function normalizeTokenIds(
  tids: (TokenId | [number, number])[]
): TokenId[] {
  if (!tids || tids.length === 0) return [];
  return tids.map(normalizeTokenId);
}
