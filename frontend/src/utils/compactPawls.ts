/**
 * Compact PAWLs v2 format — frontend decoder.
 *
 * Mirrors `opencontractserver/utils/compact_pawls.py`.
 * The frontend only needs the **expand** (v2 → v1) direction since
 * the backend always serves data, and the frontend only consumes it.
 *
 * v2 format:
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
 *
 * v1 format (what the rest of the frontend expects):
 * ```json
 * [
 *   {
 *     "page": { "width": 612.0, "height": 792.0, "index": 0 },
 *     "tokens": [{ "x": 72.0, "y": 720.0, "width": 41.0, "height": 12.0, "text": "Hello" }, ...]
 *   }
 * ]
 * ```
 */

import { PageTokens, Token } from "../components/types";

/** Compact v2 image metadata (short keys). */
interface CompactImageMeta {
  p?: string; // image_path
  b64?: string; // base64_data
  f?: string; // format
  ch?: string; // content_hash
  ow?: number; // original_width
  oh?: number; // original_height
  it?: string; // image_type
}

/** A single compact page. */
interface CompactPage {
  w: number;
  h: number;
  t: (number | string | CompactImageMeta)[][];
}

/** The top-level compact PAWLs structure. */
interface CompactPawls {
  v: number;
  p: CompactPage[];
}

/**
 * Return `true` if `data` uses the v2 compact PAWLs layout.
 */
export function isCompactPawlsFormat(data: unknown): data is CompactPawls {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as CompactPawls).v === 2 &&
    Array.isArray((data as CompactPawls).p)
  );
}

/**
 * Expand a single compact token array to a v1 Token object.
 */
function expandToken(arr: unknown[]): Token | null {
  if (!Array.isArray(arr) || arr.length < 5) return null;

  const token: Token = {
    x: Number(arr[0]),
    y: Number(arr[1]),
    width: Number(arr[2]),
    height: Number(arr[3]),
    text: String(arr[4]),
  };

  // 6th element = image metadata dict
  if (arr.length >= 6 && typeof arr[5] === "object" && arr[5] !== null) {
    const meta = arr[5] as CompactImageMeta;
    token.is_image = true;
    if (meta.p !== undefined) token.image_path = meta.p;
    if (meta.b64 !== undefined) token.base64_data = meta.b64;
    if (meta.f !== undefined) token.format = meta.f;
    if (meta.ch !== undefined) token.content_hash = meta.ch;
    if (meta.ow !== undefined) token.original_width = meta.ow;
    if (meta.oh !== undefined) token.original_height = meta.oh;
    if (meta.it !== undefined) token.image_type = meta.it;
  }

  return token;
}

/**
 * Normalize PAWLs data to v1 format (`PageTokens[]`).
 *
 * Accepts both v1 (already a `PageTokens[]`) and v2 (compact dict).
 * If already v1, returns as-is. If v2, expands to v1.
 *
 * This is the single entry point the frontend should use after
 * fetching PAWLs data from the server.
 */
export function expandPawlsPages(data: unknown): PageTokens[] {
  if (data == null) return [];

  // Already v1 — pass through
  if (Array.isArray(data)) return data as PageTokens[];

  if (!isCompactPawlsFormat(data)) return [];

  return data.p.map((compactPage, pageIndex) => {
    const tokens: Token[] = [];
    if (Array.isArray(compactPage.t)) {
      for (const tokArr of compactPage.t) {
        if (Array.isArray(tokArr)) {
          const tok = expandToken(tokArr);
          if (tok) tokens.push(tok);
        }
      }
    }

    return {
      page: {
        width: compactPage.w ?? 0,
        height: compactPage.h ?? 0,
        index: pageIndex,
      },
      tokens,
    };
  });
}
