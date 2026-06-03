import styled from "styled-components";

import { CORPUS_COLORS } from "../styles/corpusDesignTokens";

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
    max-width: 720px;
    margin-inline: auto;
  }

  article > section p {
    margin: 0 0 1.1em;
    line-height: 1.72;
    font-size: 1.0625rem;
    color: ${CORPUS_COLORS.slate[800]};
  }

  article > section li {
    margin: 0.35em 0;
    line-height: 1.65;
    color: ${CORPUS_COLORS.slate[800]};
  }

  article > section ul,
  article > section ol {
    margin: 0.4em 0 1.1em;
    padding-left: 1.4em;
  }

  article > section h2,
  article > section h3 {
    color: ${CORPUS_COLORS.slate[900]};
    letter-spacing: -0.01em;
    line-height: 1.25;
    font-weight: 650;
  }

  article > section h2 {
    font-size: 1.5rem;
    margin: 2.25em 0 0.6em;
    padding-bottom: 0.3em;
    /* hairline rule: teal[700] accent at ~18% alpha (token + 8-digit hex) */
    border-bottom: 1px solid ${CORPUS_COLORS.teal[700]}2e;
  }

  article > section h3 {
    font-size: 1.175rem;
    margin: 1.75em 0 0.4em;
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
      padding-left: max(1.25rem, env(safe-area-inset-left, 0px));
      padding-right: max(1.25rem, env(safe-area-inset-right, 0px));
    }

    article > section {
      width: 100%;
      max-width: 100%;
      padding-left: max(1.25rem, env(safe-area-inset-left, 0px)) !important;
      padding-right: max(1.25rem, env(safe-area-inset-right, 0px)) !important;
    }

    article blockquote {
      padding-left: 1rem;
      padding-right: 1rem;
      margin-left: 0;
      margin-right: 0;
    }
  }
`;
