import styled from "styled-components";

import {
  CORPUS_BREAKPOINTS,
  CORPUS_COLORS,
  CORPUS_FONT_SIZES,
  CORPUS_SPACING,
} from "../styles/corpusDesignTokens";

/**
 * Viewport guard around @os-legal/caml-react output.
 *
 * The library owns the article internals, but app pages still need to enforce
 * the local viewport contract: no horizontal escape on mobile, full-width
 * sections use valid gutter padding, and bottom fixed controls get scroll
 * clearance.
 *
 * It also applies a long-form *reading* layer on top of the library output.
 * Prose blocks are rendered by the shared chat MarkdownMessageRenderer, whose
 * spacing/contrast is tuned for chat bubbles, not articles. Scoping these rules
 * to the article frame gives corpus READMEs article-grade vertical rhythm,
 * heading hierarchy, and contrast without touching the shared chat renderer.
 */
export const CamlArticleFrame = styled.div<{ $bottomInset?: string }>`
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: hidden;
  box-sizing: border-box;

  article {
    width: 100%;
    max-width: 100%;
    min-width: 0;
    overflow-x: hidden;
    box-sizing: border-box;
  }

  article * {
    box-sizing: border-box;
  }

  article > header,
  article > section,
  article > footer {
    max-width: 100%;
    min-width: 0;
    box-sizing: border-box;
  }

  article > section > * {
    max-width: 100%;
    min-width: 0;
  }

  /* ----------------------------------------------------------------------- */
  /* Long-form reading layer (see component docblock).                       */
  /* Caps the measure, opens up vertical rhythm, and restores the heading    */
  /* hierarchy + body contrast that the chat-tuned prose renderer omits.     */
  /*                                                                         */
  /* Scoped to "article > section" ONLY -- the library-owned header (serif   */
  /* title, eyebrow/dek, hero) is intentionally left alone so its elegant    */
  /* muted lead styling survives.                                            */
  /* ----------------------------------------------------------------------- */
  article > section {
    max-width: ${CORPUS_BREAKPOINTS.readingMeasure}px;
    margin-inline: auto;

    /* Neutralize the library's full-bleed dark/gradient padding so it cannot
       collapse the content column. @os-legal/caml-react styles theme:dark /
       gradient chapters full-bleed via "max-width: 100%" + "padding: 3rem
       calc((100% - 720px) / 2 + 2rem)", where the percentage resolves against
       the (wider) article width W, not the section. Capping the section to
       readingMeasure above leaves that padding intact, so the content box works
       out to ~(2*readingMeasure - W): for any viewport wider than ~readingMeasure
       it shrinks, and around W ~ 1300px it collapses to a single word per line
       (and CTA buttons wrap mid-word, e.g. "Contact" / "Us"). A flat gutter that
       matches the light-chapter measure keeps dark/gradient chapters as centered
       boxes instead. The mobile @media block below overrides this with
       safe-area-aware gutters. */
    padding-left: ${CORPUS_SPACING[6]};
    padding-right: ${CORPUS_SPACING[6]};
  }

  /* The reading layer sets NO text color: caml-react already colors prose
     theme-aware and dark chapters set a light section color. Hardcoding dark
     slate here outranks those (extra element vs the library's hashed class) and
     renders dark-on-dark on dark chapters. We own only rhythm + hierarchy. */
  article > section p {
    margin: 0 0 1.1em;
    line-height: 1.72;
    font-size: 1.0625rem;
  }

  article > section li {
    margin: 0.35em 0;
    line-height: 1.65;
  }

  article > section ul,
  article > section ol {
    margin: 0.4em 0 1.1em;
    padding-left: 1.4em;
  }

  article > section h2,
  article > section h3 {
    letter-spacing: -0.01em;
    line-height: 1.25;
    font-weight: 600;
  }

  article > section h2 {
    font-size: ${CORPUS_FONT_SIZES["3xl"]};
    margin: 2.25em 0 0.6em;
    padding-bottom: 0.3em;
    /* hairline rule: teal[700] accent at ~18% alpha. color-mix keeps this robust
       if the token format ever changes (rgb()/oklch()/hex) -- no reliance on a
       6-digit #rrggbb literal for an 8-digit hex concatenation. */
    border-bottom: 1px solid
      color-mix(in srgb, ${CORPUS_COLORS.teal[700]} 18%, transparent);
  }

  article > section h3 {
    font-size: 1.175rem;
    margin: 1.75em 0 0.4em;
  }

  /* Fallthrough for deeper headings (h4-h6) so #### and beyond stay sized
     instead of inheriting browser defaults inside the scoped section. Color is
     left to the library / section inheritance (see the prose note above). */
  article > section h4,
  article > section h5,
  article > section h6 {
    font-size: ${CORPUS_FONT_SIZES.lg};
    font-weight: 600;
    line-height: 1.3;
    margin: 1.5em 0 0.3em;
  }

  article img,
  article table,
  article blockquote,
  article pre {
    max-width: 100%;
  }

  article table,
  article pre {
    overflow-x: auto;
  }

  padding-bottom: ${(props) => props.$bottomInset ?? "0"};

  @media (max-width: 768px) {
    article {
      min-height: 0 !important;
    }

    article > header {
      padding-left: max(${CORPUS_SPACING[5]}, env(safe-area-inset-left, 0px));
      padding-right: max(${CORPUS_SPACING[5]}, env(safe-area-inset-right, 0px));
    }

    article > section {
      width: 100%;
      max-width: 100%;
      padding-left: max(
        ${CORPUS_SPACING[5]},
        env(safe-area-inset-left, 0px)
      ) !important;
      padding-right: max(
        ${CORPUS_SPACING[5]},
        env(safe-area-inset-right, 0px)
      ) !important;
    }

    article blockquote {
      padding-left: 1rem;
      padding-right: 1rem;
      margin-left: 0;
      margin-right: 0;
    }
  }
`;
