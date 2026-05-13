import styled from "styled-components";

/**
 * Viewport guard around @os-legal/caml-react output.
 *
 * The library owns the article internals, but app pages still need to enforce
 * the local viewport contract: no horizontal escape on mobile, full-width
 * sections use valid gutter padding, and bottom fixed controls get scroll
 * clearance.
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
      padding-left: max(1rem, env(safe-area-inset-left, 0px));
      padding-right: max(1rem, env(safe-area-inset-right, 0px));
    }

    article > section {
      width: 100%;
      max-width: 100%;
      padding-left: max(1rem, env(safe-area-inset-left, 0px)) !important;
      padding-right: max(1rem, env(safe-area-inset-right, 0px)) !important;
    }

    article blockquote {
      padding-left: 1rem;
      padding-right: 1rem;
      margin-left: 0;
      margin-right: 0;
    }
  }
`;
