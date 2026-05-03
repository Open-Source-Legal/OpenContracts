import { PDFPageProxy } from "pdfjs-dist/types/src/display/api";
import { AnnotationLabelType } from "../../../types/graphql-api";
import {
  CompactToken,
  BoundingBox,
  SinglePageAnnotationJson,
} from "../../types";
import {
  scaled,
  normalizeBounds,
  doOverlap,
  spanningBound,
} from "../../../utils/transform";
import { convertAnnotationTokensToText } from "../utils";
import { RenderedSpanAnnotation, TokenId } from "./annotations";
import { PAGE_SPANNING_TOKEN_THRESHOLD } from "../../../assets/configurations/constants";

export type Optional<T> = T | undefined;

// Somehow (still trying to figure this one out), undefined tokens are getting
// passed to getScaledTokenBounds and this is blowing up the entire app. For now,
// test for undefined token and just return this dummy token json.
export const undefined_bounding_box = {
  top: 0,
  bottom: 0,
  left: 0,
  right: 0,
};

export class PDFPageInfo {
  private readonly viewport: ReturnType<PDFPageProxy["getViewport"]>;

  constructor(
    public readonly page: PDFPageProxy,
    public readonly tokens: CompactToken[] = [],
    public scale: number,
    public bounds?: BoundingBox
  ) {
    this.viewport = page.getViewport({ scale: 1 });
  }

  /**
   * Returns true if a token should participate in annotation selection.
   * Filters out degenerate tokens such as page-level bounding boxes emitted
   * by some parsers (e.g. Docling) which have empty text and cover the
   * entire page.  Including them would cause every annotation's spanning
   * bound to expand to the full page dimensions.
   */
  private isSelectableToken(
    t: CompactToken,
    pageWidth: number,
    pageHeight: number
  ): boolean {
    // Exclude all non-image tokens with empty text. While the page-spanning
    // Docling tokens are the most problematic case, any empty-text token
    // contributes no selectable content and would only inflate annotation
    // bounding boxes without adding meaningful text to the selection.
    if (!t.text?.trim() && !t.isImage) return false;

    // Skip tokens that span the entire page (degenerate page captures)
    if (
      t.width >= pageWidth * PAGE_SPANNING_TOKEN_THRESHOLD &&
      t.height >= pageHeight * PAGE_SPANNING_TOKEN_THRESHOLD
    ) {
      return false;
    }

    return true;
  }

  getFreeFormAnnotationForBounds(
    selection: BoundingBox,
    label: AnnotationLabelType
  ): RenderedSpanAnnotation {
    if (this.bounds === undefined) {
      throw new Error("Unknown Page Bounds");
    }

    // Here we invert the scale, because the user has drawn this bounding
    // box, so it is *already* scaled with respect to the client's view. For
    // the annotation, we want to remove this, because storing it with respect
    // to the PDF page's original scale means we can render it everywhere.
    const bounds = scaled(selection, 1 / this.scale);

    return new RenderedSpanAnnotation(
      bounds,
      this.page.pageNumber - 1,
      label,
      [],
      ""
    );
  }

  getPageAnnotationJson(selections: BoundingBox[]): SinglePageAnnotationJson {
    if (this.bounds === undefined) {
      throw new Error("Unknown Page Bounds");
    }
    const viewport = this.viewport;
    const ids: TokenId[] = [];
    const tokenBounds: BoundingBox[] = [];
    for (let i = 0; i < this.tokens.length; i++) {
      if (
        !this.isSelectableToken(this.tokens[i], viewport.width, viewport.height)
      )
        continue;

      for (let j = 0; j < selections.length; j++) {
        const normalized_selection_bounds = normalizeBounds(selections[j]);
        const tokenBound = this.getTokenBounds(this.tokens[i]);

        if (
          doOverlap(scaled(tokenBound, this.scale), normalized_selection_bounds)
        ) {
          ids.push({ pageIndex: this.page.pageNumber - 1, tokenIndex: i });
          tokenBounds.push(tokenBound);
          break;
        }
      }
    }
    if (ids.length === 0) {
      return {
        bounds: {
          top: 0,
          bottom: 0,
          left: 0,
          right: 0,
        },
        tokensJsons: [],
        rawText: "",
      };
    }
    const bounds = spanningBound(tokenBounds);
    const rawText = convertAnnotationTokensToText([this], 0, ids);

    return {
      bounds,
      tokensJsons: ids,
      rawText,
    };
  }

