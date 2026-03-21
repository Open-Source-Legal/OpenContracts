/**
 * DOM offset resolution utilities for the DOCX annotator.
 *
 * These functions compute character offsets from DOM selection positions,
 * enabling accurate annotation placement when the same text appears
 * multiple times in a document.
 */

/** CSS class for annotation label elements injected by the WASM renderer. */
export const ANNOTATION_LABEL_CLASS = "oc-annot-label";

/**
 * Compute an approximate character offset from a DOM selection point.
 *
 * Walks text nodes in document order within the container, skipping text
 * inside annotation label elements (injected by the WASM renderer and not
 * part of the original document text). The result may differ slightly from
 * the true docText offset (e.g. inter-paragraph newlines in docText aren't
 * present as DOM text nodes), but is close enough to disambiguate which
 * occurrence of repeated text the user selected via closest-match.
 */
export function getGlobalOffsetFromDomPosition(
  container: HTMLElement,
  node: Node | null,
  localOffset: number,
  cssClassPrefix: string = ANNOTATION_LABEL_CLASS
): number | null {
  if (!node) return null;

  // If the node is an element, resolve to the child at the given offset
  let targetNode: Node = node;
  let targetOffset: number = localOffset;
  if (node.nodeType === Node.ELEMENT_NODE) {
    const el = node as HTMLElement;
    if (localOffset < el.childNodes.length) {
      targetNode = el.childNodes[localOffset];
      targetOffset = 0;
    } else if (el.childNodes.length > 0) {
      // Past the end — point to end of last child
      targetNode = el.childNodes[el.childNodes.length - 1];
      targetOffset = targetNode.textContent?.length ?? 0;
    } else {
      return null;
    }
  }

  // Classes whose text content is NOT part of docText and should be skipped.
  // Includes annotation labels (WASM renderer) and page numbers (PaginatedDocument).
  const SKIP_CLASSES = [cssClassPrefix, "page-number"];
  // Tag names whose text content is NOT part of docText (e.g. <style>, <title>).
  const SKIP_TAGS = new Set(["STYLE", "TITLE", "SCRIPT"]);

  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode: (n: Node) => {
      let parent = n.parentElement;
      while (parent && parent !== container) {
        if (SKIP_TAGS.has(parent.tagName)) {
          return NodeFilter.FILTER_SKIP;
        }
        if (SKIP_CLASSES.some((cls) => parent!.classList.contains(cls))) {
          return NodeFilter.FILTER_SKIP;
        }
        parent = parent.parentElement;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  let globalOffset = 0;
  let current: Node | null;
  while ((current = walker.nextNode())) {
    if (current === targetNode) {
      return globalOffset + targetOffset;
    }
    globalOffset += current.textContent?.length ?? 0;
  }

  return null;
}

/**
 * Map a character offset in whitespace-normalized text back to the
 * corresponding offset in the original (un-normalized) text.
 *
 * Normalization collapses all whitespace runs to a single space, so a
 * single normalized position may correspond to a multi-character
 * whitespace run in the original. This function walks both strings in
 * lockstep, advancing past whitespace runs in the original whenever the
 * normalized position advances by one.
 */
export function mapNormOffsetToReal(
  originalText: string,
  normOffset: number
): number {
  let realPos = 0;
  let normPos = 0;
  while (normPos < normOffset && realPos < originalText.length) {
    if (/\s/.test(originalText[realPos])) {
      while (realPos < originalText.length && /\s/.test(originalText[realPos]))
        realPos++;
      normPos++;
    } else {
      realPos++;
      normPos++;
    }
  }
  return realPos;
}

/**
 * Pick the closest occurrence of text based on an approximate DOM offset.
 *
 * Given multiple occurrences (from findTextOccurrences) and an approximate
 * character offset from the DOM, returns the occurrence whose start position
 * is closest to the DOM offset.
 */
export function pickClosestOccurrence(
  occurrences: Array<{ start: number; end: number }>,
  approximateOffset: number
): { start: number; end: number } {
  return occurrences.reduce((closest, occ) =>
    Math.abs(occ.start - approximateOffset) <
    Math.abs(closest.start - approximateOffset)
      ? occ
      : closest
  );
}
