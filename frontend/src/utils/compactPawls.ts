/**
 * Compact PAWLs decoder — frontend.
 *
 * Mirrors `opencontractserver/utils/compact_pawls.py` on the backend.
 * The frontend only needs the **decode** direction since it never writes
 * PAWLs — it only fetches and renders.
 *
 * **This module is the ONLY place where v1 wire input is tolerated.**
 * Everywhere else in the frontend works exclusively with the v2-canonical
 * in-memory shape ({@link CompactPage} / {@link CompactToken}).
 *
 * The decoder accepts:
 *   - **v2 wire format** (preferred): `{v: 2, p: [{w, h, t: [[x,y,w,h,"text"], ...]}]}`
 *   - **v1 wire format** (legacy, still on disk for un-reparsed documents):
 *     `[{page: {width,height,index}, tokens: [{x,y,width,height,text,...}]}]`
 *
 * Both inputs produce v2-canonical typed objects. v1 input is converted
 * internally — there is no v1-shape exposed beyond this module.
 *
 * **v2 wire format** (mirrored from the backend):
 * ```json
 * {
 *   "v": 2,
 *   "p": [
 *     {
 *       "w": 612.0,
 *       "h": 792.0,
 *       "t": [[72.0, 720.0, 41.0, 12.0, "Hello"], ...]
 *     }
 *   ]
 * }
 * ```
 * An image token carries a 6th element with metadata short keys:
 * `[x, y, w, h, "", {p: "...", f: "jpeg", ch: "...", ...}]`.
 */

import { CompactImageMeta, CompactPage, CompactToken } from "../components/types";

// ─────────────────────────────────────────────────────────────────────
// Wire-shape types (internal — never leak past the decoder)
// ─────────────────────────────────────────────────────────────────────

/** v2 wire token: a positional array, optionally with a 6th metadata dict. */
type CompactTokenV2Wire = [number, number, number, number, string]
  | [number, number, number, number, string, CompactImageMeta];

/** v2 wire page: short keys + array of positional tokens. */
interface CompactPageV2Wire {
  w: number;
  h: number;
  t: CompactTokenV2Wire[];
}

/** v2 top-level wire envelope. */
export interface CompactPawlsV2Wire {
  v: 2;
  p: CompactPageV2Wire[];
}

/** v1 wire token (verbose dict, legacy on-disk format). */
interface V1WireToken {
  x: number;
  y: number;
  width: number;
  height: number;
  text: string;
  is_image?: boolean;
  image_path?: string;
  base64_data?: string;
  format?: string;
  content_hash?: string;
  original_width?: number;
  original_height?: number;
  image_type?: string;
}

/** v1 wire page (verbose dict, legacy on-disk format). */
interface V1WirePage {
  page: { width: number; height: number; index?: number };
  tokens: V1WireToken[];
}

// ─────────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────────

/**
 * Type guard: `true` if `value` is a v2-shape PAWLs wire envelope.
 *
 * Distinguishes by shape — v2 is a JSON dict with `v: 2` and a `p` array;
 * v1 is a top-level JSON array.
 */
export function isV2WirePawls(value: unknown): value is CompactPawlsV2Wire {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as { v?: unknown; p?: unknown };
  return obj.v === 2 && Array.isArray(obj.p);
}

/**
 * Decode raw PAWLs JSON to canonical v2-shape in-memory pages.
 *
 * Accepts both v1 (array) and v2 (`{v:2, p:[…]}`) wire formats. The output
 * is always {@link CompactPage}[] — the v1 case is normalized internally.
 *
 * @throws {Error} when `json` is non-null but does not match v1 or v2 shape.
 *   Returns `[]` for `null` / `undefined` (treated as "no data" — common
 *   when a document has not been parsed yet).
 */
export function decodeV2Pawls(json: unknown): CompactPage[] {
  if (json == null) return [];

  if (Array.isArray(json)) {
    // v1 wire format — normalize to v2-canonical shape.
    return json.map((page, idx) => normalizeV1Page(page, idx));
  }

  if (isV2WirePawls(json)) {
    return json.p.map((page, idx) => normalizeV2Page(page, idx));
  }

  throw new Error(
    "Invalid PAWLs payload: expected a v1 array or a v2 envelope " +
      "({v:2, p:[…]}), got " +
      describe(json)
  );
}