  getBoundsForTokens(selected_tokens: TokenId[]): Optional<BoundingBox> {
    /**
     * Given a list of token ids and page ids, determine the bounding box
     */
    if (this.bounds === undefined) {
      throw new Error("Unknown Page Bounds");
    }

    const this_page_tokens = selected_tokens.filter(
      (token) => token.pageIndex === this.page.pageNumber - 1
    );

    const viewport = this.viewport;
    const tokenBounds: BoundingBox[] = [];
    for (let i = 0; i < this_page_tokens.length; i++) {
      const token = this.tokens[this_page_tokens[i].tokenIndex];
      if (!this.isSelectableToken(token, viewport.width, viewport.height))
        continue;

      tokenBounds.push(this.getTokenBounds(token));
    }
    const bounds = spanningBound(tokenBounds);

    return bounds;
  }

  getAnnotationForBounds(
    selection: BoundingBox,
    label: AnnotationLabelType
  ): Optional<RenderedSpanAnnotation> {
    /* This function is quite complicated. Our objective here is to
      compute overlaps between a bounding box provided by a user and
      grobid token spans associated with a pdf. The complexity here is
      that grobid spans are relative to an absolute scale of the pdf,
      but our user's bounding box is relative to the pdf rendered in their
      client.
 
      The critical key here is that anything we *store* must be relative
      to the underlying pdf. So for example, inside the for loop, we are
      computing:
 
      whether a grobid token (tokenBound), scaled to the current scale of the
      pdf in the client (scaled(tokenBound, this.scale)), is overlapping with
      the bounding box drawn by the user (selection).
 
      But! Once we have computed this, we store the grobid tokens and the bound
      that contains all of them relative to the *original grobid tokens*.
 
      This means that the stored data is not tied to a particular scale, and we
      can re-scale it when we need to (mainly when the user resizes the browser window).
    */
    if (this.bounds === undefined) {
      throw new Error("Unknown Page Bounds");
    }

    // console.log("Get annotations for bounds", selection);

    const viewport = this.viewport;
    const ids: TokenId[] = [];
    const tokenBounds: BoundingBox[] = [];
    for (let i = 0; i < this.tokens.length; i++) {
      if (
        !this.isSelectableToken(this.tokens[i], viewport.width, viewport.height)
      )
        continue;

      const tokenBound = this.getTokenBounds(this.tokens[i]);

      if (doOverlap(scaled(tokenBound, this.scale), selection)) {
        ids.push({ pageIndex: this.page.pageNumber - 1, tokenIndex: i });
        tokenBounds.push(tokenBound);
      }
    }
    if (ids.length === 0) {
      return undefined;
    }
    const bounds = spanningBound(tokenBounds);
    const rawText = convertAnnotationTokensToText([this], 0, ids);
    return new RenderedSpanAnnotation(
      bounds,
      this.page.pageNumber - 1,
      label,
      ids,
      rawText
    );
  }

  getScaledTokenBounds(t: CompactToken): BoundingBox {
    //console.log("getScaledTokenBounds() for t: ", t );
    if (typeof t === "undefined") {
      return undefined_bounding_box;
    }
    return this.getScaledBounds(this.getTokenBounds(t));
  }

  getTokenBounds(t: CompactToken): BoundingBox {
    if (!t) {
      return {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
      };
    } else {
      return {
        left: t.x,
        top: t.y,
        right: t.x + t.width,
        bottom: t.y + t.height,
      };
    }
  }

  getScaledBounds(b: BoundingBox): BoundingBox {
    return scaled(b, this.scale);
  }

  getScreenSpaceBounds(b: BoundingBox): BoundingBox {
    const scaledBounds = this.getScaledBounds(b);
    const pageHeight = this.page.getViewport({ scale: this.scale }).height;

    return {
      left: scaledBounds.left,
      top: pageHeight - scaledBounds.bottom,
      right: scaledBounds.right,
      bottom: pageHeight - scaledBounds.top,
    };
  }

  // Method to create a new instance with an updated scale
  public withScale(newScale: number): PDFPageInfo {
    return new PDFPageInfo(this.page, this.tokens, newScale, this.bounds);
  }
}