// ─────────────────────────────────────────────────────────────────────
// Internal helpers — v1 → CompactPage / v2 → CompactPage
// ─────────────────────────────────────────────────────────────────────

/** Best-effort description of an unknown payload for error messages. */
function describe(value: unknown): string {
  if (value === null) return "null";
  if (typeof value !== "object") return typeof value;
  if (Array.isArray(value)) return "array";
  return "object";
}

/** Convert a single v2 wire page to a {@link CompactPage}. */
function normalizeV2Page(page: CompactPageV2Wire, index: number): CompactPage {
  const tokens: CompactToken[] = [];
  if (Array.isArray(page.t)) {
    for (const tokArr of page.t) {
      const tok = normalizeV2Token(tokArr);
      if (tok) tokens.push(tok);
    }
  }
  return {
    index,
    width: page.w ?? 0,
    height: page.h ?? 0,
    tokens,
  };
}

/** Convert a single v2 wire token (positional array) to {@link CompactToken}. */
function normalizeV2Token(arr: unknown): CompactToken | null {
  if (!Array.isArray(arr) || arr.length < 5) return null;

  const token: CompactToken = {
    x: Number(arr[0]),
    y: Number(arr[1]),
    width: Number(arr[2]),
    height: Number(arr[3]),
    text: String(arr[4]),
    isImage: false,
  };

  // 6th element = image metadata dict. Its presence is what marks an image.
  if (arr.length >= 6 && typeof arr[5] === "object" && arr[5] !== null) {
    token.isImage = true;
    token.imageMeta = arr[5] as CompactImageMeta;
  }

  return token;
}

/** Convert a single v1 wire page to a {@link CompactPage}. */
function normalizeV1Page(page: unknown, fallbackIndex: number): CompactPage {
  if (typeof page !== "object" || page === null) {
    throw new Error(
      "Invalid v1 PAWLs page: expected object, got " + describe(page)
    );
  }
  const p = page as Partial<V1WirePage>;
  const meta = p.page ?? { width: 0, height: 0 };
  const tokens: CompactToken[] = Array.isArray(p.tokens)
    ? p.tokens
        .map((t) => normalizeV1Token(t))
        .filter((t): t is CompactToken => t !== null)
    : [];

  return {
    index: typeof meta.index === "number" ? meta.index : fallbackIndex,
    width: typeof meta.width === "number" ? meta.width : 0,
    height: typeof meta.height === "number" ? meta.height : 0,
    tokens,
  };
}

/** Convert a single v1 wire token (verbose dict) to {@link CompactToken}. */
function normalizeV1Token(t: unknown): CompactToken | null {
  if (typeof t !== "object" || t === null) return null;
  const v1 = t as V1WireToken;
  if (
    typeof v1.x !== "number" ||
    typeof v1.y !== "number" ||
    typeof v1.width !== "number" ||
    typeof v1.height !== "number"
  ) {
    return null;
  }

  const token: CompactToken = {
    x: v1.x,
    y: v1.y,
    width: v1.width,
    height: v1.height,
    text: typeof v1.text === "string" ? v1.text : "",
    isImage: Boolean(v1.is_image),
  };

  if (token.isImage) {
    const meta: CompactImageMeta = {};
    if (v1.image_path !== undefined) meta.p = v1.image_path;
    if (v1.base64_data !== undefined) meta.b64 = v1.base64_data;
    if (v1.format !== undefined) meta.f = v1.format;
    if (v1.content_hash !== undefined) meta.ch = v1.content_hash;
    if (v1.original_width !== undefined) meta.ow = v1.original_width;
    if (v1.original_height !== undefined) meta.oh = v1.original_height;
    if (v1.image_type !== undefined) meta.it = v1.image_type;
    token.imageMeta = meta;
  }

  return token;
}
